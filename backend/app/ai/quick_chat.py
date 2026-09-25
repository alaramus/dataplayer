"""Persistent plain conversations, separate from agent runs and tools (D158)."""

import asyncio
import logging
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
from app.ai.models import MAX_TITLE_CHARS, Role
from app.ai.providers import ChatModels
from app.core.schemas import get_datetime_utc

logger = logging.getLogger(__name__)
HISTORY_LIMIT = 20
HISTORY_CHARS = 80_000
MAX_QUICK_TEXT = 16_000
ANSWER_LIMIT = 100_000
PROMPT = (
    "You are a plain chat assistant in DataPlayer. Answer in the user's language "
    "using Markdown. You have no access to application data or tools. "
    "Do not claim to have inspected data, files, or connections."
)


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


def summary(chat: QuickConversation) -> QuickChatSummary:
    title = opened(chat.title)
    return QuickChatSummary(
        id=chat.id, title="New chat" if title == "New quick chat" else title,
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


def response_text(response: BaseMessage) -> str:
    if isinstance(response.content, str):
        return response.content
    parts: list[str] = []
    for block in response.content:
        if isinstance(block, dict) and block.get("type") == "text":
            value = block.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)


async def send(
    session: AsyncSession,
    chat: QuickConversation,
    owner_id: uuid.UUID,
    body: QuickChatSend,
    catalog: ModelCatalog,
    chat_models: ChatModels,
) -> QuickChatPublic:
    model = catalog.find(body.model_key or chat.model_key)
    if model is None:
        model = await preferences.chosen_model(session, owner_id, catalog)
    if model is None:
        raise ValueError("Choose a model in AI settings first")
    key = await preferences.key_for(session, owner_id, model.provider)
    if key is None:
        raise ValueError("Add this model provider's API key in AI settings first")
    text = body.text.strip()
    if not text:
        raise ValueError("Write a message first")
    previous = (await session.exec(
        select(QuickMessage)
        .where(QuickMessage.conversation_id == chat.id)
        .order_by(col(QuickMessage.created_at).desc(), col(QuickMessage.id).desc())
        .limit(HISTORY_LIMIT)
    )).all()
    kept: list[QuickMessage] = []
    used = 0
    for row in previous:
        length = len(opened(row.content))
        if used + length > HISTORY_CHARS:
            break
        kept.append(row)
        used += length
    messages: list[BaseMessage] = [SystemMessage(content=PROMPT)]
    messages.extend(
        HumanMessage(content=opened(row.content)) if row.role == "user"
        else AIMessage(content=opened(row.content))
        for row in reversed(kept)
    )
    messages.append(HumanMessage(content=text))
    if not previous and opened(chat.title) in {"New chat", "New quick chat"}:
        chat.title = sealed(text.splitlines()[0][:80])
    chat.model_key = model.key
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="user", content=sealed(text)),
    ])
    await session.commit()
    try:
        async with asyncio.timeout(120):
            response = await chat_models.build(
                model, key, max_output_tokens=min(model.max_output_tokens, 8192)
            ).ainvoke(messages)
    except Exception as error:  # noqa: BLE001  # Provider errors may contain private text
        logger.warning("Quick chat answer failed: %s", type(error).__name__)
        raise RuntimeError(chat_models.sentence(model, error)) from error
    answer = response_text(response)[:ANSWER_LIMIT]
    if not answer.strip():
        raise RuntimeError("The model returned an empty answer")
    chat.updated_at = get_datetime_utc()
    session.add_all([
        chat,
        QuickMessage(conversation_id=chat.id, role="assistant", content=sealed(answer)),
    ])
    await session.commit()
    return await public(session, chat)
