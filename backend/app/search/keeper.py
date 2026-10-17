"""The process that reads kept lists of names (D213, D214).

`python -m app.search.keeper`, the compose service `search-keeper`. Not the
backend: walking one SSH tree of a hundred thousand entries must not share the
one process every request runs in (D124). The backend learns what happened from
the rows this writes, and the screens poll them.
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, func, not_, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.protocol import AdapterError, EnumeratesNames
from app.adapters.search import KeptName, SearchBounds
from app.connectors.access import context_for
from app.connectors.models import Connector
from app.connectors.service import build_adapter, merge_options
from app.core import logs
from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.core.logs import record_failure
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say
from app.search.embedder import Embedder
from app.search.keep import SearchKeep, SearchName
from app.search.kept import reading, stale, window_of
from app.search.kept_meaning import (
    embed_missing,
    keep_meaning,
    name_passages,
    prune,
    ready_model,
    waiting_for_vectors,
)
from app.search.kept_text import keep_text

logger = logging.getLogger(__name__)

TICK_SECONDS = 5.0
# How often, in ticks, what the model has not read yet is looked for.
MEANING_TICKS = 12
# Passes at once. A pass is mostly waiting on somebody's server, but two
# remote trees walked at once already hold two worker threads.
PASSES = 2
# How long a failed pass waits before it is tried again, at most.
RETRY_SECONDS = 600

# No request starts a pass, so what it writes is English (D226); the screens
# word a sentence without parameters as they read it.
_LOCKED = N_(
    "The SSH key's passphrase is held only while its owner is signed in, "
    "so the names cannot be read in the background"
)


def due(row: SearchKeep, now: datetime) -> bool:
    """Whether a list should be read now (D214).

    Never read, renamed in DataPlayer, asked for, or past half its window — so
    a list that keeps passing never expires. A failed pass is tried again
    after a while rather than on every tick.
    """
    if reading(row):
        return False
    if row.refresh_asked_at is not None:
        return True
    half = timedelta(seconds=window_of(row) / 2)
    if row.outcome == "failed" and row.pass_ended_at is not None:
        return now - row.pass_ended_at >= min(half, timedelta(seconds=RETRY_SECONDS))
    if stale(row):
        return True
    if row.kept_at is None:
        return row.pass_started_at is None
    return now - row.kept_at >= half


async def due_now(session: AsyncSession) -> list[tuple[SearchKeep, Connector]]:
    """Every list due, of a switched-on connection, the longest waiting first."""
    rows = await session.exec(
        select(SearchKeep, Connector)
        .join(Connector, col(Connector.id) == col(SearchKeep.connector_id))
        .where(col(Connector.enabled).is_(True))
    )
    now = get_datetime_utc()
    found = [(row, connector) for row, connector in rows.all() if due(row, now)]
    found.sort(key=lambda pair: pair[0].kept_at or datetime.min.replace(tzinfo=now.tzinfo))
    return found


async def run_pass(connector: Connector) -> None:
    """One pass over one connection, its outcome written whatever happens."""
    started = get_datetime_utc()
    pass_id = uuid.uuid4()
    async with async_session_maker() as session:
        await session.exec(
            update(SearchKeep)
            .where(col(SearchKeep.connector_id) == connector.id)
            .values(pass_started_at=started, pass_ended_at=None, refresh_asked_at=None)
        )
        await session.commit()
    try:
        adapter = _adapter_of(connector)
        async with asyncio.timeout(settings.SEARCH_KEPT_PASS_SECONDS + 30):
            notice, unread = await _read(adapter, connector, pass_id)
    except AdapterError as failure:
        message = _LOCKED if failure.error_kind == "locked" else failure.message
        await _ended(connector.id, outcome="failed", notice=message, error_kind=failure.error_kind)
        return
    except Exception as failure:
        ref = record_failure(logger, "A pass over a connection's names failed", failure)
        await _ended(
            connector.id,
            outcome="failed",
            notice=say("The names could not be read (ref {ref})", ref=ref),
            error_kind="unknown",
        )
        return
    async with async_session_maker() as session:
        if notice is None and "" not in unread:
            await session.exec(
                delete(SearchName).where(
                    col(SearchName.connector_id) == connector.id,
                    col(SearchName.pass_id) != pass_id,
                    *_outside(unread),
                )
            )
        names = (
            await session.exec(
                select(func.count())
                .select_from(SearchName)
                .where(col(SearchName.connector_id) == connector.id)
            )
        ).one()
        await session.commit()
    if notice is None and unread:
        notice = say(
            "{count} folders could not be read; what was kept in them stays",
            count=f"{len(unread):,}",
        )
    # The text below the chosen folders, from the names just kept (D218). Its
    # failure is said on its scopes and never undoes the names.
    try:
        async with asyncio.timeout(settings.SEARCH_KEPT_PASS_SECONDS + 30):
            await keep_text(connector.id, adapter)
    except Exception as failure:
        record_failure(logger, "A pass over a connection's text failed", failure)
    # Then what the model reads of both (D221); without a model, nothing.
    try:
        await keep_meaning(connector.id)
    except Exception as failure:
        record_failure(logger, "A pass over a connection's meaning failed", failure)
    await _ended(
        connector.id,
        outcome="kept" if notice is None else "partial",
        notice=notice,
        kept=(started, names),
    )


def _adapter_of(connector: Connector) -> object:
    return build_adapter(
        registry.get(connector.adapter_type),
        merge_options(connector.config, connector.secrets),
        # The owner's credentials, and no pool: a connection of its own (D127).
        context_for(connector.owner_id),
    )


async def _read(
    adapter: object, connector: Connector, pass_id: uuid.UUID
) -> tuple[str | None, list[str]]:
    """Every batch written as it arrives; the source's notice and what it could not read."""
    if not isinstance(adapter, EnumeratesNames):
        raise AdapterError("config", say("This kind of source cannot keep its names"))
    bounds = SearchBounds.within(settings.SEARCH_KEPT_PASS_SECONDS)
    notice: str | None = None
    unread: list[str] = []
    async for batch in adapter.enumerate_names(settings.SEARCH_KEPT_MAX_NAMES, bounds):
        unread.extend(batch.unread)
        notice = notice or batch.notice
        if batch.names:
            async with async_session_maker() as session:
                await write(session, connector.id, pass_id, batch.names)
    return notice, unread


async def write(
    session: AsyncSession, connector_id: uuid.UUID, pass_id: uuid.UUID, names: Sequence[KeptName]
) -> None:
    """Names added or refreshed, each marked as seen by this pass."""
    rows = {
        one.node.id: {
            "connector_id": connector_id,
            "node_id": one.node.id,
            "parent_id": one.parent_id,
            "scope": one.scope,
            "name": (name := one.full_name or one.node.name),
            # Folded once, by the rule's own fold (D215).
            "folded": name.casefold(),
            "kind": one.node.kind,
            "location": one.location,
            "node": one.node.model_dump(mode="json"),
            "ancestors": None
            if one.ancestors is None
            else [ancestor.model_dump(mode="json") for ancestor in one.ancestors],
            "pass_id": pass_id,
        }
        for one in names
    }
    statement = insert(SearchName).values(list(rows.values()))
    excluded = statement.excluded
    await session.exec(
        statement.on_conflict_do_update(
            index_elements=["connector_id", "node_id"],
            set_={
                field: excluded[field]
                for field in (
                    "parent_id",
                    "scope",
                    "name",
                    "folded",
                    "kind",
                    "location",
                    "node",
                    "ancestors",
                    "pass_id",
                )
            },
        )
    )
    await session.commit()


def _outside(unread: Sequence[str]) -> list[ColumnElement[bool]]:
    """Not under a scope the source could not read: what is there stays."""
    scope = col(SearchName.scope)
    return [
        not_(or_(scope == one, scope.startswith(f"{one}/", autoescape=True)))
        for one in unread
    ]


async def _ended(
    connector_id: uuid.UUID,
    *,
    outcome: str,
    notice: str | None,
    error_kind: str | None = None,
    kept: tuple[datetime, int] | None = None,
) -> None:
    values: dict[str, object] = {
        "pass_ended_at": get_datetime_utc(),
        "outcome": outcome,
        "notice": notice,
        "error_kind": error_kind,
    }
    if kept is not None:
        started, names = kept
        values.update(
            kept_at=values["pass_ended_at"],
            kept_started_at=started,
            kept_notice=notice,
            names=names,
        )
    async with async_session_maker() as session:
        await session.exec(
            update(SearchKeep)
            .where(col(SearchKeep.connector_id) == connector_id)
            .values(**values)
        )
        await session.commit()


async def settle_interrupted() -> None:
    """A pass this process was running when it stopped ended there."""
    async with async_session_maker() as session:
        await session.exec(
            update(SearchKeep)
            .where(
                and_(
                    col(SearchKeep.pass_started_at).is_not(None),
                    or_(
                        col(SearchKeep.pass_ended_at).is_(None),
                        col(SearchKeep.pass_ended_at) < col(SearchKeep.pass_started_at),
                    ),
                )
            )
            .values(
                pass_ended_at=get_datetime_utc(),
                outcome="failed",
                notice=N_("The pass was interrupted"),
                error_kind="unknown",
            )
        )
        await session.commit()


async def _meaning_now(running: dict[uuid.UUID, asyncio.Task[None]]) -> None:
    """Vectors for lists read before the model started, and old ones pruned (D221)."""
    ready = await ready_model()
    if ready is None:
        return
    model, name = ready
    for connector_id in await waiting_for_vectors(name):
        if len(running) >= PASSES:
            return
        if connector_id not in running:
            running[connector_id] = asyncio.create_task(_embed_only(connector_id, model, name))
    await prune(name)


async def _embed_only(connector_id: uuid.UUID, model: Embedder, name: str) -> None:
    try:
        await name_passages(connector_id)
        await embed_missing(connector_id, model, name)
    except Exception as failure:
        record_failure(logger, "A connection's passages could not be embedded", failure)


async def serve() -> None:
    await settle_interrupted()
    running: dict[uuid.UUID, asyncio.Task[None]] = {}
    logger.info("Keeping names for search")
    ticks = 0
    while True:
        ticks += 1
        if ticks % MEANING_TICKS == 0:
            try:
                await _meaning_now(running)
            except Exception as failure:
                record_failure(logger, "The vectors could not be looked after", failure)
        try:
            async with async_session_maker() as session:
                found = await due_now(session)
            for _, connector in found:
                if len(running) >= PASSES:
                    break
                if connector.id in running:
                    continue
                running[connector.id] = asyncio.create_task(run_pass(connector))
            for key in [key for key, task in running.items() if task.done()]:
                running.pop(key)
        except Exception as failure:
            record_failure(logger, "The kept lists could not be read", failure)
        await asyncio.sleep(TICK_SECONDS)


def main() -> None:
    logs.configure("search-keeper")
    asyncio.run(serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
