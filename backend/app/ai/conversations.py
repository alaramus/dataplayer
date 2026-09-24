"""The transcript as rows: conversations, what was said, and how each answer ran.

Database access only, and the one place a stored row becomes what the API
sends. Somebody else's conversation is not found rather than refused, the rule
connections and jobs follow (D33, D81).
"""

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func
from sqlalchemy.orm import QueryableAttribute, defer
from sqlmodel import col, delete, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.attachments import NewAttachment
from app.ai.catalog import ChatProvider, chat_provider_of
from app.ai.content import opened, sealed, sealed_bytes
from app.ai.models import (
    MAX_TITLE_CHARS,
    TERMINAL,
    AgentQuestion,
    AgentRun,
    AgentRunPublic,
    AgentStep,
    AgentStepPublic,
    ChangePolicy,
    ChatProject,
    ChatProjectPublic,
    ChatProjectsPublic,
    Conversation,
    ConversationMessage,
    ConversationMessagePublic,
    ConversationPublic,
    ConversationsPublic,
    ConversationSummary,
    MessageAttachment,
    MessageAttachmentPublic,
    Role,
    RunStatus,
    StepKind,
    StepStatus,
)
from app.core.schemas import get_datetime_utc

# How many answers a conversation page carries with their steps. The messages
# are all there; the runs are what explains the latest of them.
RECENT_RUNS = 20


def first_line_title(text: str) -> str:
    """The title a conversation has before a model writes one (D141)."""
    line = next((part.strip() for part in text.splitlines() if part.strip()), "")
    return line[:MAX_TITLE_CHARS] or "New chat"


def policy_of(value: str) -> ChangePolicy:
    """The stored text as the closed set it is (D136).

    Written by hand rather than cast: a column holding a policy some later
    release stopped offering reads as the one every conversation starts with,
    which is the careful end, instead of reaching the browser as a value
    nothing there knows.
    """
    if value == "read_only":
        return "read_only"
    if value == "allow":
        return "allow"
    if value == "jev":
        return "jev"
    return "ask"


def summary_of(
    conversation: Conversation, *, active: bool, waiting: bool
) -> ConversationSummary:
    """One row of the history: the one place a stored conversation becomes one."""
    return ConversationSummary(
        id=conversation.id,
        title=opened(conversation.title),
        updated_at=conversation.updated_at,
        active=active,
        waiting=waiting,
        pinned=conversation.pinned,
        archived=conversation.archived,
        model_key=conversation.model_key,
        auto_provider=chat_provider_of(conversation.auto_provider),
        change_policy=policy_of(conversation.change_policy),
        project_id=conversation.project_id,
    )


async def create(
    session: AsyncSession, owner_id: uuid.UUID, title: str = "New chat"
) -> Conversation:
    conversation = Conversation(owner_id=owner_id, title=sealed(title))
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_for_owner(
    session: AsyncSession, conversation_id: uuid.UUID, owner_id: uuid.UUID
) -> Conversation | None:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.owner_id != owner_id:
        return None
    return conversation


async def list_for_owner(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    skip: int,
    limit: int,
    archived: bool = False,
) -> ConversationsPublic:
    """The history, or the archive: one list or the other, never both (D141)."""
    count = (
        await session.exec(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.owner_id == owner_id,
                col(Conversation.archived).is_(archived),
            )
        )
    ).one()
    rows = (
        await session.exec(
            select(Conversation)
            .where(
                Conversation.owner_id == owner_id,
                col(Conversation.archived).is_(archived),
            )
            .order_by(col(Conversation.pinned).desc(), col(Conversation.updated_at).desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    active = set(
        (
            await session.exec(
                select(AgentRun.conversation_id).where(
                    col(AgentRun.conversation_id).in_([row.id for row in rows]),
                    col(AgentRun.status).in_(["running", "awaiting_answer"]),
                )
            )
        ).all()
    )
    waiting = set(
        (
            await session.exec(
                select(AgentRun.conversation_id).where(
                    col(AgentRun.conversation_id).in_([row.id for row in rows]),
                    col(AgentRun.status) == "awaiting_answer",
                )
            )
        ).all()
    )
    return ConversationsPublic(
        data=[
            summary_of(row, active=row.id in active, waiting=row.id in waiting)
            for row in rows
        ],
        count=count,
    )


async def has_image_attachment(session: AsyncSession, conversation_id: uuid.UUID) -> bool:
    found = await session.exec(
        select(MessageAttachment.id)
        .join(
            ConversationMessage,
            col(MessageAttachment.message_id) == col(ConversationMessage.id),
        )
        .where(col(ConversationMessage.conversation_id) == conversation_id)
        .where(col(MessageAttachment.kind) == "image")
        .limit(1)
    )
    return found.first() is not None


async def change(
    session: AsyncSession,
    conversation: Conversation,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
    model_key: str | None = None,
    auto_provider: ChatProvider | None = None,
    set_auto_provider: bool = False,
    change_policy: ChangePolicy | None = None,
    project_id: uuid.UUID | None = None,
    move: bool = False,
) -> Conversation:
    """Apply what was asked and leave the rest alone.

    A pin survives archiving: a conversation restored from the archive comes
    back where it was, not at the bottom of the history.
    """
    if title is not None:
        conversation.title = sealed(title)
        conversation.title_is_custom = True
    if pinned is not None:
        conversation.pinned = pinned
    if archived is not None:
        conversation.archived = archived
    if model_key is not None:
        conversation.model_key = model_key
    if set_auto_provider:
        conversation.auto_provider = auto_provider
    if change_policy is not None:
        conversation.change_policy = change_policy
    # Said apart from the value: taking a conversation out of every folder is a
    # move, and it is `None` like leaving the folder alone would be.
    if move:
        conversation.project_id = project_id
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def retitle(
    session: AsyncSession, conversation_id: uuid.UUID, title: str
) -> bool:
    """A title from the model, unless the person named it meanwhile."""
    result = await session.exec(
        update(Conversation)
        .where(
            col(Conversation.id) == conversation_id,
            col(Conversation.title_is_custom).is_(False),
        )
        .values(title=sealed(title))
    )
    await session.commit()
    return bool(result.rowcount)


async def projects_for_owner(
    session: AsyncSession, owner_id: uuid.UUID
) -> ChatProjectsPublic:
    rows = (
        await session.exec(
            select(ChatProject)
            .where(ChatProject.owner_id == owner_id)
            .order_by(col(ChatProject.created_at))
        )
    ).all()
    data = [
        ChatProjectPublic(id=row.id, name=opened(row.name)) for row in rows
    ]
    return ChatProjectsPublic(data=data, count=len(data))


async def create_project(
    session: AsyncSession, owner_id: uuid.UUID, name: str
) -> ChatProject:
    project = ChatProject(owner_id=owner_id, name=sealed(name))
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def project_for_owner(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> ChatProject | None:
    project = await session.get(ChatProject, project_id)
    if project is None or project.owner_id != owner_id:
        return None
    return project


async def rename_project(
    session: AsyncSession, project: ChatProject, name: str
) -> ChatProject:
    project.name = sealed(name)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: ChatProject) -> None:
    """The folder goes; every conversation in it stays, out of any folder."""
    await session.exec(
        update(Conversation)
        .where(col(Conversation.project_id) == project.id)
        .values(project_id=None)
    )
    await session.delete(project)
    await session.commit()


async def archived_ids_for_owner(
    session: AsyncSession, owner_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        (
            await session.exec(
                select(Conversation.id).where(
                    Conversation.owner_id == owner_id,
                    col(Conversation.archived).is_(True),
                )
            )
        ).all()
    )


async def delete_rows(session: AsyncSession, conversation_ids: list[uuid.UUID]) -> None:
    if not conversation_ids:
        return
    await session.exec(
        delete(Conversation).where(col(Conversation.id).in_(conversation_ids))
    )
    await session.commit()


async def add_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: Role,
    text: str,
    run_id: uuid.UUID | None,
    attachments: Sequence[NewAttachment] = (),
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation_id, role=role, content=sealed(text), run_id=run_id
    )
    session.add(message)
    # In the message's own commit: a message is never seen without its files.
    for ordinal, one in enumerate(attachments):
        session.add(
            MessageAttachment(
                message_id=message.id,
                ordinal=ordinal,
                kind=one.kind,
                media_type=one.media_type,
                size=len(one.content),
                name=sealed(one.name),
                content=sealed_bytes(one.content),
            )
        )
    await session.exec(
        update(Conversation)
        .where(col(Conversation.id) == conversation_id)
        .values(updated_at=get_datetime_utc())
    )
    await session.commit()
    return message


async def attachments_of(
    session: AsyncSession, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[MessageAttachmentPublic]]:
    """What each message carried, without reading a byte of it (D142)."""
    if not message_ids:
        return {}
    rows = (
        await session.exec(
            select(MessageAttachment)
            .where(col(MessageAttachment.message_id).in_(message_ids))
            .order_by(col(MessageAttachment.ordinal))
            # SQLModel types the attribute as the value it holds; on the class it
            # is the column, which is what defer takes.
            .options(defer(cast("QueryableAttribute[bytes]", MessageAttachment.content)))
        )
    ).all()
    found: dict[uuid.UUID, list[MessageAttachmentPublic]] = {}
    for row in rows:
        found.setdefault(row.message_id, []).append(
            MessageAttachmentPublic(
                id=row.id,
                name=opened(row.name),
                kind="image" if row.kind == "image" else "text",
                media_type=row.media_type,
                size=row.size,
            )
        )
    return found


async def attachment_for_owner(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> MessageAttachment | None:
    """One file of somebody's own conversation; anybody else's is not found."""
    return (
        await session.exec(
            select(MessageAttachment)
            .join(
                ConversationMessage,
                col(ConversationMessage.id) == col(MessageAttachment.message_id),
            )
            .join(Conversation, col(Conversation.id) == col(ConversationMessage.conversation_id))
            .where(
                MessageAttachment.id == attachment_id,
                Conversation.id == conversation_id,
                Conversation.owner_id == owner_id,
            )
        )
    ).first()


async def active_run(
    session: AsyncSession, conversation_id: uuid.UUID
) -> AgentRun | None:
    return (
        await session.exec(
            select(AgentRun).where(
                AgentRun.conversation_id == conversation_id,
                col(AgentRun.status).in_(["running", "awaiting_answer"]),
            )
        )
    ).first()


async def has_answer(session: AsyncSession, conversation_id: uuid.UUID) -> bool:
    return (
        await session.exec(
            select(ConversationMessage.id).where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.role == "assistant",
            )
        )
    ).first() is not None


async def user_message_for_run(session: AsyncSession, run_id: uuid.UUID) -> str:
    message = (
        await session.exec(
            select(ConversationMessage).where(
                ConversationMessage.run_id == run_id,
                ConversationMessage.role == "user",
            )
        )
    ).first()
    return opened(message.content) if message is not None else ""


async def record_run(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
    model_key: str,
) -> AgentRun:
    run = AgentRun(
        conversation_id=conversation_id, owner_id=owner_id, model_key=model_key
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def finish_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: RunStatus,
    error: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> AgentRun | None:
    run = await session.get(AgentRun, run_id)
    if run is None:
        return None
    run.status = status
    run.error = None if error is None else error[:500]
    run.input_tokens = input_tokens
    run.output_tokens = output_tokens
    run.finished_at = get_datetime_utc()
    session.add(run)
    await session.commit()
    return run


async def start_step(
    session: AsyncSession, run_id: uuid.UUID, ordinal: int, kind: StepKind, title: str
) -> AgentStep:
    step = AgentStep(run_id=run_id, ordinal=ordinal, kind=kind, title=title)
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


async def running_tool_step(
    session: AsyncSession, run_id: uuid.UUID
) -> AgentStep | None:
    return (
        await session.exec(
            select(AgentStep)
            .where(
                AgentStep.run_id == run_id,
                AgentStep.kind == "tool",
                AgentStep.status == "running",
            )
            .order_by(col(AgentStep.ordinal).desc())
            .limit(1)
        )
    ).first()


async def last_step_ordinal(session: AsyncSession, run_id: uuid.UUID) -> int:
    value = (
        await session.exec(select(func.max(AgentStep.ordinal)).where(AgentStep.run_id == run_id))
    ).one()
    return int(value or 0)


async def pending_question(
    session: AsyncSession, run_id: uuid.UUID
) -> AgentQuestion | None:
    step = await running_tool_step(session, run_id)
    if step is None or not step.detail:
        return None
    return AgentQuestion.model_validate_json(opened(step.detail))


async def finish_step(
    session: AsyncSession,
    run_id: uuid.UUID,
    ordinal: int,
    *,
    status: StepStatus,
    detail: str | None = None,
) -> AgentStep | None:
    step = await session.get(AgentStep, (run_id, ordinal))
    if step is None:
        return None
    step.status = status
    step.finished_at = get_datetime_utc()
    if detail:
        step.detail = sealed(detail)
    session.add(step)
    await session.commit()
    return step


async def close_running_steps(
    session: AsyncSession, run_id: uuid.UUID, *, status: StepStatus
) -> list[AgentStep]:
    """The tool steps an ended run left open, ended with it (D137).

    A Stop, a timeout or a failure can cut a tool off mid-call, and the tool
    never reaches the line that finishes its step; nothing else would.
    """
    steps = (
        await session.exec(
            select(AgentStep).where(
                AgentStep.run_id == run_id,
                AgentStep.kind == "tool",
                AgentStep.status == "running",
            )
        )
    ).all()
    if not steps:
        return []
    moment = get_datetime_utc()
    for step in steps:
        step.status = status
        step.finished_at = moment
        session.add(step)
    await session.commit()
    return list(steps)


async def set_step_detail(
    session: AsyncSession, run_id: uuid.UUID, ordinal: int, detail: str
) -> AgentStep | None:
    step = await session.get(AgentStep, (run_id, ordinal))
    if step is None:
        return None
    step.detail = sealed(detail)
    session.add(step)
    await session.commit()
    return step


async def set_run_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: RunStatus,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> AgentRun | None:
    run = await session.get(AgentRun, run_id)
    if run is None:
        return None
    run.status = status
    run.finished_at = None
    if input_tokens is not None:
        run.input_tokens = input_tokens
    if output_tokens is not None:
        run.output_tokens = output_tokens
    session.add(run)
    await session.commit()
    return run


async def step_detail(
    session: AsyncSession, run_id: uuid.UUID, ordinal: int
) -> str:
    step = await session.get(AgentStep, (run_id, ordinal))
    return opened(step.detail) if step is not None and step.detail else ""


def step_public(step: AgentStep, *, with_detail: bool = True) -> AgentStepPublic:
    stored = opened(step.detail) if with_detail and step.detail else None
    detail = stored if step.kind == "thinking" else None
    substeps: list[str] = []
    if step.kind == "tool" and stored:
        try:
            value = json.loads(stored)
            if isinstance(value, dict) and isinstance(value.get("substeps"), list):
                substeps = [str(item) for item in value["substeps"]]
        except json.JSONDecodeError:
            pass
    return AgentStepPublic(
        ordinal=step.ordinal,
        kind=step.kind,  # type: ignore[arg-type]  # the column holds the union
        title=step.title,
        status=step.status,  # type: ignore[arg-type]  # the column holds the union
        detail=detail,
        substeps=substeps,
        started_at=step.started_at,
        finished_at=step.finished_at,
    )


async def run_public(
    session: AsyncSession, run: AgentRun, *, partial_answer: str | None = None
) -> AgentRunPublic:
    steps = (
        await session.exec(
            select(AgentStep)
            .where(AgentStep.run_id == run.id)
            .order_by(col(AgentStep.ordinal))
        )
    ).all()
    question = None
    if run.status == "awaiting_answer":
        question = await pending_question(session, run.id)
    return AgentRunPublic(
        id=run.id,
        conversation_id=run.conversation_id,
        status=run.status,  # type: ignore[arg-type]  # the column holds the union
        model_key=run.model_key,
        error=run.error,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        created_at=run.created_at,
        finished_at=run.finished_at,
        steps=[step_public(step) for step in steps],
        partial_answer=None if run.status in TERMINAL else partial_answer,
        question=question,
    )


async def conversation_public(
    session: AsyncSession,
    conversation: Conversation,
    partial_answers: dict[uuid.UUID, str],
) -> ConversationPublic:
    messages = (
        await session.exec(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(col(ConversationMessage.created_at))
        )
    ).all()
    carried = await attachments_of(session, [message.id for message in messages])
    runs = (
        await session.exec(
            select(AgentRun)
            .where(AgentRun.conversation_id == conversation.id)
            .order_by(col(AgentRun.created_at).desc())
            .limit(RECENT_RUNS)
        )
    ).all()
    return ConversationPublic(
        id=conversation.id,
        title=opened(conversation.title),
        title_is_custom=conversation.title_is_custom,
        model_key=conversation.model_key,
        auto_provider=chat_provider_of(conversation.auto_provider),
        change_policy=policy_of(conversation.change_policy),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessagePublic(
                id=message.id,
                role=message.role,  # type: ignore[arg-type]  # the column holds the union
                content=opened(message.content),
                attachments=carried.get(message.id, []),
                run_id=message.run_id,
                created_at=message.created_at,
            )
            for message in messages
        ],
        runs=[
            await run_public(session, run, partial_answer=partial_answers.get(run.id))
            for run in reversed(runs)
        ],
    )


async def recover_interrupted(session: AsyncSession) -> int:
    """At startup: an answer that was being written is not being written now.

    A pause for a person is left as it is: its state is in the checkpointer,
    and answering it continues the run (D137).
    """
    stranded = (
        await session.exec(select(AgentRun).where(AgentRun.status == "running"))
    ).all()
    if not stranded:
        return 0
    moment = datetime.now(UTC)
    for run in stranded:
        run.status = "interrupted"
        run.finished_at = moment
        session.add(run)
    await session.exec(
        update(AgentStep)
        .where(
            col(AgentStep.run_id).in_([run.id for run in stranded]),
            col(AgentStep.status) == "running",
        )
        .values(status="cancelled", finished_at=moment)
    )
    await session.commit()
    return len(stranded)
