"""What the agent keeps: a person's keys and choices, and the transcript (D139).

The transcript is this project's own and only grows: a conversation, the
messages said in it, the runs that answered and the steps each run took.
The model's working state is LangGraph's, in its own tables; nothing here is
kept in step with it.

Everything anybody said, and every piece of reasoning, is stored encrypted
under `ai_content` (D141). A provider key is a credential and is stored under
`connector` (D140).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, LargeBinary
from sqlmodel import Field, SQLModel

from app.ai.catalog import Provider
from app.core.schemas import get_datetime_utc

# The lifecycle of one answer, and no state outside it. `awaiting_answer` is a
# pause for a person, kept across a restart in the model's working state (D137).
RunStatus = Literal[
    "running",
    "awaiting_answer",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
]

TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled", "interrupted"})

StepKind = Literal["thinking", "tool"]
StepStatus = Literal["running", "done", "failed", "cancelled"]
Role = Literal["user", "assistant"]

MAX_MESSAGE_CHARS = 100_000
MAX_TITLE_CHARS = 200


def _timestamp() -> datetime | None:
    return get_datetime_utc()


class ProviderKey(SQLModel, table=True):
    """One person's key for one provider. Never sent back, only replaced."""

    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    provider: str = Field(primary_key=True, max_length=16)
    secret: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    updated_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class AgentPreferences(SQLModel, table=True):
    """What a person chose for the agent. A row exists once they chose anything."""

    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    # `provider:id` from the catalog. Text rather than a closed set: the file
    # changes with a release, and a stored choice it dropped reads as none.
    model_key: str | None = Field(default=None, max_length=160)
    # Every change in every conversation proceeds without asking, within what
    # the owner of each connection allows (D136).
    allow_all_changes: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )


class Conversation(SQLModel, table=True):
    __table_args__ = (
        # The history reads "mine, most recently active first".
        Index("ix_conversation_owner_updated", "owner_id", "updated_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    # Encrypted like everything said here: an automatic title is the first
    # line of what somebody typed.
    title: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # Once a person names it, no title from the model replaces the name.
    title_is_custom: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )
    # Every change in this conversation proceeds without asking (D136, AI5).
    allow_all_changes: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )
    created_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    updated_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class AgentRun(SQLModel, table=True):
    """One answer: a row before it is a task (D137)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversation.id", nullable=False, ondelete="CASCADE", index=True
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    model_key: str = Field(max_length=160)
    status: str = Field(default="running", max_length=16, index=True)
    # A safe sentence, never a provider's own text (D2c).
    error: str | None = Field(default=None, max_length=500)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    created_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class ConversationMessage(SQLModel, table=True):
    __table_args__ = (
        Index("ix_conversationmessage_conversation_created", "conversation_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversation.id", nullable=False, ondelete="CASCADE"
    )
    # The run a user message started, or the run that wrote an answer.
    run_id: uuid.UUID | None = Field(
        default=None, foreign_key="agentrun.id", ondelete="SET NULL"
    )
    role: str = Field(max_length=16)
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class AgentStep(SQLModel, table=True):
    """What a run is doing, in the words the server chose (D137)."""

    run_id: uuid.UUID = Field(
        foreign_key="agentrun.id", primary_key=True, ondelete="CASCADE"
    )
    ordinal: int = Field(primary_key=True)
    kind: str = Field(max_length=16)
    title: str = Field(max_length=200)
    status: str = Field(default="running", max_length=16)
    # The reasoning a provider returned, encrypted; nothing for most steps.
    detail: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    started_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


# --- what crosses the API ----------------------------------------------------


class AgentModelPublic(BaseModel):
    key: str
    provider: Provider
    id: str
    name: str
    context_window: int
    max_output_tokens: int
    reasoning: bool
    image_input: bool
    # Whether this person has a key for its provider. The settings offer only
    # these, and the list stays whole so the page can say why one is missing.
    available: bool


class ProviderKeyState(BaseModel):
    provider: Provider
    # Set or not, and nothing else: a key is never sent back (D140).
    set: bool


class AgentSettingsPublic(BaseModel):
    model_key: str | None
    # A stored choice the catalog no longer lists. The settings ask for a new
    # one rather than showing a model that cannot be used.
    model_missing: bool
    allow_all_changes: bool
    keys: list[ProviderKeyState]


class AgentSettingsUpdate(BaseModel):
    """What is being changed, and nothing about the rest."""

    model_config = ConfigDict(extra="forbid")

    model_key: str | None = None
    allow_all_changes: bool | None = None


class ProviderKeyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: SecretStr = PydanticField(min_length=1, max_length=1024)


class ProviderKeyCheck(BaseModel):
    ok: bool
    message: str


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime | None
    # Whether an answer is being written or waits for a person now.
    active: bool


class ConversationsPublic(BaseModel):
    data: list[ConversationSummary]
    count: int


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = PydanticField(min_length=1, max_length=MAX_TITLE_CHARS)


class ScreenContext(BaseModel):
    """One open workspace panel explicitly attached to the next message (D133)."""

    model_config = ConfigDict(extra="forbid")

    panel_id: str = PydanticField(min_length=1, max_length=2048)
    label: str = PydanticField(min_length=1, max_length=300)
    kind: Literal[
        "catalog", "rows", "content", "structure", "summary", "record",
        "chart", "queries", "query", "result", "relationships",
    ]
    connector_id: uuid.UUID | None = None
    node_id: str | None = PydanticField(default=None, max_length=2048)


class ConversationMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(min_length=1, max_length=MAX_MESSAGE_CHARS)
    contexts: list[ScreenContext] = PydanticField(default_factory=list, max_length=5)


class AgentStepPublic(BaseModel):
    ordinal: int
    kind: StepKind
    title: str
    status: StepStatus
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentRunPublic(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: RunStatus
    model_key: str
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[AgentStepPublic] = PydanticField(default_factory=list)
    # What has been written so far while the answer is being written, so a
    # page opened mid-answer shows it. Nothing once the answer is a message.
    partial_answer: str | None = None


class ConversationMessagePublic(BaseModel):
    id: uuid.UUID
    role: Role
    content: str
    run_id: uuid.UUID | None = None
    created_at: datetime | None = None


class ConversationPublic(BaseModel):
    id: uuid.UUID
    title: str
    title_is_custom: bool
    created_at: datetime | None
    updated_at: datetime | None
    messages: list[ConversationMessagePublic]
    runs: list[AgentRunPublic]
