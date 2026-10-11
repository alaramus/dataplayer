"""Kept lists of names: who may see and change them, and how the search asks one.

The worker writes them (`keeper.py`); this is everything the backend does with
them: the state a screen shows, the owner's switch, Refresh, the stale mark
(D216) and the one query a names cell is answered with (D215).
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import EnumeratesNames
from app.adapters.registry import UnknownAdapterType, all_types
from app.adapters.registry import get as adapter_type_of
from app.connectors import crud
from app.connectors.models import Connector
from app.core.access import Access
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.search.keep import (
    DEFAULT_WINDOW,
    KeepOverview,
    KeepState,
    KeepStatus,
    KeepUpdate,
    KeepWindow,
    SearchKeep,
    SearchName,
)
from app.users.models import User

# Trigrams serve a word of three characters or more; an answer of only
# shorter words is asked live (D215).
TRIGRAM = 3

_WINDOWS: tuple[KeepWindow, ...] = (3600, 21600, 86400, 604800)


def can_keep(adapter_type: str) -> bool:
    """Whether a source of this type can have its names kept (D213)."""
    try:
        driver = adapter_type_of(adapter_type).adapter_class
    except UnknownAdapterType:
        return False
    return issubclass(driver, EnumeratesNames)


def keeping_types() -> list[str]:
    return sorted(one.name for one in all_types() if issubclass(one.adapter_class, EnumeratesNames))


def window_of(row: SearchKeep) -> KeepWindow:
    seconds = row.window_seconds
    return seconds if seconds in _WINDOWS else DEFAULT_WINDOW


def reading(row: SearchKeep) -> bool:
    started, ended = row.pass_started_at, row.pass_ended_at
    return started is not None and (ended is None or ended < started)


def stale(row: SearchKeep) -> bool:
    """Something was renamed after the pass that wrote the list began."""
    if row.stale_at is None:
        return False
    return row.kept_started_at is None or row.stale_at >= row.kept_started_at


def status_of(row: SearchKeep | None) -> KeepStatus:
    if row is None:
        return "off"
    if reading(row):
        return "reading"
    if row.outcome in ("kept", "partial", "failed"):
        return row.outcome  # type: ignore[return-value]  # the membership test narrows it; mypy keeps it str
    return "waiting"


def state_of(
    connector: Connector, access: Access, owner_email: str | None, row: SearchKeep | None
) -> KeepState:
    return KeepState(
        connector_id=connector.id,
        name=connector.name,
        adapter_type=connector.adapter_type,
        owner_email=owner_email,
        may_change=access == "own",
        available=can_keep(connector.adapter_type),
        status=status_of(row),
        window_seconds=DEFAULT_WINDOW if row is None else window_of(row),
        names=0 if row is None else row.names,
        kept_at=None if row is None else row.kept_at,
        pass_started_at=None if row is None else row.pass_started_at,
        pass_ended_at=None if row is None else row.pass_ended_at,
        refresh_asked=row is not None and row.refresh_asked_at is not None,
        stale=row is not None and stale(row),
        notice=None if row is None else row.notice,
        error_kind=None if row is None else row.error_kind,
    )


async def overview(session: AsyncSession, user: User) -> KeepOverview:
    """Every kept list on a connection the person can see, by connection name."""
    standings = await crud.visible_with_standing(session, user=user, limit=1000)
    rows = await _rows(session, [connector.id for connector, _, _ in standings])
    return KeepOverview(
        lists=[
            state_of(connector, access, owner_email, rows[connector.id])
            for connector, access, owner_email in standings
            if connector.id in rows
        ],
        types=keeping_types(),
    )


async def row_of(session: AsyncSession, connector_id: uuid.UUID) -> SearchKeep | None:
    return await session.get(SearchKeep, connector_id)


async def change(
    session: AsyncSession, connector: Connector, body: KeepUpdate
) -> SearchKeep | None:
    """The owner's switch. Off deletes the names in the same transaction (D212)."""
    row = await session.get(SearchKeep, connector.id)
    if not body.keep:
        await session.exec(
            delete(SearchName).where(col(SearchName.connector_id) == connector.id)
        )
        if row is not None:
            await session.delete(row)
        await session.commit()
        return None
    now = get_datetime_utc()
    if row is None:
        row = SearchKeep(connector_id=connector.id, changed_at=now)
    row.window_seconds = body.window_seconds
    row.changed_at = now
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def ask_refresh(session: AsyncSession, row: SearchKeep) -> SearchKeep:
    row.refresh_asked_at = get_datetime_utc()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@dataclass(frozen=True)
class KeptList:
    """A list the search may answer from, and how good it is."""

    kept_at: datetime
    complete: bool
    notice: str | None


async def usable(
    session: AsyncSession, connector_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, KeptList]:
    """The lists these connections keep that may answer a names cell (D215).

    Written at least once, not stale, and younger than its window. Whether the
    connection is switched on and the words are long enough is the plan's.
    """
    now = get_datetime_utc()
    found: dict[uuid.UUID, KeptList] = {}
    for connector_id, row in (await _rows(session, connector_ids)).items():
        if row.kept_at is None or stale(row):
            continue
        if now - row.kept_at > timedelta(seconds=window_of(row)):
            continue
        found[connector_id] = KeptList(
            kept_at=row.kept_at, complete=row.kept_notice is None, notice=row.kept_notice
        )
    return found


def answers_kept(words: Sequence[str]) -> bool:
    """Whether a trigram index can serve these words: one of three or more."""
    return any(len(word) >= TRIGRAM for word in words)


async def find(
    session: AsyncSession,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    words: Sequence[str],
    limit: int,
) -> list[SearchName]:
    """Names holding every word, best first, one more than the limit.

    The person's standing and the connection being switched on are inside the
    query (D199): nothing of a revoked grant or a switched-off connection comes
    back, whatever the plan thought. Exact and prefix names first, then the
    shortest; the engine classes them again by the rule.
    """
    folded = col(SearchName.folded)
    statement = (
        select(SearchName)
        .join(Connector, col(Connector.id) == col(SearchName.connector_id))
        .where(
            col(SearchName.connector_id) == connector_id,
            col(Connector.enabled).is_(True),
            crud.visible_to(user_id),
            *(folded.like(f"%{_escaped(word)}%", escape="\\") for word in words),
        )
        .order_by(
            case((folded == " ".join(words), 0), else_=1),
            case((folded.startswith(words[0], autoescape=True), 0), else_=1),
            func.length(folded),
            folded,
            col(SearchName.node_id),
        )
        .limit(limit + 1)
    )
    return list((await session.exec(statement)).all())


def _escaped(word: str) -> str:
    """A word as a `LIKE` takes it literally: `%` and `_` are characters (D2c)."""
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def mark_stale(session: AsyncSession, connector_id: uuid.UUID) -> None:
    """Something in DataPlayer renamed what the list holds (D216)."""
    await session.exec(
        update(SearchKeep)
        .where(col(SearchKeep.connector_id) == connector_id)
        .values(stale_at=get_datetime_utc())
    )
    await session.commit()


async def names_changed(connector_id: uuid.UUID) -> None:
    """`NamesChanged`, as the application is assembled with it (D216)."""
    async with async_session_maker() as session:
        await mark_stale(session, connector_id)


async def _rows(
    session: AsyncSession, connector_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, SearchKeep]:
    if not connector_ids:
        return {}
    rows = await session.exec(
        select(SearchKeep).where(col(SearchKeep.connector_id).in_(list(connector_ids)))
    )
    return {row.connector_id: row for row in rows.all()}
