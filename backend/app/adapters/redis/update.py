"""Writing what a key holds, one element at a time.

The actions write a whole key: six of them, one per type, each taking
everything the key will hold (D91). This is the other half — changing one
field of a hash somebody is looking at, correcting one element of a list,
giving a member of a sorted set a different score. It is the grid's ordinary
editing contract (D25, D26), answered by a source that has no rows and no
versions of its own.

What stands in for a version is a fingerprint of what was read, carried in the
row handle: an edit whose element no longer holds what the page showed is
refused rather than applied. Redis has no compare-and-set for a field, so this
is optimism with a re-read, which is honest about being a race the server does
not arbitrate — and still better than a write that silently overwrites what
somebody else has just put there.

One writer per type rather than a chain of branches, for the reason the
readers beside them are a table: a type that becomes writable is a class and a
line, not an `elif`.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import redis.asyncio as redis

from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import (
    MAX_STRING_BYTES,
    KeyRef,
    RedisKeyspace,
    is_key,
    key_of,
)
from app.adapters.redis.row_handle import (
    RedisRowHandle,
    decode_row_handle,
    encode_row_handle,
    fingerprint,
)
from app.adapters.redis.session import RedisSession, resolved, text
from app.adapters.update import (
    CellsRejected,
    CellsUpdated,
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    RejectedCell,
    RejectedValue,
    RowConflict,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
    UpdatedRow,
    ValuesRejected,
)

# What a value written into a key may be. The same ceiling the reader shows a
# string up to: a cell of a grid is not where a megabyte is typed, and a value
# larger than what the page showed would be a save that silently truncated.
MAX_VALUE_BYTES = MAX_STRING_BYTES

# Why each type refuses what it refuses, said once so the fetch result and the
# refusal agree word for word.
NO_INSERT: Mapping[str, str] = {
    "string": "A string key holds one value; there is no row to add",
    "stream": "An entry of a stream is written by the server, not typed here",
}
NO_DELETE: Mapping[str, str] = {
    "string": "Removing the value of a string key is removing the key",
    "list": (
        "An element of a list cannot be removed by position without rewriting "
        "the list"
    ),
    "stream": "An entry of a stream is not removed here",
}
NO_UPDATE: Mapping[str, str] = {
    "stream": "The entries of a stream are written once and not edited",
}


class ElementWriter(ABC):
    """What one kind of key admits, and how each of its rows is written.

    A base class rather than a protocol, because most of these share the two
    refusals below: a type that cannot take a new row and one that cannot lose
    one say so by not overriding them.
    """

    data_type: ClassVar[str]
    # The row's columns, in the order the reader lists them.
    columns: ClassVar[tuple[str, ...]]
    # Which of them may be written. A column outside this is refused by name.
    editable: ClassVar[frozenset[str]]

    @abstractmethod
    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        """The row as it stands now, or nothing when the element is gone."""

    @abstractmethod
    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        """Put the row back, replacing the element the identity names."""

    @abstractmethod
    def identity_of(self, values: Sequence[str]) -> str:
        """What names this row within its key, taken from the row itself."""

    async def insert(
        self, client: redis.Redis, ref: KeyRef, values: Sequence[str]
    ) -> None:
        raise ValueError(NO_INSERT.get(self.data_type, "This key takes no new rows"))

    async def delete(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> None:
        raise ValueError(
            NO_DELETE.get(self.data_type, "Rows of this key are not removed here")
        )


class _StringWriter(ElementWriter):
    """One row, one value, and the identity of a row that has no name."""

    data_type: ClassVar[str] = "string"
    columns: ClassVar[tuple[str, ...]] = ("value",)
    editable: ClassVar[frozenset[str]] = frozenset({"value"})

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        del identity
        raw = await resolved(client.getrange(ref.name, 0, MAX_STRING_BYTES))
        exists = await resolved(client.exists(ref.name))
        return None if not exists else [text(raw)]

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        del identity
        # `KEEPTTL`, because editing what a key holds is not a statement about
        # how long it should live: a value corrected in the grid must not
        # silently outlive the deadline somebody set on it.
        await resolved(client.set(ref.name, values[0], keepttl=True))

    def identity_of(self, values: Sequence[str]) -> str:
        del values
        return ""


class _HashWriter(ElementWriter):
    data_type: ClassVar[str] = "hash"
    columns: ClassVar[tuple[str, ...]] = ("field", "value")
    editable: ClassVar[frozenset[str]] = frozenset({"field", "value"})

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        found = await resolved(client.hget(ref.name, identity))
        return None if found is None else [identity, text(found)]

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        field, value = values[0], values[1]
        if field == identity:
            await resolved(client.hset(ref.name, field, value))
            return
        # Renaming a field is two commands, so they are one transaction: a
        # failure between them would leave the field under both names or
        # neither.
        async with client.pipeline(transaction=True) as pipe:
            pipe.hdel(ref.name, identity)
            pipe.hset(ref.name, field, value)
            await pipe.execute()

    def identity_of(self, values: Sequence[str]) -> str:
        return values[0]

    async def insert(
        self, client: redis.Redis, ref: KeyRef, values: Sequence[str]
    ) -> None:
        await resolved(client.hset(ref.name, values[0], values[1]))

    async def delete(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> None:
        await resolved(client.hdel(ref.name, identity))


class _ListWriter(ElementWriter):
    """A list is written by position, which is also what names its rows."""

    data_type: ClassVar[str] = "list"
    columns: ClassVar[tuple[str, ...]] = ("index", "value")
    # The position is where the element is, not something it holds: moving an
    # element is not an edit of it, and a list that let one be typed would be
    # a list where two rows could claim the same place.
    editable: ClassVar[frozenset[str]] = frozenset({"value"})

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        found = await resolved(client.lindex(ref.name, _index(identity)))
        return None if found is None else [identity, text(found)]

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        await resolved(client.lset(ref.name, _index(identity), values[1]))

    def identity_of(self, values: Sequence[str]) -> str:
        return values[0]

    async def insert(
        self, client: redis.Redis, ref: KeyRef, values: Sequence[str]
    ) -> None:
        # At the end, wherever the grid put the draft row: a list has an order
        # of its own, and inserting into the middle of it is not something a
        # position typed into a cell can ask for safely.
        await resolved(client.rpush(ref.name, values[1]))


class _SetWriter(ElementWriter):
    data_type: ClassVar[str] = "set"
    columns: ClassVar[tuple[str, ...]] = ("member",)
    editable: ClassVar[frozenset[str]] = frozenset({"member"})

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        present = await resolved(client.sismember(ref.name, identity))
        return [identity] if present else None

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        if values[0] == identity:
            return
        async with client.pipeline(transaction=True) as pipe:
            pipe.srem(ref.name, identity)
            pipe.sadd(ref.name, values[0])
            await pipe.execute()

    def identity_of(self, values: Sequence[str]) -> str:
        return values[0]

    async def insert(
        self, client: redis.Redis, ref: KeyRef, values: Sequence[str]
    ) -> None:
        await resolved(client.sadd(ref.name, values[0]))

    async def delete(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> None:
        await resolved(client.srem(ref.name, identity))


class _SortedSetWriter(ElementWriter):
    data_type: ClassVar[str] = "zset"
    columns: ClassVar[tuple[str, ...]] = ("member", "score")
    editable: ClassVar[frozenset[str]] = frozenset({"member", "score"})

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        score = await resolved(client.zscore(ref.name, identity))
        return None if score is None else [identity, _score_text(score)]

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        member, score = values[0], _score(values[1])
        if member == identity:
            await resolved(client.zadd(ref.name, {member: score}))
            return
        async with client.pipeline(transaction=True) as pipe:
            pipe.zrem(ref.name, identity)
            pipe.zadd(ref.name, {member: score})
            await pipe.execute()

    def identity_of(self, values: Sequence[str]) -> str:
        return values[0]

    async def insert(
        self, client: redis.Redis, ref: KeyRef, values: Sequence[str]
    ) -> None:
        await resolved(client.zadd(ref.name, {values[0]: _score(values[1])}))

    async def delete(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> None:
        await resolved(client.zrem(ref.name, identity))


class _StreamWriter(ElementWriter):
    """A stream is read and not written here: an entry is an event."""

    data_type: ClassVar[str] = "stream"
    columns: ClassVar[tuple[str, ...]] = ("id", "fields")
    editable: ClassVar[frozenset[str]] = frozenset()

    async def read(
        self, client: redis.Redis, ref: KeyRef, identity: str
    ) -> list[str] | None:
        del client, ref, identity
        return None

    async def write(
        self, client: redis.Redis, ref: KeyRef, identity: str, values: Sequence[str]
    ) -> None:
        del client, ref, identity, values
        raise ValueError(NO_UPDATE["stream"])

    def identity_of(self, values: Sequence[str]) -> str:
        return values[0]


WRITERS: Mapping[str, ElementWriter] = {
    "string": _StringWriter(),
    "hash": _HashWriter(),
    "list": _ListWriter(),
    "set": _SetWriter(),
    "zset": _SortedSetWriter(),
    "stream": _StreamWriter(),
}


def writer_for(data_type: str) -> ElementWriter | None:
    return WRITERS.get(data_type)


def row_handle_of(data_type: str, values: Sequence[str]) -> str | None:
    """The handle for one row of a page, or nothing where rows are not edited.

    Built where the page is built, from the same values the page shows, so a
    handle can never describe something other than what the reader showed.
    """
    writer = WRITERS.get(data_type)
    if writer is None or not writer.editable:
        return None
    return encode_row_handle(data_type, writer.identity_of(values), *values)


class RedisUpdate:
    """Changing, adding and removing the elements of one key."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        ref, writer = await self._writable(request.node_id)
        self._must_be_editable(writer, request.column)
        value = _required(request.value, request.column)
        _bounded(value)
        handle = decode_row_handle(request.row_handle)
        async with self._session.connection(ref.database) as client:
            current = await self._as_read(client, ref, writer, handle)
            values = _with(writer, current, {request.column: value})
            await writer.write(client, ref, handle.identity, values)
        return UpdateCellResult(
            values=list(values),
            row_handle=encode_row_handle(
                writer.data_type, writer.identity_of(values), *values
            ),
        )

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        """A block, or none of it — as far as one server without a transaction
        across keys can promise.

        The values are checked first and every unreadable one is named, so a
        paste with a bad score in it changes nothing rather than half of what
        it named (D26).
        """
        ref, writer = await self._writable(request.node_id)
        rejected: list[RejectedCell] = []
        for index, row in enumerate(request.rows):
            for cell in row.cells:
                self._must_be_editable(writer, cell.column)
                if cell.value is None or not _readable(writer, cell.column, cell.value):
                    rejected.append(RejectedCell(row=index, column=cell.column))
        if rejected:
            return CellsRejected(cells=rejected)

        updated: list[UpdatedRow] = []
        async with self._session.connection(ref.database) as client:
            for row in request.rows:
                handle = decode_row_handle(row.row_handle)
                current = await self._as_read(client, ref, writer, handle)
                edits = {
                    cell.column: cell.value
                    for cell in row.cells
                    if cell.value is not None
                }
                values = _with(writer, current, edits)
                for value in values:
                    _bounded(value)
                await writer.write(client, ref, handle.identity, values)
                updated.append(
                    UpdatedRow(
                        row_handle=encode_row_handle(
                            writer.data_type, writer.identity_of(values), *values
                        ),
                        values=list(values),
                    )
                )
        return CellsUpdated(rows=updated)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        ref, writer = await self._writable(request.node_id)
        supplied = {item.column: item.value for item in request.values}
        values = _complete(writer, supplied)
        for value in values:
            _bounded(value)
        async with self._session.connection(ref.database) as client:
            await writer.insert(client, ref, values)
        return InsertRowResult(
            values=list(values),
            row_handle=encode_row_handle(
                writer.data_type, writer.identity_of(values), *values
            ),
        )

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        ref, writer = await self._writable(request.node_id)
        rows: list[list[str]] = []
        rejected: list[RejectedValue] = []
        for index, row in enumerate(request.rows):
            supplied = dict(zip(request.columns, row, strict=True))
            for column, value in supplied.items():
                if value is None or not _readable(writer, column, value):
                    rejected.append(
                        RejectedValue(row=index, column=column, value=value)
                    )
            if not rejected:
                rows.append(list(_complete(writer, supplied)))
        if rejected:
            return ValuesRejected(cells=rejected)
        async with self._session.connection(ref.database) as client:
            for values in rows:
                await writer.insert(client, ref, values)
        return RowsInserted(inserted=len(rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        ref, writer = await self._writable(request.node_id)
        async with self._session.connection(ref.database) as client:
            for raw in request.row_handles:
                handle = decode_row_handle(raw)
                await self._as_read(client, ref, writer, handle)
                await writer.delete(client, ref, handle.identity)
        return DeleteRowsResult(deleted=len(request.row_handles))

    async def _writable(self, node_id: str) -> tuple[KeyRef, ElementWriter]:
        """The key this is about, and what its type admits.

        A folder is refused here rather than half-answered: the keys under one
        are a listing, and a name in it is a node rather than a value to type
        over.
        """
        if not is_key(node_id):
            raise ValueError("Only what a key holds can be edited")
        ref = key_of(node_id)
        facts = await self._keyspace.facts_of(ref.database, ref.name)
        if facts is None:
            raise NodeNotFound(node_id)
        writer = WRITERS.get(facts.data_type)
        if writer is None or not writer.editable:
            raise ValueError(
                NO_UPDATE.get(facts.data_type, "This key cannot be edited")
            )
        return ref, writer

    def _must_be_editable(self, writer: ElementWriter, column: str) -> None:
        if column not in writer.columns:
            raise ValueError(f'This key has no column "{column}"')
        if column not in writer.editable:
            raise ValueError(f'Column "{column}" cannot be edited')

    async def _as_read(
        self,
        client: redis.Redis,
        ref: KeyRef,
        writer: ElementWriter,
        handle: RedisRowHandle,
    ) -> list[str]:
        """What the element holds now, refused if it is not what was read.

        The whole of this source's optimistic locking: there is no version to
        compare, so what was shown is compared instead.
        """
        if handle.data_type != writer.data_type:
            raise RowConflict
        current = await writer.read(client, ref, handle.identity)
        if current is None or fingerprint(*current) != handle.fingerprint:
            raise RowConflict
        return current


def _with(
    writer: ElementWriter, current: Sequence[str], edits: Mapping[str, str]
) -> tuple[str, ...]:
    """The row as it will be, which is the row as it is with cells replaced."""
    return tuple(
        edits.get(column, held)
        for column, held in zip(writer.columns, current, strict=True)
    )


def _complete(
    writer: ElementWriter, supplied: Mapping[str, str | None]
) -> tuple[str, ...]:
    """A whole new row from what was typed, refusing what was left out.

    Redis has no defaults and no nulls: a field with no name is not a field,
    and a member with no score is not a member of a sorted set.
    """
    values: list[str] = []
    for column in writer.columns:
        if column not in writer.editable:
            # The position of a new element is the server's, not the caller's.
            values.append("")
            continue
        value = supplied.get(column)
        if value is None or value == "":
            raise ValueError(f'A new row needs a value for "{column}"')
        if not _readable(writer, column, value):
            raise ValueError(f'"{column}" takes a number')
        values.append(value)
    return tuple(values)


def _required(value: str | None, column: str) -> str:
    """Redis holds no nulls, so an emptied cell is a refusal rather than one."""
    if value is None:
        raise ValueError(f'"{column}" cannot be emptied: Redis holds no nulls')
    return value


def _readable(writer: ElementWriter, column: str, value: str) -> bool:
    """Whether a typed value is one this column can hold.

    Only the score of a sorted set is anything but text, which is why this is
    one question rather than a type system.
    """
    if writer.data_type == "zset" and column == "score":
        try:
            _score(value)
        except ValueError:
            return False
    return True


def _bounded(value: str) -> None:
    if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError(
            f"A value written here is at most {MAX_VALUE_BYTES // 1024} KB"
        )


def _index(identity: str) -> int:
    try:
        return int(identity)
    except ValueError:
        raise ValueError("The row handle is not valid") from None


def _score(value: str) -> float:
    return float(value)


def _score_text(score: Any) -> str:
    """A score as the reader shows it, so a fingerprint matches what was read."""
    return str(score)
