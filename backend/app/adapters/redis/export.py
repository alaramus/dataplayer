"""Every row of a Redis node, in bounded batches (D44, D171).

What is written is what the grid shows, with the command each type has for
reading itself a piece at a time: `HSCAN` and `SSCAN` for a hash and a set,
index ranges for a list and a sorted set, `XRANGE` from the last id for a
stream. Nothing is read whole except a string, which is one value.

The order is the source's. A list, a sorted set and a stream keep theirs; a
hash and a set come as Redis scans them, which may give an element twice or
miss one while they change — the grid sorts for the eye, and sorting a million
fields would mean holding them all.
"""

from collections.abc import AsyncIterator

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.fetch import listing_row
from app.adapters.redis.keyspace import (
    SCAN_CEILING,
    KeyRef,
    NotAKey,
    RedisKeyspace,
    is_direct,
    is_folder_prefix,
    is_key,
    key_ref,
    pattern_under,
    place_ref,
)
from app.adapters.redis.session import RedisSession, resolved, text
from app.adapters.redis.shapes import (
    KEY_SHAPES,
    LISTING,
    Shape,
    stream_fields,
)

type Rows = AsyncIterator[list[list[str | None]]]

TOO_MANY_KEYS = "This folder holds more keys than can be listed"


class RedisExport:
    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        shape, rows = await self._reader(request)
        names = [name for name, _, _ in shape]
        unknown = [column for column in request.columns if column not in names]
        if unknown:
            raise ValueError(f"Unknown column: {unknown[0]}")
        picked = [names.index(column) for column in request.columns]
        pending: list[list[str | None]] = []
        async for found in rows:
            pending.extend([row[index] for index in picked] for row in found)
            while len(pending) >= EXPORT_BATCH_SIZE:
                yield ExportBatch(rows=pending[:EXPORT_BATCH_SIZE])
                pending = pending[EXPORT_BATCH_SIZE:]
        if pending:
            yield ExportBatch(rows=pending)

    async def _reader(self, request: ExportRequest) -> tuple[Shape, Rows]:
        """The node's columns and its rows, checked before anything is read.

        Redis does not take a filter or a sort.
        """
        node_id = request.node_id
        if request.filters or request.sort:
            raise ValueError("Redis rows cannot be filtered or sorted")
        if is_key(node_id):
            ref = key_ref(node_id)
            facts = await self._keyspace.facts_of(ref.database, ref.name)
            if facts is None:
                raise NodeNotFound(node_id)
            reader = _READERS[facts.data_type]
            return KEY_SHAPES[facts.data_type], reader(self, ref)
        try:
            place = place_ref(node_id)
        except NotAKey:
            raise NodeNotFound(node_id) from None
        if place.prefix and not is_folder_prefix(place.prefix):
            raise NodeNotFound(node_id)
        names, complete = await self._keyspace.scan_names(
            place.database, pattern_under(place.prefix), SCAN_CEILING
        )
        # Refused rather than saved short: a CSV that stopped at the ceiling
        # would look like the whole folder.
        if not complete or len(names) > SCAN_CEILING:
            raise ValueError(TOO_MANY_KEYS)
        direct = sorted(name for name in names if is_direct(name, place.prefix))
        return LISTING, self._listing(place.database, direct)

    async def _listing(self, database: int, names: list[str]) -> Rows:
        for start in range(0, len(names), EXPORT_BATCH_SIZE):
            facts = await self._keyspace.describe(
                database, names[start : start + EXPORT_BATCH_SIZE]
            )
            yield [listing_row(one) for one in facts]

    async def _string(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            value = await client.get(ref.name)
        if value is not None:
            yield [[text(value)]]

    async def _hash(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            cursor = 0
            while True:
                cursor, found = await resolved(
                    client.hscan(ref.name, cursor=cursor, count=EXPORT_BATCH_SIZE)
                )
                if found:
                    yield [[text(field), text(value)] for field, value in found.items()]
                if cursor == 0:
                    return

    async def _set(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            cursor = 0
            while True:
                cursor, found = await resolved(
                    client.sscan(ref.name, cursor=cursor, count=EXPORT_BATCH_SIZE)
                )
                if found:
                    yield [[text(member)] for member in found]
                if cursor == 0:
                    return

    async def _list(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            start = 0
            while True:
                found = await resolved(
                    client.lrange(ref.name, start, start + EXPORT_BATCH_SIZE - 1)
                )
                if not found:
                    return
                yield [
                    [str(start + index), text(value)] for index, value in enumerate(found)
                ]
                if len(found) < EXPORT_BATCH_SIZE:
                    return
                start += EXPORT_BATCH_SIZE

    async def _zset(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            start = 0
            while True:
                found = await client.zrange(
                    ref.name, start, start + EXPORT_BATCH_SIZE - 1, withscores=True
                )
                if not found:
                    return
                yield [[text(member), str(score)] for member, score in found]
                if len(found) < EXPORT_BATCH_SIZE:
                    return
                start += EXPORT_BATCH_SIZE

    async def _stream(self, ref: KeyRef) -> Rows:
        async with self._session.connection(ref.database) as client:
            after = "-"
            while True:
                found = await client.xrange(ref.name, min=after, count=EXPORT_BATCH_SIZE)
                if not found:
                    return
                yield [[text(entry_id), stream_fields(fields)] for entry_id, fields in found]
                if len(found) < EXPORT_BATCH_SIZE:
                    return
                after = _next_id(text(found[-1][0]))


def _next_id(entry_id: str) -> str:
    """The smallest id after this one, for servers older than exclusive ranges."""
    milliseconds, _, sequence = entry_id.partition("-")
    return f"{milliseconds}-{int(sequence or 0) + 1}"


_READERS = {
    "string": RedisExport._string,
    "hash": RedisExport._hash,
    "list": RedisExport._list,
    "set": RedisExport._set,
    "zset": RedisExport._zset,
    "stream": RedisExport._stream,
}
