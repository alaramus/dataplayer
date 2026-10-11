"""Kept lists of names: who may see and change them, and how the search asks one.

The worker writes them (`keeper.py`); this is everything the backend does with
them: the state a screen shows, the owner's switch, Refresh, the stale mark
(D216) and the one query a names cell is answered with (D215).
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, case, delete, false, func, not_, or_, update
from sqlalchemy.orm import Mapped
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import EnumeratesNames, ExtractsText
from app.adapters.registry import UnknownAdapterType, all_types
from app.adapters.registry import get as adapter_type_of
from app.connectors import crud
from app.connectors.models import Connector
from app.core.access import Access
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.search.keep import (
    DEFAULT_WINDOW,
    ContentsScopeState,
    KeepOverview,
    KeepState,
    KeepStatus,
    KeepUpdate,
    KeepWindow,
    SearchChunk,
    SearchContentFile,
    SearchContentScope,
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


def can_keep_contents(adapter_type: str) -> bool:
    """Whether its files' text can be kept too: it reads its names and its text (D217)."""
    try:
        driver = adapter_type_of(adapter_type).adapter_class
    except UnknownAdapterType:
        return False
    return issubclass(driver, EnumeratesNames) and issubclass(driver, ExtractsText)


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
    connector: Connector,
    access: Access,
    owner_email: str | None,
    row: SearchKeep | None,
    scopes: Sequence[SearchContentScope] = (),
) -> KeepState:
    return KeepState(
        contents_available=can_keep_contents(connector.adapter_type),
        contents=[
            ContentsScopeState(
                node_id=scope.node_id,
                files=scope.files,
                unread=scope.unread,
                read_at=scope.read_at,
                notice=scope.notice,
            )
            for scope in sorted(scopes, key=lambda one: one.node_id)
        ],
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
    scopes = await scopes_of(session, list(rows))
    return KeepOverview(
        lists=[
            state_of(
                connector, access, owner_email, rows[connector.id], scopes.get(connector.id, [])
            )
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
        # The text goes with the names it was read through (D217).
        await session.exec(delete(SearchName).where(col(SearchName.connector_id) == connector.id))
        await session.exec(
            delete(SearchContentScope).where(col(SearchContentScope.connector_id) == connector.id)
        )
        await session.exec(
            delete(SearchContentFile).where(col(SearchContentFile.connector_id) == connector.id)
        )
        await session.exec(delete(SearchChunk).where(col(SearchChunk.connector_id) == connector.id))
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
    # Some of its files' text is kept too, and answers a contents cell (D219).
    contents: bool = False


async def usable(
    session: AsyncSession, connector_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, KeptList]:
    """The lists these connections keep that may answer a names cell (D215).

    Written at least once, not stale, and younger than its window. Whether the
    connection is switched on and the words are long enough is the plan's.
    """
    now = get_datetime_utc()
    found: dict[uuid.UUID, KeptList] = {}
    rows = await _rows(session, connector_ids)
    scopes = await scopes_of(session, list(rows))
    for connector_id, row in rows.items():
        if row.kept_at is None or stale(row):
            continue
        if now - row.kept_at > timedelta(seconds=window_of(row)):
            continue
        found[connector_id] = KeptList(
            kept_at=row.kept_at,
            complete=row.kept_notice is None,
            notice=row.kept_notice,
            contents=any(scope.read_at is not None for scope in scopes.get(connector_id, [])),
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


async def scopes_of(
    session: AsyncSession, connector_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[SearchContentScope]]:
    if not connector_ids:
        return {}
    rows = await session.exec(
        select(SearchContentScope).where(
            col(SearchContentScope.connector_id).in_(list(connector_ids))
        )
    )
    found: dict[uuid.UUID, list[SearchContentScope]] = {}
    for scope in rows.all():
        found.setdefault(scope.connector_id, []).append(scope)
    return found


def under(node_id: str, scope: str) -> bool:
    """Whether a node lies in a scope: the whole connection, itself, or below it."""
    return scope == "" or node_id == scope or node_id.startswith(f"{scope}/")


def outside(column: Mapped[str], scopes: Sequence[str]) -> ColumnElement[bool]:
    """A node id in none of these scopes, as a condition."""
    if "" in scopes:
        return false()
    return not_(
        or_(
            false(),
            *(
                or_(column == scope, column.startswith(f"{scope}/", autoescape=True))
                for scope in scopes
            ),
        )
    )


async def add_contents(session: AsyncSession, row: SearchKeep, node_id: str) -> None:
    """Keep the text below this folder too; the worker reads it at once (D217)."""
    if await session.get(SearchContentScope, (row.connector_id, node_id)) is None:
        session.add(SearchContentScope(connector_id=row.connector_id, node_id=node_id))
    row.refresh_asked_at = get_datetime_utc()
    session.add(row)
    await session.commit()


async def remove_contents(session: AsyncSession, connector_id: uuid.UUID, node_id: str) -> None:
    """Stop keeping a folder's text; what no other scope covers is deleted with it."""
    scope = await session.get(SearchContentScope, (connector_id, node_id))
    if scope is not None:
        await session.delete(scope)
        await session.flush()
    left = [one.node_id for one in (await scopes_of(session, [connector_id])).get(connector_id, [])]
    await session.exec(
        delete(SearchContentFile).where(
            col(SearchContentFile.connector_id) == connector_id,
            outside(col(SearchContentFile.node_id), left),
        )
    )
    await session.exec(
        delete(SearchChunk).where(
            col(SearchChunk.connector_id) == connector_id,
            outside(col(SearchChunk.node_id), left),
        )
    )
    await session.commit()


async def find_text(
    session: AsyncSession,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    words: Sequence[str],
    limit: int,
) -> list[SearchChunk]:
    """Chunks holding every word, the standing inside the query (D199, D219).

    A chunk holds many lines, so one found may hold the words on different
    lines; the caller keeps only a line that holds them all, the live rule.
    """
    folded = col(SearchChunk.folded)
    statement = (
        select(SearchChunk)
        .join(Connector, col(Connector.id) == col(SearchChunk.connector_id))
        .where(
            col(SearchChunk.connector_id) == connector_id,
            col(Connector.enabled).is_(True),
            crud.visible_to(user_id),
            *(folded.like(f"%{_escaped(word)}%", escape="\\") for word in words),
        )
        .order_by(col(SearchChunk.node_id), col(SearchChunk.seq))
        .limit(limit)
    )
    return list((await session.exec(statement)).all())


async def nodes_of(
    session: AsyncSession, connector_id: uuid.UUID, node_ids: Sequence[str]
) -> dict[str, SearchName]:
    """The kept names of these nodes, for the hits their text was found in."""
    if not node_ids:
        return {}
    rows = await session.exec(
        select(SearchName).where(
            col(SearchName.connector_id) == connector_id,
            col(SearchName.node_id).in_(list(node_ids)),
        )
    )
    return {row.node_id: row for row in rows.all()}


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
