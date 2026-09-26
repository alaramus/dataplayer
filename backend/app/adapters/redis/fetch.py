"""Reading a Redis node as rows.

Three things can be read. A key is read as what it holds, and what that looks
like depends on its type: a hash is fields and values, a list is positions and
values, a sorted set is members and scores. A folder is read as the keys under
it — name, type, expiry and size — which is the listing a person wants when
they are looking for a key rather than at one. A table somebody declared over
a folder is read as one row per hash in it (D170), in `tables.py`.

Neither sorts and neither filters. Redis has no index over values and no
ordering except the one a list or a sorted set carries in itself, so the
columns say `sortable=False` and offer no operators: a grid that offered them
would be offering something this source would have to fake by reading
everything.
"""

from collections.abc import Sequence
from typing import Any

from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import (
    MAX_STRING_BYTES,
    SCAN_CEILING,
    KeyFacts,
    KeyRef,
    RedisKeyspace,
    is_key,
    is_table,
    key_of,
    key_ref,
    place_of,
)
from app.adapters.redis.session import RedisSession, resolved, text
from app.adapters.redis.shapes import KEY_SHAPES, LISTING, fetch_columns, stream_fields
from app.adapters.redis.tables import RedisTables
from app.adapters.redis.update import (
    NO_DELETE,
    NO_INSERT,
    NO_UPDATE,
    row_handle_of,
    writer_for,
)


def _columns_of(data_type: str) -> list[FetchColumn]:
    """A key's columns. Whether one can be written is added afterwards, from the
    one place that knows how each type is written: a reader that also declared
    what is editable would be a second answer to that question."""
    return fetch_columns(KEY_SHAPES[data_type])


class RedisFetch:
    """One page of whatever a node holds."""

    def __init__(
        self, session: RedisSession, keyspace: RedisKeyspace, tables: RedisTables
    ) -> None:
        self._session = session
        self._keyspace = keyspace
        self._tables = tables

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if is_key(request.node_id):
            return await self._one_key(request)
        if is_table(request.node_id):
            return await self._tables.fetch(request)
        return await self._keys_under(request)

    # --- a folder, read as the keys under it -------------------------------

    async def _keys_under(self, request: FetchRequest) -> FetchResult:
        # Refuses an id this source did not issue, before anything is read.
        # The root of the connection is not one: what is there is the list of
        # databases, and a list of databases is not a page of rows.
        place = place_of(request.node_id)
        children = await self._keyspace.list_children(request.node_id)
        names = sorted(
            key_ref(node.id).name for node in children if node.kind == "key"
        )
        page = names[request.offset : request.offset + request.limit]
        facts = await self._keyspace.describe(place.database, page)
        return FetchResult(
            columns=fetch_columns(LISTING),
            rows=[listing_row(one) for one in facts],
            has_more=len(names) > request.offset + request.limit,
            # Deliberately not the same as "there are no more keys": a scan
            # that reached its ceiling has stopped looking, and a page that
            # said "that is all of them" would be wrong about a large key
            # space rather than merely incomplete.
            refresh_seconds=None,
            page_commands=["download", "share"],
        )

    # --- one key, read as what it holds ------------------------------------

    async def _one_key(self, request: FetchRequest) -> FetchResult:
        ref = key_of(request.node_id)
        facts = await self._keyspace.facts_of(ref.database, ref.name)
        if facts is None:
            raise NodeNotFound(request.node_id)
        reader = _READERS[facts.data_type]
        rows, has_more = await reader(self, ref, request)
        return _writable(facts.data_type, _columns_of(facts.data_type), rows, has_more)

    async def _string(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        """One row, because a string key is one value.

        Read by range rather than whole: `GET` on a key holding ten megabytes
        would put ten megabytes in this process to show the first screenful.
        """
        del request
        async with self._session.connection(ref.database) as client:
            raw = await client.getrange(ref.name, 0, MAX_STRING_BYTES)
            size = int(await client.strlen(ref.name))
        value = text(raw)
        truncated = size > MAX_STRING_BYTES
        return [[value + (" …" if truncated else "")]], False

    async def _hash(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        async with self._session.connection(ref.database) as client:
            found = await resolved(client.hgetall(ref.name))
        pairs = sorted((text(k), text(v)) for k, v in found.items())
        page = _page(pairs, request)
        return [[field, value] for field, value in page], _has_more(pairs, request)

    async def _list(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        """A page of a list, read by index: the one type that pages honestly."""
        start = request.offset
        stop = request.offset + request.limit
        async with self._session.connection(ref.database) as client:
            found = await resolved(client.lrange(ref.name, start, stop))
        values = [text(one) for one in found]
        has_more = len(values) > request.limit
        return (
            [
                [str(start + index), value]
                for index, value in enumerate(values[: request.limit])
            ],
            has_more,
        )

    async def _set(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        async with self._session.connection(ref.database) as client:
            found = await resolved(client.smembers(ref.name))
        members = sorted(text(one) for one in found)
        return [[one] for one in _page(members, request)], _has_more(members, request)

    async def _zset(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        """A page of a sorted set, in the order the set itself carries."""
        start = request.offset
        stop = request.offset + request.limit
        async with self._session.connection(ref.database) as client:
            found = await client.zrange(ref.name, start, stop, withscores=True)
        scored = [(text(member), str(score)) for member, score in found]
        return (
            [[member, score] for member, score in scored[: request.limit]],
            len(scored) > request.limit,
        )

    async def _stream(
        self, ref: KeyRef, request: FetchRequest
    ) -> tuple[list[list[str | None]], bool]:
        """Entries of a stream, each as its id and its fields written out."""
        async with self._session.connection(ref.database) as client:
            found = await client.xrange(ref.name, count=request.offset + request.limit + 1)
        entries = [(text(entry_id), stream_fields(fields)) for entry_id, fields in found]
        return (
            [[entry_id, fields] for entry_id, fields in _page(entries, request)],
            _has_more(entries, request),
        )


def listing_row(facts: KeyFacts) -> list[str | None]:
    """One key of a folder's listing: name, type, expiry and size."""
    return [
        facts.name,
        facts.data_type,
        None if facts.ttl_seconds is None else str(facts.ttl_seconds),
        None if facts.length is None else str(facts.length),
    ]


def _writable(
    data_type: str,
    columns: list[FetchColumn],
    rows: list[list[str | None]],
    has_more: bool,
) -> FetchResult:
    """A page of a key, saying which of it can be written and how.

    Every one of these answers comes from the writer of that type, so the page
    cannot offer an edit the write side would refuse. A row whose values are
    not all there — a string too long to have been shown whole — still gets a
    handle: the fingerprint is of what was shown, so an edit of it is refused
    for the reason it should be.
    """
    writer = writer_for(data_type)
    if writer is None or not writer.editable:
        return FetchResult(
            columns=columns,
            rows=rows,
            has_more=has_more,
            update_reason=NO_UPDATE.get(data_type),
            insert_reason=NO_INSERT.get(data_type),
            delete_reason=NO_DELETE.get(data_type),
            page_commands=["download", "share"],
        )
    return FetchResult(
        columns=[
            column.model_copy(update={"editable": column.name in writer.editable})
            for column in columns
        ],
        rows=rows,
        has_more=has_more,
        row_handles=[
            row_handle_of(data_type, [value or "" for value in row]) for row in rows
        ],
        update_supported=True,
        insert_supported=data_type not in NO_INSERT,
        insert_reason=NO_INSERT.get(data_type),
        delete_supported=data_type not in NO_DELETE,
        delete_reason=NO_DELETE.get(data_type),
        page_commands=["download", "share"],
    )


def _page[T](items: Sequence[T], request: FetchRequest) -> Sequence[T]:
    return items[request.offset : request.offset + request.limit]


def _has_more(items: Sequence[Any], request: FetchRequest) -> bool:
    return len(items) > request.offset + request.limit


# Which reader answers for which type. A table rather than a chain of `elif`,
# for the reason every other table in this repository is one: a type that
# gains a reader is a line here.
_READERS = {
    "string": RedisFetch._string,
    "hash": RedisFetch._hash,
    "list": RedisFetch._list,
    "set": RedisFetch._set,
    "zset": RedisFetch._zset,
    "stream": RedisFetch._stream,
}

__all__ = ["MAX_STRING_BYTES", "SCAN_CEILING", "KeyFacts", "RedisFetch"]
