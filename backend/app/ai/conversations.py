"""The transcript as rows: conversations, what was said, and how each answer ran.

Database access only, and the one place a stored row becomes what the API
sends. Somebody else's conversation is not found rather than refused, the rule
connections and jobs follow (D33, D81).
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import col, delete, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.content import opened, sealed
from app.ai.models import (
    MAX_TITLE_CHARS,
    TERMINAL,
    AgentQuestion,
    AgentRun,
    AgentRunPublic,
    AgentStep,
    AgentStepPublic,
    Conversation,
    ConversationMessage,
    ConversationMessagePublic,
    ConversationPublic,
    ConversationsPublic,
    ConversationSummary,
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
    session: AsyncSession, owner_id: uuid.UUID, *, skip: int, limit: int
) -> ConversationsPublic:
    count = (
        await session.exec(
            select(func.count()).select_from(Conversation).where(Conversation.owner_id == owner_id)
        )
    ).one()
    rows = (
        await session.exec(
            select(Conversation)
            .where(Conversation.owner_id == owner_id)
            .order_by(col(Conversation.updated_at).desc())
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
            ConversationSummary(
                id=row.id,
                title=opened(row.title),
                updated_at=row.updated_at,
                active=row.id in active,
                waiting=row.id in waiting,
            )
            for row in rows
        ],
        count=count,
    )


async def rename(
    session: AsyncSession, conversation: Conversation, title: str
) -> Conversation:
    conversation.title = sealed(title)
    conversation.title_is_custom = True
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


async def ids_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.exec(
                select(Conversation.id).where(Conversation.owner_id == owner_id)
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
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation_id, role=role, content=sealed(text), run_id=run_id
    )
    session.add(message)
    await session.exec(
        update(Conversation)
        .where(col(Conversation.id) == conversation_id)
        .values(updated_at=get_datetime_utc())
    )
    await session.commit()
    return message


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
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessagePublic(
                id=message.id,
                role=message.role,  # type: ignore[arg-type]  # the column holds the union
                content=opened(message.content),
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
