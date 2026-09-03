"""Reading a Redis node as rows.

Two things can be read. A key is read as what it holds, and what that looks
like depends on its type: a hash is fields and values, a list is positions and
values, a sorted set is members and scores. A folder is read as the keys under
it — name, type, expiry and size — which is the listing a person wants when
they are looking for a key rather than at one.

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
    SCAN_CEILING,
    KeyFacts,
    RedisKeyspace,
    folder_prefix,
    is_key,
    key_name,
)
from app.adapters.redis.session import RedisSession, resolved, text
from app.adapters.relation import ColumnType, TypeCategory

# What a string key shows. A value larger than this is shown up to here and
# said to be longer: a viewer is a preview, and a megabyte of JSON in a cell
# is not something a grid can do anything with.
MAX_STRING_BYTES = 64 * 1024


def _column(name: str, sql: str, category: TypeCategory) -> FetchColumn:
    """One column, saying it can be neither sorted nor filtered.

    Redis has no index over values, so a source that offered either would be
    offering to read everything and do it here.
    """
    return FetchColumn(
        name=name,
        type=ColumnType(sql=sql, category=category),
        sortable=False,
        filter_operators=[],
    )


class RedisFetch:
    """One page of whatever a node holds."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if is_key(request.node_id):
            return await self._one_key(request)
        return await self._keys_under(request)

    # --- a folder, read as the keys under it -------------------------------

    async def _keys_under(self, request: FetchRequest) -> FetchResult:
        # Refuses an id this source did not issue, before anything is read.
        folder_prefix(request.node_id)
        children = await self._keyspace.list_children(request.node_id)
        names = sorted(
            key_name(node.id) for node in children if node.kind == "key"
        )
        page = names[request.offset : request.offset + request.limit]
        facts = await self._keyspace.describe(page)
        return FetchResult(
            columns=[
                _column("key", "key", "string"),
                _column("type", "type", "string"),
                _column("ttl", "seconds", "number"),
                _column("size", "count", "number"),
            ],
            rows=[
                [
                    one.name,
                    one.data_type,
                    None if one.ttl_seconds is None else str(one.ttl_seconds),
                    None if one.length is None else str(one.length),
                ]
                for one in facts
            ],
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
        name = key_name(request.node_id)
        facts = await self._keyspace.facts_of(name)
        if facts is None:
            raise NodeNotFound(request.node_id)
        reader = _READERS[facts.data_type]
        columns, rows, has_more = await reader(self, name, request)
        return FetchResult(
            columns=columns,
            rows=rows,
            has_more=has_more,
            page_commands=["download", "share"],
        )

    async def _string(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        """One row, because a string key is one value.

        Read by range rather than whole: `GET` on a key holding ten megabytes
        would put ten megabytes in this process to show the first screenful.
        """
        del request
        async with self._session.connection() as client:
            raw = await client.getrange(name, 0, MAX_STRING_BYTES)
            size = int(await client.strlen(name))
        value = text(raw)
        truncated = size > MAX_STRING_BYTES
        return (
            [_column("value", "string", "string")],
            [[value + (" …" if truncated else "")]],
            False,
        )

    async def _hash(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        async with self._session.connection() as client:
            found = await resolved(client.hgetall(name))
        pairs = sorted((text(k), text(v)) for k, v in found.items())
        page = _page(pairs, request)
        return (
            [_column("field", "field", "string"), _column("value", "string", "string")],
            [[field, value] for field, value in page],
            _has_more(pairs, request),
        )

    async def _list(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        """A page of a list, read by index: the one type that pages honestly."""
        start = request.offset
        stop = request.offset + request.limit
        async with self._session.connection() as client:
            found = await resolved(client.lrange(name, start, stop))
        values = [text(one) for one in found]
        has_more = len(values) > request.limit
        return (
            [_column("index", "position", "number"), _column("value", "string", "string")],
            [
                [str(start + index), value]
                for index, value in enumerate(values[: request.limit])
            ],
            has_more,
        )

    async def _set(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        async with self._session.connection() as client:
            found = await resolved(client.smembers(name))
        members = sorted(text(one) for one in found)
        return (
            [_column("member", "member", "string")],
            [[one] for one in _page(members, request)],
            _has_more(members, request),
        )

    async def _zset(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        """A page of a sorted set, in the order the set itself carries."""
        start = request.offset
        stop = request.offset + request.limit
        async with self._session.connection() as client:
            found = await client.zrange(name, start, stop, withscores=True)
        scored = [(text(member), str(score)) for member, score in found]
        return (
            [_column("member", "member", "string"), _column("score", "score", "number")],
            [[member, score] for member, score in scored[: request.limit]],
            len(scored) > request.limit,
        )

    async def _stream(
        self, name: str, request: FetchRequest
    ) -> tuple[list[FetchColumn], list[list[str | None]], bool]:
        """Entries of a stream, each as its id and its fields written out.

        The fields are one column rather than columns of their own: a stream's
        entries need not agree on what they hold, so a grid built from the
        first one would hide what is in the rest.
        """
        async with self._session.connection() as client:
            found = await client.xrange(name, count=request.offset + request.limit + 1)
        entries = [
            (
                text(entry_id),
                ", ".join(f"{text(k)}={text(v)}" for k, v in fields.items()),
            )
            for entry_id, fields in found
        ]
        return (
            [_column("id", "id", "string"), _column("fields", "text", "string")],
            [[entry_id, fields] for entry_id, fields in _page(entries, request)],
            _has_more(entries, request),
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
