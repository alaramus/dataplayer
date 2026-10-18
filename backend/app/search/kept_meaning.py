"""Vectors for what a connection keeps: its names and its files' text (D221).

The keeper's last step of a pass, and its own when the model starts after the
lists were read. A passage is embedded once per text and model: a vector is
kept under the text's digest, so a file read again unchanged, or the same name
in two connections, costs nothing more. A new model's vectors are made beside
the old ones, which go once every passage has one of the new.
"""

import hashlib
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import and_, delete, exists, func, not_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import Exists
from sqlmodel import col, select

from app.adapters.search import SearchBounds
from app.core.config import settings
from app.core.db import async_session_maker
from app.search.embedder import Embedder, embedder
from app.search.keep import SearchKeep, SearchName, SearchPassage, SearchVector

logger = logging.getLogger(__name__)

# Passages sent to the model at once.
BATCH = 32


def _name_text(name: str, location: str) -> str:
    """A name as the model reads it: with where it is, which says what it is."""
    return f"{name} ({location})" if location else name


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def ready_model() -> tuple[Embedder, str] | None:
    """The model and its name, when one answers and keeps text on this server.

    An embedder that sends text out is not used: passing a connection's names to
    one is a transfer its owner decides (D135), and that is not built.
    """
    model = embedder()
    if model is None or model.sends_out:
        return None
    info = await model.info()
    return None if info is None else (model, info.model)


async def keep_meaning(connector_id: uuid.UUID) -> None:
    """Passages for the names just kept, then a vector for every one missing."""
    ready = await ready_model()
    if ready is None:
        return
    await name_passages(connector_id)
    await embed_missing(connector_id, *ready)


async def name_passages(connector_id: uuid.UUID) -> None:
    """One passage per kept name; a name gone takes its passage."""
    async with async_session_maker() as session:
        names = (
            await session.exec(
                select(col(SearchName.node_id), col(SearchName.name), col(SearchName.location)).where(
                    col(SearchName.connector_id) == connector_id
                )
            )
        ).all()
        wanted = {
            node_id: _name_text(name, location) for node_id, name, location in names
        }
        kept = await session.exec(
            select(col(SearchPassage.node_id), col(SearchPassage.digest)).where(
                col(SearchPassage.connector_id) == connector_id,
                col(SearchPassage.kind) == "name",
            )
        )
        have: dict[str, str] = {str(row[0]): str(row[1]) for row in kept.all()}
        gone = [node_id for node_id in have if node_id not in wanted]
        changed = {
            node_id: text
            for node_id, text in wanted.items()
            if have.get(node_id) != _digest(text)
        }
        for start in range(0, len(gone), 1000):
            await session.exec(
                delete(SearchPassage).where(
                    col(SearchPassage.connector_id) == connector_id,
                    col(SearchPassage.kind) == "name",
                    col(SearchPassage.node_id).in_(gone[start : start + 1000]),
                )
            )
        rows = [
            {
                "connector_id": connector_id,
                "kind": "name",
                "node_id": node_id,
                "seq": 0,
                "line": None,
                "text": text,
                "digest": _digest(text),
            }
            for node_id, text in changed.items()
        ]
        for start in range(0, len(rows), 1000):
            statement = insert(SearchPassage).values(rows[start : start + 1000])
            await session.exec(
                statement.on_conflict_do_update(
                    index_elements=["connector_id", "kind", "node_id", "seq"],
                    set_={"text": statement.excluded.text, "digest": statement.excluded.digest},
                )
            )
        await session.commit()


async def embed_missing(connector_id: uuid.UUID, model: Embedder, name: str) -> int:
    """A vector for every passage of this connection without one, within the pass's clock."""
    bounds = SearchBounds.within(settings.SEARCH_KEPT_PASS_SECONDS)
    made = 0
    while not bounds.over():
        async with async_session_maker() as session:
            batch = (
                await session.exec(
                    select(col(SearchPassage.digest), func.min(col(SearchPassage.text)))
                    .where(
                        col(SearchPassage.connector_id) == connector_id,
                        not_(_has_vector(name)),
                    )
                    .group_by(col(SearchPassage.digest))
                    .limit(BATCH)
                )
            ).all()
        if not batch:
            break
        vectors = await model.passages([text for _, text in batch])
        await _store(name, [digest for digest, _ in batch], vectors)
        made += len(batch)
    return made


def _has_vector(name: str) -> Exists:
    return exists().where(
        and_(col(SearchVector.digest) == col(SearchPassage.digest), col(SearchVector.model) == name)
    )


async def _store(name: str, digests: Sequence[str], vectors: Sequence[list[float]]) -> None:
    async with async_session_maker() as session:
        statement = insert(SearchVector).values(
            [
                {"digest": digest, "model": name, "embedding": vector}
                for digest, vector in zip(digests, vectors, strict=True)
            ]
        )
        await session.exec(statement.on_conflict_do_nothing())
        await session.commit()


async def waiting_for_vectors(name: str, limit: int = 20) -> list[uuid.UUID]:
    """Connections the model has not read all of: it started after their lists
    were read, so their names have no passages yet, or some passages no vector."""
    async with async_session_maker() as session:
        unread = await session.exec(
            select(col(SearchPassage.connector_id))
            .where(not_(_has_vector(name)))
            .group_by(col(SearchPassage.connector_id))
            .limit(limit)
        )
        found: list[uuid.UUID] = list(unread.all())
        unnamed = await session.exec(
            select(col(SearchKeep.connector_id))
            .where(
                col(SearchKeep.kept_at).is_not(None),
                not_(
                    exists().where(
                        and_(
                            col(SearchPassage.connector_id) == col(SearchKeep.connector_id),
                            col(SearchPassage.kind) == "name",
                        )
                    )
                ),
            )
            .limit(limit)
        )
        found.extend(one for one in unnamed.all() if one not in found)
        return found[:limit]


async def prune(name: str) -> None:
    """Vectors no passage has any more, and another model's once this one's are whole."""
    async with async_session_maker() as session:
        await session.exec(
            delete(SearchVector).where(
                not_(exists().where(col(SearchPassage.digest) == col(SearchVector.digest)))
            )
        )
        whole = not (
            await session.exec(
                select(
                    exists(select(col(SearchPassage.digest)).where(not_(_has_vector(name))))
                )
            )
        ).one()
        if whole:
            await session.exec(delete(SearchVector).where(col(SearchVector.model) != name))
        await session.commit()
