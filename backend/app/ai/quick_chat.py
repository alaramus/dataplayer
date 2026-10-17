"""Persistent plain conversations, separate from agent runs and tools (D158)."""

import asyncio
import logging
import time
import uuid
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, LargeBinary
from sqlmodel import Field, SQLModel, col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import preferences
from app.ai.catalog import ModelCatalog
from app.ai.content import opened, sealed
from app.ai.conversations import NEW_CHAT
from app.ai.models import MAX_TITLE_CHARS, Role
from app.ai.prompts import language_line
from app.ai.providers import ChatModels
from app.ai.providers.failures import UNKNOWN_FAILURE
from app.ai.quick_answers import QuickAnswers
from app.ai.runner import DELTA_INTERVAL_SECONDS, split_text
from app.ai.topic import QuickAnswerDelta, announce_quick
from app.core.logs import record_failure, with_ref
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, Language, current_language, say
from app.realtime.topics import TopicSet

logger = logging.getLogger(__name__)
HISTORY_LIMIT = 20
HISTORY_CHARS = 80_000
MAX_QUICK_TEXT = 16_000
ANSWER_LIMIT = 100_000
# A model that stops writing for this long has stopped; one that keeps writing
# is let go on up to the whole limit. A single limit on the whole answer cut
# long answers off while they were still arriving.
QUIET_SECONDS = 60.0
ANSWER_SECONDS = 300.0
TOO_QUIET = N_("The model stopped answering")
PROMPT = (
    "You are a plain chat assistant in DataPlayer. Answer in the user's language "
    "using Markdown. You have no access to application data or tools. "
    "Do not claim to have inspected data, files, or connections."
)


def quick_prompt(language: Language) -> str:
    line = language_line(language)
    return f"{PROMPT} {line}" if line else PROMPT

# The model Chrome runs on the person's own machine (D223). It is in no
# catalog: the server never calls it, and only stores what the browser wrote.
BROWSER_MODEL_KEY = "browser:gemini-nano"


class QuickConversation(SQLModel, table=True):
    __table_args__ = (
        Index("ix_quickconversation_owner_updated", "owner_id", "updated_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    title: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    model_key: str | None = Field(default=None, max_length=160)
    pinned: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    archived: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    project_id: uuid.UUID | None = Field(
        default=None, foreign_key="chatproject.id", ondelete="SET NULL", index=True
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class QuickMessage(SQLModel, table=True):
    __table_args__ = (
        Index("ix_quickmessage_chat_created", "conversation_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="quickconversation.id", nullable=False, ondelete="CASCADE"
    )
    role: str = Field(max_length=16)
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class QuickChatSummary(BaseModel):
    id: uuid.UUID
    title: str
    model_key: str | None
    updated_at: datetime | None
    pinned: bool
    archived: bool
    project_id: uuid.UUID | None


class QuickChatUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = PydanticField(default=None, min_length=1, max_length=MAX_TITLE_CHARS)
    pinned: bool | None = None
    archived: bool | None = None
    project_id: uuid.UUID | None = None


class QuickChatMessagePublic(BaseModel):
    id: uuid.UUID
    role: Role
    content: str
    created_at: datetime | None


class QuickChatPublic(QuickChatSummary):
    messages: list[QuickChatMessagePublic]


class QuickChatSend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(min_length=1, max_length=MAX_QUICK_TEXT)
    model_key: str | None = PydanticField(default=None, max_length=160)


class BrowserQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(min_length=1, max_length=MAX_QUICK_TEXT)


class BrowserAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(min_length=1, max_length=ANSWER_LIMIT)


class QuickTurnMessage(BaseModel):
    role: Role
    content: str


class BrowserTurn(BaseModel):
    """What the browser's model is given: the prompt and the trimmed history a
    provider would be given, so the two paths cannot drift apart."""

    chat: QuickChatPublic
    prompt: str
    history: list[QuickTurnMessage]


def shown_title(title: str) -> str:
    """The title a quick chat is listed and found by: an older untitled one was
    stored as "New quick chat"."""
    return say(NEW_CHAT) if title in (NEW_CHAT, "New quick chat") else title


def summary(chat: QuickConversation) -> QuickChatSummary:
    return QuickChatSummary(
        id=chat.id, title=shown_title(opened(chat.title)),
        model_key=chat.model_key,
        updated_at=chat.updated_at, pinned=chat.pinned, archived=chat.archived,
        project_id=chat.project_id,
    )


async def get_for_owner(
    session: AsyncSession, chat_id: uuid.UUID, owner_id: uuid.UUID
) -> QuickConversation | None:
    chat = await session.get(QuickConversation, chat_id)
    return chat if chat is not None and chat.owner_id == owner_id else None


async def list_for_owner(
    session: AsyncSession, owner_id: uuid.UUID, *, archived: bool = False
) -> list[QuickChatSummary]:
    rows = (await session.exec(
        select(QuickConversation)
        .where(QuickConversation.owner_id == owner_id, col(QuickConversation.archived).is_(archived))
        .order_by(col(QuickConversation.pinned).desc(), col(QuickConversation.updated_at).desc())
        .limit(200)
    )).all()
    return [summary(chat) for chat in rows]


async def delete_archived_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> int:
    ids = list((await session.exec(
        select(QuickConversation.id).where(
            QuickConversation.owner_id == owner_id,
            col(QuickConversation.archived).is_(True),
        )
    )).all())
    if ids:
        await session.exec(delete(QuickConversation).where(col(QuickConversation.id).in_(ids)))
        await session.commit()
    return len(ids)


async def public(session: AsyncSession, chat: QuickConversation) -> QuickChatPublic:
    rows = (await session.exec(
        select(QuickMessage)
        .where(QuickMessage.conversation_id == chat.id)
        .order_by(col(QuickMessage.created_at), col(QuickMessage.id))
    )).all()
    return QuickChatPublic(
        **summary(chat).model_dump(),
        messages=[QuickChatMessagePublic(
            id=row.id,
            role="user" if row.role == "user" else "assistant",
            content=opened(row.content),
            created_at=row.created_at,
        ) for row in rows],
    )


async def _history(session: AsyncSession, chat: QuickConversation) -> list[QuickTurnMessage]:
    """The latest messages, oldest first, within the count and the characters
    a model is given."""
    previous = (await session.exec(
        select(QuickMessage)
        .where(QuickMessage.conversation_id == chat.id)
        .order_by(col(QuickMessage.created_at).desc(), col(QuickMessage.id).desc())
        .limit(HISTORY_LIMIT)
    )).all()
    kept: list[QuickTurnMessage] = []
    used = 0
    for row in previous:
        content = opened(row.content)
        if used + len(content) > HISTORY_CHARS:
            break
        kept.append(QuickTurnMessage(
            role="user" if row.role == "user" else "assistant", content=content
        ))
        used += len(content)
    return kept[::-1]


async def _last_message(session: AsyncSession, chat: QuickConversation) -> QuickMessage | None:
    return (await session.exec(
        select(QuickMessage)
        .where(QuickMessage.conversation_id == chat.id)
        .order_by(col(QuickMessage.created_at).desc(), col(QuickMessage.id).desc())
        .limit(1)
    )).first()


async def _name_by_question(session: AsyncSession, chat: QuickConversation, text: str) -> None:
    if (
        opened(chat.title) in {NEW_CHAT, "New quick chat"}
        and await _last_message(session, chat) is None
    ):
        chat.title = sealed(text.splitlines()[0][:80])


async def ask_in_browser(
    session: AsyncSession, chat: QuickConversation, body: BrowserQuestion
) -> BrowserTurn:
    """Keeps the question, as `send` does before the model is called, and hands
    the browser what to answer it from (D223)."""
    text = body.text.strip()
    if not text:
        raise ValueError(say("Write a message first"))
    history = await _history(session, chat)
    await _name_by_question(session, chat, text)
    # Not remembered as the person's choice: the settings name a model the
    # server can call, and this one exists only in a browser.
    chat.model_key = BROWSER_MODEL_KEY
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="user", content=sealed(text)),
    ])
    await session.commit()
    return BrowserTurn(chat=await public(session, chat), prompt=quick_prompt(current_language.get()), history=history)


async def answer_from_browser(
    session: AsyncSession, chat: QuickConversation, body: BrowserAnswer
) -> QuickChatPublic:
    last = await _last_message(session, chat)
    if last is None or last.role != "user":
        raise ValueError(say("No question is waiting for an answer"))
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="assistant", content=sealed(body.text)),
    ])
    await session.commit()
    return await public(session, chat)


async def send(
    session: AsyncSession,
    chat: QuickConversation,
    owner_id: uuid.UUID,
    body: QuickChatSend,
    catalog: ModelCatalog,
    chat_models: ChatModels,
    topics: TopicSet,
    answers: QuickAnswers,
) -> QuickChatPublic:
    model = catalog.find(body.model_key or chat.model_key)
    if model is None:
        model = await preferences.chosen_model(session, owner_id, catalog)
    if model is None:
        raise ValueError(say("Choose a model in AI settings first"))
    key = await preferences.key_for(session, owner_id, model.provider)
    if key is None:
        raise ValueError(say("Add this model provider's API key in AI settings first"))
    text = body.text.strip()
    if not text:
        raise ValueError(say("Write a message first"))
    history = await _history(session, chat)
    messages: list[BaseMessage] = [SystemMessage(content=quick_prompt(current_language.get()))]
    messages.extend(
        HumanMessage(content=one.content) if one.role == "user" else AIMessage(content=one.content)
        for one in history
    )
    messages.append(HumanMessage(content=text))
    await _name_by_question(session, chat, text)
    # An explicitly chosen model is what the next chat starts with too (D140),
    # as a choice in an agent chat is: staged, and committed with the chat.
    # Only a change is remembered: the window sends its model with every
    # message, and rewriting the same one would switch Jev's choice off.
    if body.model_key is not None:
        remembered = await preferences.chosen_model(session, owner_id, catalog)
        if remembered is None or remembered.key != model.key:
            await preferences.remember_model(session, owner_id, model.key)
    chat.model_key = model.key
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="user", content=sealed(text)),
    ])
    await session.commit()
    # Streamed to the window as it is written; what this returns is still the
    # authority, so an event the socket missed costs nothing.
    async def deliver(text: str) -> None:
        await announce_quick(topics, owner_id, QuickAnswerDelta(chat_id=chat.id, text=text))

    written: list[str] = []
    unsent = ""
    sent_at = time.monotonic()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ANSWER_SECONDS
    failure: str | None = None
    ref: str | None = None
    async def write() -> None:
        nonlocal unsent, sent_at
        async with asyncio.timeout(QUIET_SECONDS) as limit:
            async for chunk in chat_models.build(
                model, key, max_output_tokens=min(model.max_output_tokens, 8192)
            ).astream(messages):
                limit.reschedule(min(loop.time() + QUIET_SECONDS, deadline))
                said = split_text(chunk)[0]
                written.append(said)
                unsent += said
                if unsent and time.monotonic() - sent_at >= DELTA_INTERVAL_SECONDS:
                    await deliver(unsent)
                    unsent, sent_at = "", time.monotonic()
            if unsent:
                await deliver(unsent)

    # A task of its own, so Stop can cancel the writing and leave this request
    # to keep what was written and answer as usual.
    writer = asyncio.create_task(write())
    stopped = False
    try:
        with answers.writing(chat.id, owner_id, writer) as entry:
            try:
                await writer
            except asyncio.CancelledError:
                if not entry.stopped:
                    writer.cancel()
                    raise
                stopped = True
    except TimeoutError:
        logger.warning("Quick chat answer stopped arriving")
        failure = say(TOO_QUIET)
    except Exception as error:  # noqa: BLE001  # Provider errors may contain private text
        sentence = chat_models.sentence(model, error)
        failure = say(sentence)
        if sentence == UNKNOWN_FAILURE:
            ref = record_failure(logger, "A quick chat answer failed", error, private=True)
        else:
            logger.warning("Quick chat answer failed: %s", type(error).__name__)

    def refused(message: str) -> str:
        # The ref closes the whole message rather than cutting it in two.
        return message if ref is None else with_ref(message, ref)

    answer = "".join(written)[:ANSWER_LIMIT]
    if not answer.strip():
        if stopped:
            return await public(session, chat)
        raise RuntimeError(refused(failure or say("The model returned an empty answer")))
    # Kept even when the provider failed on the way: an answer that broke off
    # at its end is most of an answer, and it was already on the screen.
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="assistant", content=sealed(answer)),
    ])
    await session.commit()
    if failure is not None:
        raise RuntimeError(refused(say("{failure}. The answer so far is kept.", failure=failure)))
    return await public(session, chat)
