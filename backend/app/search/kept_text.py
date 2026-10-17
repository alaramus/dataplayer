"""The text of a connection's files, kept below the folders its owner chose (D218).

Read by the keeper right after the names, from the names it just kept: a file
whose time and size did not change is not read, and one whose text did not
change keeps its chunks. What the rule does not read — binary, too large — is
remembered as such so it is not opened again while it stays the same.
"""

import hashlib
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, not_, update
from sqlmodel import col, select

from app.adapters.protocol import AdapterError, ExtractsText, NodeNotFound
from app.adapters.search import SearchBounds, out_of_time
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.core.translation import say
from app.search.keep import (
    SearchChunk,
    SearchContentFile,
    SearchContentScope,
    SearchName,
    SearchPassage,
)
from app.search.kept import outside, under

logger = logging.getLogger(__name__)

# A chunk is a run of lines the trigram index finds: small enough that a hit
# names a few lines, large enough that a file is not thousands of rows.
CHUNK_LINES = 40
CHUNK_CHARACTERS = 8000
# A passage the model reads (D221): well inside its 512 tokens, so nothing of
# it is cut, and short enough that a hit by meaning points at a few lines.
PASSAGE_CHARACTERS = 1000


def version_of(node: Mapping[str, Any]) -> str:
    """What a file was when its name was read: time and size."""
    return f"{node.get('modified_at')}|{node.get('size_bytes')}"


def chunks_of(lines: Sequence[str]) -> list[tuple[int, str]]:
    """Runs of lines with the number of their first, counted from 1."""
    found: list[tuple[int, str]] = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines) and end - start < CHUNK_LINES:
            size += len(lines[end]) + 1
            end += 1
            if size >= CHUNK_CHARACTERS:
                break
        found.append((start + 1, "\n".join(lines[start:end])))
        start = end
    return found


def passages_of(lines: Sequence[str]) -> list[tuple[int, str]]:
    """Runs of non-empty lines of at most `PASSAGE_CHARACTERS`, each with its first
    line's number; a longer line is a passage of its own, cut."""
    found: list[tuple[int, str]] = []
    run: list[str] = []
    first = 0
    size = 0
    for number, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        if run and size + len(text) + 1 > PASSAGE_CHARACTERS:
            found.append((first, "\n".join(run)))
            run, size = [], 0
        if not run:
            first = number
        run.append(text[:PASSAGE_CHARACTERS])
        size += len(run[-1]) + 1
    if run:
        found.append((first, "\n".join(run)))
    return found


def digest_of(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class _Tally:
    files: int = 0
    unread: int = 0


@dataclass
class _Pass:
    read_bytes: int = 0
    notice: str | None = None
    tallies: dict[str, _Tally] = field(default_factory=dict)


async def keep_text(connector_id: uuid.UUID, adapter: object) -> None:
    """One contents pass after a names pass. A failure is said on the scopes."""
    async with async_session_maker() as session:
        scopes = [
            one.node_id
            for one in (
                await session.exec(
                    select(SearchContentScope).where(
                        col(SearchContentScope.connector_id) == connector_id
                    )
                )
            ).all()
        ]
    if not scopes or not isinstance(adapter, ExtractsText):
        return
    state = _Pass(tallies={scope: _Tally() for scope in scopes})
    try:
        await _read(connector_id, adapter, scopes, state)
    except AdapterError as failure:
        state.notice = failure.message
    await _settle(connector_id, scopes, state)


async def _read(
    connector_id: uuid.UUID, adapter: ExtractsText, scopes: list[str], state: _Pass
) -> None:
    async with async_session_maker() as session:
        names = (
            await session.exec(
                select(SearchName.node_id, SearchName.node).where(
                    col(SearchName.connector_id) == connector_id, col(SearchName.kind) == "file"
                )
            )
        ).all()
        known = {
            row.node_id: row
            for row in (
                await session.exec(
                    select(SearchContentFile).where(
                        col(SearchContentFile.connector_id) == connector_id
                    )
                )
            ).all()
        }
    bounds = SearchBounds.within(settings.SEARCH_KEPT_PASS_SECONDS)
    looked = 0
    for node_id, node in sorted(names):
        holding = [scope for scope in scopes if under(node_id, scope)]
        if not holding:
            continue
        version = version_of(node)
        row = known.get(node_id)
        if row is None or row.version != version:
            if bounds.over():
                state.notice = out_of_time(looked, "files")
                return
            if state.read_bytes > settings.SEARCH_KEPT_CONTENTS_BYTES:
                state.notice = say(
                    "More than {size} MB were read; the rest is read on the next pass",
                    size=f"{settings.SEARCH_KEPT_CONTENTS_BYTES // 1_000_000:,}",
                )
                return
            try:
                extracted = await adapter.extract_text(node_id, bounds)
            except NodeNotFound:
                continue
            looked += 1
            state.read_bytes += extracted.read_bytes
            row = await _write(connector_id, node_id, version, row, extracted.lines, extracted.digest)
        for scope in holding:
            tally = state.tallies[scope]
            if row.readable:
                tally.files += 1
            else:
                tally.unread += 1


async def _write(
    connector_id: uuid.UUID,
    node_id: str,
    version: str,
    row: SearchContentFile | None,
    lines: list[str] | None,
    digest: str | None,
) -> SearchContentFile:
    """The file's row, and its chunks unless its text is what was kept already."""
    async with async_session_maker() as session:
        same = row is not None and lines is not None and row.digest == digest
        current = await session.get(SearchContentFile, (connector_id, node_id))
        if current is None:
            current = SearchContentFile(connector_id=connector_id, node_id=node_id, version=version)
        current.version = version
        current.digest = digest
        current.readable = lines is not None
        session.add(current)
        if not same:
            await session.exec(
                delete(SearchChunk).where(
                    col(SearchChunk.connector_id) == connector_id,
                    col(SearchChunk.node_id) == node_id,
                )
            )
            await session.exec(
                delete(SearchPassage).where(
                    col(SearchPassage.connector_id) == connector_id,
                    col(SearchPassage.kind) == "text",
                    col(SearchPassage.node_id) == node_id,
                )
            )
            for seq, (line, text) in enumerate(passages_of(lines or [])):
                session.add(
                    SearchPassage(
                        connector_id=connector_id,
                        kind="text",
                        node_id=node_id,
                        seq=seq,
                        line=line,
                        text=text,
                        digest=digest_of(text),
                    )
                )
            for seq, (line, text) in enumerate(chunks_of(lines or [])):
                session.add(
                    SearchChunk(
                        connector_id=connector_id,
                        node_id=node_id,
                        seq=seq,
                        line=line,
                        text=text,
                        # Folded once, by the rule's own fold (D215).
                        folded=text.casefold(),
                    )
                )
        await session.commit()
        await session.refresh(current)
        return current


async def _settle(connector_id: uuid.UUID, scopes: list[str], state: _Pass) -> None:
    """What no kept name holds any more, or no scope covers, goes; each scope says how it went."""
    async with async_session_maker() as session:
        if state.notice is None:
            names = select(SearchName.node_id).where(col(SearchName.connector_id) == connector_id)
            for passages in (
                not_(col(SearchPassage.node_id).in_(names)),
                outside(col(SearchPassage.node_id), scopes),
            ):
                await session.exec(
                    delete(SearchPassage).where(
                        col(SearchPassage.connector_id) == connector_id,
                        col(SearchPassage.kind) == "text",
                        passages,
                    )
                )
            for table in (SearchContentFile, SearchChunk):
                await session.exec(
                    delete(table).where(
                        col(table.connector_id) == connector_id,
                        not_(col(table.node_id).in_(names)),
                    )
                )
                await session.exec(
                    delete(table).where(
                        col(table.connector_id) == connector_id,
                        outside(col(table.node_id), scopes),
                    )
                )
        now = get_datetime_utc()
        for scope, tally in state.tallies.items():
            await session.exec(
                update(SearchContentScope)
                .where(
                    col(SearchContentScope.connector_id) == connector_id,
                    col(SearchContentScope.node_id) == scope,
                )
                .values(read_at=now, files=tally.files, unread=tally.unread, notice=state.notice)
            )
        await session.commit()
