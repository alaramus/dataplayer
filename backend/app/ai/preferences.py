"""A person's keys and choices for the agent (D140).

A key is written, replaced, removed and checked, and never read back by anyone
but the runner that calls the provider with it.
"""

import asyncio
import logging
import uuid

from langchain_core.tools import tool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.catalog import PROVIDER_TITLES, PROVIDERS, ModelCatalog, ModelInfo, Provider
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
        model_missing=stored.model_key is not None and chosen is None,
        allow_all_changes=stored.allow_all_changes,
        keys=[ProviderKeyState(provider=p, set=p in keys) for p in PROVIDERS],
    )


class SettingsRefused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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
    if update.allow_all_changes is not None:
        stored.allow_all_changes = update.allow_all_changes
    session.add(stored)
    await session.commit()
    return await settings_of(session, user_id, models)


async def remember_model(
    session: AsyncSession, user_id: uuid.UUID, model_key: str
) -> None:
    """A model chosen in a chat is what the next chat starts with too (D140).

    Staged and not committed: the conversation's own change commits both, so
    the chat and the settings never disagree about the last model chosen.
    """
    stored = await _stored(session, user_id)
    stored.model_key = model_key
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
            answer = await chat.bind_tools([ping]).ainvoke(
                "Call the ping tool to check the connection."
            )
    except TimeoutError:
        return ProviderKeyCheck(ok=False, message="The provider did not answer in time")
    except Exception as error:  # noqa: BLE001 - reduced to a sentence below
        # By type only: a provider's text may carry the request it failed on.
        logger.info("A key check failed: %s", type(error).__name__)
        return ProviderKeyCheck(ok=False, message=chat_models.sentence(model, error))
    if not getattr(answer, "tool_calls", None):
        return ProviderKeyCheck(
            ok=True,
            message=f"The key works, but {model.name} did not call a tool when asked",
        )
    return ProviderKeyCheck(ok=True, message=f"The key works with {model.name}")
