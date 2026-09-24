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

from pydantic import BaseModel, ConfigDict, RootModel, SecretStr
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, LargeBinary
from sqlmodel import Field, SQLModel

from app.adapters.content import NodeRepresentation
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

# What the agent may do to data in one conversation (D136). Read only is the
# narrow end and wins over anything the person allowed in general; ask is where
# a conversation starts.
ChangePolicy = Literal["read_only", "ask", "allow", "jev"]

StepKind = Literal["thinking", "tool"]
StepStatus = Literal["running", "done", "failed", "cancelled"]
Role = Literal["user", "assistant"]

MAX_MESSAGE_CHARS = 100_000
MAX_TITLE_CHARS = 200
MAX_PROJECT_CHARS = 120


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


class ChatProject(SQLModel, table=True):
    """A folder of conversations, and nothing more (D141).

    It carries no instructions and no connections of its own: what it is for is
    finding a conversation again, and a folder that quietly changed how the
    agent answers would be a second place to look for that.
    """

    __table_args__ = (Index("ix_chatproject_owner", "owner_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    # Encrypted like everything else a person writes here (D141).
    name: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime | None = Field(
        default_factory=_timestamp,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
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
    # What may be changed from this conversation, and whether it is asked
    # about first (D136, AI5). Text rather than an enum column: a policy added
    # later is a release, not a migration of the column's type.
    change_policy: str = Field(
        default="ask", max_length=16, sa_column_kwargs={"server_default": "ask"}
    )
    # Above the rest of the history, whatever it was last said in (D141).
    pinned: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )
    # Out of the history without being lost. An archived conversation is
    # restored or deleted in the agent's settings and nowhere else (D141).
    archived: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )
    # The model this conversation is held with, chosen in the conversation
    # itself. Empty means the one chosen in the settings, and so does a key the
    # list no longer has (D140).
    model_key: str | None = Field(default=None, max_length=160)
    # The folder it was put in, if any. Deleting the folder empties this rather
    # than taking the conversation with it.
    project_id: uuid.UUID | None = Field(
        default=None, foreign_key="chatproject.id", ondelete="SET NULL", index=True
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


AttachmentKind = Literal["text", "image"]


class MessageAttachment(SQLModel, table=True):
    """A file the person sent with a message, kept with it (D142).

    Its name and its bytes are the person's, so both are sealed the way the
    message text is (D141); what kind of file it is and its size are not, so
    a transcript is listed without opening any of them.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(
        foreign_key="conversationmessage.id", nullable=False, ondelete="CASCADE", index=True
    )
    ordinal: int
    kind: str = Field(max_length=8)
    media_type: str = Field(max_length=64)
    size: int
    name: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


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
    # How the provider is named on screen: the client groups by what it is
    # sent, and knows no provider of its own.
    provider_label: str
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


class AttachmentRules(BaseModel):
    """What one message may carry (D142): the composer checks before sending,
    the server when it is sent, and both read these numbers from here."""

    max_files: int
    max_image_bytes: int
    max_text_bytes: int
    max_total_bytes: int
    image_types: list[str]


class AgentSettingsPublic(BaseModel):
    model_key: str | None
    # A stored choice the catalog no longer lists. The settings ask for a new
    # one rather than showing a model that cannot be used.
    model_missing: bool
    allow_all_changes: bool
    keys: list[ProviderKeyState]
    attachments: AttachmentRules


class AgentSettingsUpdate(BaseModel):
    """What is being changed, and nothing about the rest."""

    model_config = ConfigDict(extra="forbid")

    model_key: str | None = None
    allow_all_changes: bool | None = None


class ProviderKeyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: SecretStr = PydanticField(min_length=1, max_length=1024)


class ProviderKeyTry(BaseModel):
    """A key to check without keeping it. Nothing is stored by a check."""

    model_config = ConfigDict(extra="forbid")

    key: SecretStr | None = PydanticField(default=None, max_length=1024)


class ProviderKeyCheck(BaseModel):
    ok: bool
    message: str


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime | None
    # Whether an answer is being written or waits for a person now.
    active: bool
    # A run is paused on a question or a confirmation: Needs you (D113, D136).
    waiting: bool
    pinned: bool = False
    archived: bool = False
    # What this conversation names for itself, not what it will be answered
    # with: empty means the model chosen in the settings.
    model_key: str | None = None
    change_policy: ChangePolicy = "ask"
    project_id: uuid.UUID | None = None


class ChatProjectPublic(BaseModel):
    id: uuid.UUID
    name: str


class ChatProjectsPublic(BaseModel):
    data: list[ChatProjectPublic]
    count: int


class ChatProjectWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = PydanticField(min_length=1, max_length=MAX_PROJECT_CHARS)


class ConversationsPublic(BaseModel):
    data: list[ConversationSummary]
    count: int


class ConversationUpdate(BaseModel):
    """What is being changed about one conversation, and nothing about the rest.

    A title given here is the person's own and no title from the model replaces
    it afterwards.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = PydanticField(
        default=None, min_length=1, max_length=MAX_TITLE_CHARS
    )
    pinned: bool | None = None
    archived: bool | None = None
    # A model of the catalog, for this conversation alone. Empty leaves
    # whatever it had; there is no command that takes a chosen model away.
    model_key: str | None = PydanticField(default=None, max_length=160)
    change_policy: ChangePolicy | None = None
    # The folder, or `null` for none. Unlike the fields above it, this one is
    # read as sent rather than as set: taking a conversation out of a folder is
    # a change like any other, and `null` has to be able to say it.
    project_id: uuid.UUID | None = None


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


class ScreenContexts(RootModel[list[ScreenContext]]):
    """The tabs of one message as the form field that carries them (D142).

    A model around the list rather than the list itself: FastAPI reads a form
    field typed as a list by collecting every value of that name, and handed
    JSON's validator a list where it expects the string it was sent.
    """


class OpenIntent(BaseModel):
    """One server-validated request to open ordinary Data workspace UI."""

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    connector_name: str
    adapter_type: str
    node_id: str | None = None
    title: str | None = None
    view: Literal["catalog", "preferred", "rows", "structure", "summary"] = "preferred"
    describable: bool = False
    representations: list[NodeRepresentation] = PydanticField(default_factory=list)


class ConversationMessageCreate(BaseModel):
    """The form fields of a message; its files travel beside them (D142).

    Text may be empty when a file is sent — a photo alone is a question too —
    and the route refuses a message with neither.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(default="", max_length=MAX_MESSAGE_CHARS)
    contexts: list[ScreenContext] = PydanticField(default_factory=list, max_length=5)


class ChangePreview(BaseModel):
    """What a change would do, shown in its confirmation card (D46, D136).

    A sentence plus a line per thing that would happen, in the source's own
    words — a rehearsal's outcome per statement, or an action's own preview.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str
    lines: list[str] = PydanticField(default_factory=list, max_length=50)


class AgentQuestion(BaseModel):
    """One resumable choice requested by a tool, independent of LangGraph's format."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["ask_user", "allow_transfer", "confirm_change"]
    question: str = PydanticField(min_length=1, max_length=1000)
    choices: list[str] = PydanticField(min_length=1, max_length=20)
    connector_id: uuid.UUID | None = None
    # What the change would do, when the question is a confirmation (D46).
    preview: ChangePreview | None = None


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = PydanticField(min_length=1, max_length=1000)


class AgentStepPublic(BaseModel):
    ordinal: int
    kind: StepKind
    title: str
    status: StepStatus
    detail: str | None = None
    substeps: list[str] = PydanticField(default_factory=list)
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
    question: AgentQuestion | None = None


class MessageAttachmentPublic(BaseModel):
    id: uuid.UUID
    name: str
    kind: AttachmentKind
    media_type: str
    size: int


class ConversationMessagePublic(BaseModel):
    id: uuid.UUID
    role: Role
    content: str
    attachments: list[MessageAttachmentPublic] = PydanticField(default_factory=list)
    run_id: uuid.UUID | None = None
    created_at: datetime | None = None


class ConversationPublic(BaseModel):
    id: uuid.UUID
    title: str
    title_is_custom: bool
    model_key: str | None = None
    change_policy: ChangePolicy = "ask"
    created_at: datetime | None
    updated_at: datetime | None
    messages: list[ConversationMessagePublic]
    runs: list[AgentRunPublic]
