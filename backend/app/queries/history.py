"""What was run, kept for as long as its owner wants it kept.

D63: history is a view of accepted immutable runs, not a second collection of
query text. A run is already the record; this is how it is listed, searched,
deleted and expired.

Retention is the user's choice and the default is deliberately not "for ever":
ninety days or a thousand runs, whichever comes first.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Field, SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.queries.content import preview_of, text_of
from app.queries.runs import TERMINAL, ExecutionRun

# What a person may choose. A closed set rather than a number, because these
# are the answers the interface offers and an arbitrary one would have to be
# explained (D63).
RetentionDays = Literal[0, 7, 30, 90]


class QueryRetention(SQLModel, table=True):
    """One person's answer to "how long should this be kept".

    A row only exists once somebody has chosen; everybody else has the default,
    which is what `retention_of` answers.
    """

    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    days: int = Field(default=90)


class RetentionSettings(BaseModel):
    """How long runs are kept, and the ceiling that applies whatever is chosen."""

    days: RetentionDays
    max_runs: int


class RetentionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: RetentionDays


class RunSummary(BaseModel):
    """One run as history lists it.

    The first line of what ran, decrypted for this answer and not stored: a
    list of "a run" tells nobody which run it was.
    """

    id: uuid.UUID
    connector_id: uuid.UUID | None
    document_id: uuid.UUID | None
    status: str
    scope: str
    statement_count: int
    preview: str
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class RunsPublic(BaseModel):
    data: list[RunSummary]
    count: int


class DeleteSelected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["selected"]
    ids: list[uuid.UUID] = PydanticField(min_length=1, max_length=500)


class DeleteOlderThan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["older"]
    days: int = PydanticField(ge=0, le=3650)


class DeleteEverything(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["all"]


# One, several, older than a day, or the lot — and nothing else. Discriminated,
# so "delete everything" cannot arrive by leaving a field out.
RunDeletion = Annotated[
    DeleteSelected | DeleteOlderThan | DeleteEverything,
    PydanticField(discriminator="kind"),
]


async def retention_of(session: AsyncSession, user_id: uuid.UUID) -> RetentionSettings:
    chosen = await session.get(QueryRetention, user_id)
    days = settings.QUERY_HISTORY_DEFAULT_DAYS if chosen is None else chosen.days
    return RetentionSettings(
        days=days,  # type: ignore[arg-type]  # the column only ever holds the union
        max_runs=settings.QUERY_HISTORY_MAX_RUNS,
    )


async def choose_retention(
    session: AsyncSession, user_id: uuid.UUID, days: RetentionDays
) -> RetentionSettings:
    chosen = await session.get(QueryRetention, user_id)
    if chosen is None:
        chosen = QueryRetention(user_id=user_id, days=days)
    else:
        chosen.days = days
    session.add(chosen)
    await session.commit()
    return await retention_of(session, user_id)


def summarise(run: ExecutionRun, text: str) -> RunSummary:
    duration: int | None = None
    if run.started_at is not None and run.finished_at is not None:
        duration = int((run.finished_at - run.started_at).total_seconds() * 1000)
    return RunSummary(
        id=run.id,
        connector_id=run.connector_id,
        document_id=run.document_id,
        status=run.status,
        scope=run.scope,
        statement_count=run.statement_count,
        preview=preview_of(text),
        error=run.error,
        created_at=run.created_at,
        finished_at=run.finished_at,
        duration_ms=duration,
    )


async def delete(
    session: AsyncSession, user_id: uuid.UUID, request: RunDeletion
) -> int:
    """Remove history, by the request's own shape.

    There is no hidden copy afterwards. An audit product would need its own
    disclosure and its own retention decision (D63).
    """
    # Only what has finished: a run still going is not history yet, and
    # deleting its row would leave a task writing to nothing.
    condition: ColumnElement[bool] = (col(ExecutionRun.owner_id) == user_id) & col(
        ExecutionRun.status
    ).in_(sorted(TERMINAL))
    if isinstance(request, DeleteSelected):
        condition = condition & col(ExecutionRun.id).in_(request.ids)
    elif isinstance(request, DeleteOlderThan):
        deadline = datetime.now(UTC) - timedelta(days=request.days)
        condition = condition & (col(ExecutionRun.created_at) < deadline)
    doomed = (await session.exec(select(ExecutionRun).where(condition))).all()
    for run in doomed:
        await session.delete(run)
    if doomed:
        await session.commit()
    return len(doomed)


async def sweep(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Enforce each person's retention, and the ceiling above it.

    Idempotent and cheap, so it runs beside the Trash sweep on the same timer.
    A user who chose no retention keeps a run only until it is over.
    """
    moment = now or datetime.now(UTC)
    owners = (
        await session.exec(
            select(ExecutionRun.owner_id).distinct()
        )
    ).all()
    removed = 0
    for owner_id in owners:
        retention = await retention_of(session, owner_id)
        removed += await _expire_for(session, owner_id, retention, moment)
    return removed


async def _expire_for(
    session: AsyncSession,
    owner_id: uuid.UUID,
    retention: RetentionSettings,
    moment: datetime,
) -> int:
    finished = col(ExecutionRun.status).in_(sorted(TERMINAL))
    mine = col(ExecutionRun.owner_id) == owner_id
    if retention.days == 0:
        # No retention: the row lasts through terminal publication and no
        # longer. What the run produced expires with the result store.
        return await _remove(session, mine & finished)

    deadline = moment - timedelta(days=retention.days)
    removed = await _remove(
        session, mine & finished & (col(ExecutionRun.created_at) < deadline)
    )
    kept = (
        await session.exec(
            select(func.count()).select_from(ExecutionRun).where(mine & finished)
        )
    ).one()
    if kept <= retention.max_runs:
        return removed
    over = (
        await session.exec(
            select(ExecutionRun)
            .where(mine & finished)
            .order_by(col(ExecutionRun.created_at).desc())
            .offset(retention.max_runs)
        )
    ).all()
    for run in over:
        await session.delete(run)
    if over:
        await session.commit()
    return removed + len(over)


async def _remove(session: AsyncSession, condition: ColumnElement[bool]) -> int:
    doomed = (await session.exec(select(ExecutionRun).where(condition))).all()
    for run in doomed:
        await session.delete(run)
    if doomed:
        await session.commit()
    return len(doomed)


async def list_for(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    connector_id: uuid.UUID | None = None,
    search: str = "",
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ExecutionRun], int]:
    """This person's runs, newest first.

    A search cannot be a database one: the text is ciphertext. The newest
    QUERY_HISTORY_SEARCH_MAX are read and matched in memory, no index is built
    and the search text is neither stored nor logged (D63).
    """
    condition = col(ExecutionRun.owner_id) == owner_id
    if document_id is not None:
        condition = condition & (col(ExecutionRun.document_id) == document_id)
    if connector_id is not None:
        condition = condition & (col(ExecutionRun.connector_id) == connector_id)
    ordered = (
        select(ExecutionRun)
        .where(condition)
        .order_by(col(ExecutionRun.created_at).desc(), col(ExecutionRun.id))
    )
    if not search:
        count = (
            await session.exec(
                select(func.count()).select_from(ExecutionRun).where(condition)
            )
        ).one()
        rows = (await session.exec(ordered.offset(skip).limit(limit))).all()
        return list(rows), count

    lowered = search.casefold()
    candidates = (
        await session.exec(ordered.limit(settings.QUERY_HISTORY_SEARCH_MAX))
    ).all()
    found = [run for run in candidates if lowered in text_of(run).casefold()]
    return found[skip : skip + limit], len(found)

