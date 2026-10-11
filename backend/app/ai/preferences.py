"""A person's keys and choices for the agent (D140).

A key is written, replaced, removed and checked, and never read back by anyone
but the runner that calls the provider with it.
"""

import asyncio
import logging
import uuid

from langchain_core.tools import tool
from langchain_typesafe import Noul, TypeSafeClassifier
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.attachments import RULES as ATTACHMENT_RULES
from app.ai.catalog import (
    CHAT_PROVIDERS,
    PROVIDER_KEY_PAGES,
    PROVIDER_TITLES,
    PROVIDERS,
    AutoProvider,
    ChatProvider,
    ModelCatalog,
    ModelInfo,
    Provider,
    auto_provider_of,
)
from app.ai.models import (
    AgentModelPublic,
    AgentPreferences,
    AgentSettingsPublic,
    AgentSettingsUpdate,
    Conversation,
    ProviderKey,
    ProviderKeyCheck,
    ProviderKeyState,
)
from app.ai.providers import ChatModels
from app.core import crypto
from app.core.schemas import get_datetime_utc

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 60.0
# Enough for a model that thinks before it answers, and little enough to cost
# nothing worth mentioning.
CHECK_OUTPUT_TOKENS = 2048


async def _keys(session: AsyncSession, user_id: uuid.UUID) -> dict[str, ProviderKey]:
    rows = (
        await session.exec(select(ProviderKey).where(ProviderKey.user_id == user_id))
    ).all()
    return {row.provider: row for row in rows}


async def key_for(
    session: AsyncSession, user_id: uuid.UUID, provider: Provider
) -> str | None:
    row = await session.get(ProviderKey, (user_id, provider))
    if row is None:
        return None
    return crypto.decrypt(row.secret, purpose="connector").decode()


async def set_key(
    session: AsyncSession, user_id: uuid.UUID, provider: Provider, key: str
) -> None:
    row = await session.get(ProviderKey, (user_id, provider))
    sealed = crypto.encrypt(key.encode(), purpose="connector")
    if row is None:
        row = ProviderKey(user_id=user_id, provider=provider, secret=sealed)
    else:
        row.secret = sealed
        row.updated_at = get_datetime_utc()
    session.add(row)
    await session.commit()


async def remove_key(
    session: AsyncSession, user_id: uuid.UUID, provider: Provider
) -> None:
    row = await session.get(ProviderKey, (user_id, provider))
    if row is not None:
        await session.delete(row)
        await session.commit()


async def _stored(session: AsyncSession, user_id: uuid.UUID) -> AgentPreferences:
    row = await session.get(AgentPreferences, user_id)
    return row if row is not None else AgentPreferences(user_id=user_id)


async def settings_of(
    session: AsyncSession, user_id: uuid.UUID, models: ModelCatalog
) -> AgentSettingsPublic:
    stored = await _stored(session, user_id)
    keys = await _keys(session, user_id)
    chosen = models.find(stored.model_key)
    return AgentSettingsPublic(
        model_key=chosen.key if chosen else None,
        auto_provider=auto_provider_of(stored.auto_provider) if chosen else None,
        model_missing=stored.model_key is not None and chosen is None,
        allow_all_changes=stored.allow_all_changes,
        keys=[
            ProviderKeyState(provider=p, set=p in keys, key_page=PROVIDER_KEY_PAGES[p]) for p in PROVIDERS
        ],
        attachments=ATTACHMENT_RULES,
    )


class SettingsRefused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def check_auto_choice(
    session: AsyncSession,
    user_id: uuid.UUID,
    auto_provider: AutoProvider,
    fallback: ModelInfo | None,
) -> None:
    """Refuse a Jev choice that could not answer (D157).

    The fallback answers whenever Jev cannot, so it must be callable: across
    every provider it may be any keyed model, within one it must be of it.
    """
    if fallback is None:
        raise SettingsRefused("Choose a fallback model first")
    if auto_provider == "all":
        if await key_for(session, user_id, fallback.provider) is None:
            raise SettingsRefused(
                f"Set the {PROVIDER_TITLES[fallback.provider]} API key first"
            )
    else:
        if fallback.provider != auto_provider:
            raise SettingsRefused("Choose a fallback model from this provider")
        if await key_for(session, user_id, auto_provider) is None:
            raise SettingsRefused("Set this model provider's API key first")
    if await key_for(session, user_id, "typesafe") is None:
        raise SettingsRefused("Set a Jev API key first")


async def update_settings(
    session: AsyncSession,
    user_id: uuid.UUID,
    update: AgentSettingsUpdate,
    models: ModelCatalog,
) -> AgentSettingsPublic:
    stored = await _stored(session, user_id)
    if "model_key" in update.model_fields_set:
        if update.model_key is not None and models.find(update.model_key) is None:
            raise SettingsRefused("That model is not in the list")
        stored.model_key = update.model_key
        if "auto_provider" not in update.model_fields_set:
            stored.auto_provider = None
    if "auto_provider" in update.model_fields_set:
        if update.auto_provider is not None:
            await check_auto_choice(
                session, user_id, update.auto_provider,
                models.find(update.model_key or stored.model_key),
            )
        stored.auto_provider = update.auto_provider
    if update.allow_all_changes is not None:
        stored.allow_all_changes = update.allow_all_changes
    session.add(stored)
    await session.commit()
    return await settings_of(session, user_id, models)


async def remember_model(
    session: AsyncSession, user_id: uuid.UUID, model_key: str,
    auto_provider: AutoProvider | None = None,
) -> None:
    """A model chosen in a chat is what the next chat starts with too (D140).

    Staged and not committed: the conversation's own change commits both, so
    the chat and the settings never disagree about the last model chosen.
    """
    stored = await _stored(session, user_id)
    stored.model_key = model_key
    stored.auto_provider = auto_provider
    session.add(stored)


async def chosen_model(
    session: AsyncSession, user_id: uuid.UUID, models: ModelCatalog
) -> ModelInfo | None:
    return models.find((await _stored(session, user_id)).model_key)


async def model_for(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation: Conversation,
    models: ModelCatalog,
) -> ModelInfo | None:
    """The model a conversation is answered with (D140).

    Its own when it names one; otherwise the person's choice. A conversation
    naming a model the list no longer has falls back the same way a stored
    choice does, rather than refusing to answer at all.
    """
    return models.find(conversation.model_key) or await chosen_model(
        session, user_id, models
    )


async def auto_provider_for(
    session: AsyncSession, user_id: uuid.UUID, conversation: Conversation
) -> AutoProvider | None:
    stored = (
        conversation.auto_provider
        if conversation.model_key is not None
        else (await _stored(session, user_id)).auto_provider
    )
    return auto_provider_of(stored)


async def keyed_chat_providers(
    session: AsyncSession, user_id: uuid.UUID
) -> list[ChatProvider]:
    """Every chat provider this person has a key for, in catalog order (D157).

    Read at the start of an answer rather than trusted from a stored choice:
    a key removed after the choice still routes only where a call can go.
    """
    keys = await _keys(session, user_id)
    return [provider for provider in CHAT_PROVIDERS if provider in keys]


async def models_for(
    session: AsyncSession, user_id: uuid.UUID, models: ModelCatalog
) -> list[AgentModelPublic]:
    keys = await _keys(session, user_id)
    return [
        AgentModelPublic(
            key=model.key,
            provider=model.provider,
            provider_label=PROVIDER_TITLES[model.provider],
            id=model.id,
            name=model.name,
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            reasoning=model.reasoning,
            image_input=model.image_input,
            available=model.provider in keys,
        )
        # Grouped by provider in the order the providers are listed, the file's
        # own order within each: the client draws the groups as they arrive.
        for model in sorted(models.models, key=lambda one: PROVIDERS.index(one.provider))
    ]


@tool
def ping() -> str:
    """Answer that the connection works. Call it when asked to check."""
    return "pong"


async def check_key(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider: Provider,
    models: ModelCatalog,
    chat_models: ChatModels,
    candidate: str | None = None,
) -> ProviderKeyCheck:
    """A small call that uses a tool, which also proves the model can call one.

    The model is the one chosen when it belongs to this provider, otherwise
    the first the list has for it.

    A key typed into the form is checked as it stands, before anybody decides
    to keep it; nothing is written either way. Without one the stored key is
    checked.
    """
    key = candidate if candidate is not None else await key_for(session, user_id, provider)
    if key is None:
        return ProviderKeyCheck(ok=False, message="No key is set for this provider")
    if provider == "typesafe":
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                answer = await TypeSafeClassifier(api_key=key).ainvoke(
                    {
                        "state": "Check the Jev API key.",
                        "questions": {"ready": Noul(instructions="Is this a key check?")},
                    }
                )
            if "ready" in answer.nouls:
                return ProviderKeyCheck(ok=True, message="The Jev key works")
        except Exception as error:  # noqa: BLE001 - provider text must stay private
            logger.info("A Jev key check failed: %s", type(error).__name__)
        return ProviderKeyCheck(ok=False, message="The Jev key could not be verified")
    chosen = await chosen_model(session, user_id, models)
    model = (
        chosen
        if chosen is not None and chosen.provider == provider
        else next((m for m in models.models if m.provider == provider), None)
    )
    if model is None:
        return ProviderKeyCheck(ok=False, message="The list has no model of this provider")
    chat = chat_models.build(model, key, max_output_tokens=CHECK_OUTPUT_TOKENS)
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            chat_answer = await chat.bind_tools([ping]).ainvoke(
                "Call the ping tool to check the connection."
            )
    except TimeoutError:
        return ProviderKeyCheck(ok=False, message="The provider did not answer in time")
    except Exception as error:  # noqa: BLE001 - reduced to a sentence below
        # By type only: a provider's text may carry the request it failed on.
        logger.info("A key check failed: %s", type(error).__name__)
        return ProviderKeyCheck(ok=False, message=chat_models.sentence(model, error))
    if not getattr(chat_answer, "tool_calls", None):
        return ProviderKeyCheck(
            ok=True,
            message=f"The key works, but {model.name} did not call a tool when asked",
        )
    return ProviderKeyCheck(ok=True, message=f"The key works with {model.name}")
