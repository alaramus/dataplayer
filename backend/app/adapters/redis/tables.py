"""Tables declared over Redis folders of hashes (D170).

A folder whose keys are hashes is plainly a table — `user:1`, `user:2`, each
with `name` and `email` — and Redis has no way to say so. A person says it
instead: the declaration is the application's, kept with the connection, and
arrives here when the adapter is built. This module is what only the source
can answer about one: which node can carry it, what the first hashes of the
folder hold, and the rows it reads as.

The rows are the hashes directly in the folder, in key order, each read for
the declared fields alone. A key of another type is counted out rather than
shown. `key` equal to a value is looked up by reading the one key it names,
which is what makes it an end of a reference (D172). Writing the rows is
`table_update.py`'s (D173).
"""

import re
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

from app.adapters.declared_tables import (
    MAX_DECLARED_COLUMNS,
    DeclaredTable,
    DeclaredType,
    DeclareTableRequest,
    ProposedColumn,
    TablePlace,
    TableProposal,
)
from app.adapters.fetch import FetchRequest, FetchResult, Filter, ScalarFilter, Sort
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import (
    SCAN_BATCH,
    SCAN_CEILING,
    NotAKey,
    PlaceRef,
    RedisKeyspace,
    database_id,
    folder_id,
    is_direct,
    is_folder_prefix,
    is_table,
    parent_prefix,
    pattern_under,
    place_ref,
    table_ref,
)
from app.adapters.redis.row_handle import encode_row_handle, fingerprint
from app.adapters.redis.session import RedisSession, text
from app.adapters.redis.shapes import (
    KEY_COLUMN,
    model_columns,
    table_columns,
    table_shape,
)
from app.adapters.relation import RelationModel

# How many keys the grid reads of a table's folder. Names are short, which is
# why this is higher than the catalog's own ceiling.
TABLE_CEILING = 100_000

# What a proposal is read from: the first hashes of the folder, and a bounded
# look at each — a hash of a million fields is still one row of a table.
SAMPLE_KEYS = 100
SAMPLE_FIELDS = 200

CHOOSE_FOLDER = "Select a folder to describe as a table"
KEY_ONLY = "A Redis table is filtered only by key equal to a value"

# What a row handle says it names: a row of a declared table, not an element
# of one key (D173).
TABLE_ROW = "table"
# Stands for a field the hash lacks in a fingerprint, which no value typed
# into a cell contains.
_ABSENT = "\x01"

_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class RedisTables:
    """The tables declared over this server's folders, as rows and as places."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    def declared(self, node_id: str | None) -> tuple[PlaceRef, DeclaredTable]:
        """The folder a table id reads and its declaration, or no such node."""
        try:
            place = table_ref(node_id)
        except NotAKey:
            raise NodeNotFound(node_id or "") from None
        table = self._keyspace.table_at(place.database, place.prefix)
        if table is None:
            raise NodeNotFound(node_id or "")
        return place, table

    async def place(self, node_id: str) -> TablePlace:
        table: DeclaredTable | None
        if is_table(node_id):
            place, table = self.declared(node_id)
        else:
            try:
                place = place_ref(node_id)
            except NotAKey:
                raise ValueError(CHOOSE_FOLDER) from None
            if not is_folder_prefix(place.prefix):
                raise ValueError(CHOOSE_FOLDER)
            table = self._keyspace.table_at(place.database, place.prefix)
        parent = parent_prefix(place.prefix)
        return TablePlace(
            place_id=folder_id(place.database, place.prefix),
            listed_in=(
                folder_id(place.database, parent)
                if parent
                else database_id(place.database)
            ),
            declared=table,
        )

    async def propose(self, node_id: str) -> TableProposal:
        """The fields of the first hashes, or the declaration and what else they hold."""
        found = await self.place(node_id)
        place = place_ref(found.place_id)
        sample = await self._sample(place)
        seen: dict[str, list[str]] = {}
        for fields in sample:
            for name, value in fields.items():
                seen.setdefault(name, []).append(value)
        declared = found.declared
        columns = [
            ProposedColumn(
                name=column.name,
                type=column.type,
                ticked=True,
                found_in=len(seen.get(column.name, [])),
            )
            for column in (declared.columns if declared is not None else [])
        ]
        taken = {column.name for column in columns} | {KEY_COLUMN}
        columns.extend(
            ProposedColumn(
                name=name,
                type=guessed_type(values),
                ticked=declared is None,
                found_in=len(values),
            )
            for name, values in seen.items()
            if name not in taken
        )
        parent = parent_prefix(place.prefix)
        return TableProposal(
            node_id=node_id,
            name=(
                declared.name
                if declared is not None
                else place.prefix[len(parent) : -1]
            ),
            columns=columns[:MAX_DECLARED_COLUMNS],
            sampled=len(sample),
            declared=declared is not None,
            reserved=[KEY_COLUMN],
        )

    async def checked(self, request: DeclareTableRequest) -> DeclaredTable:
        found = await self.place(request.node_id)
        if any(column.name == KEY_COLUMN for column in request.columns):
            raise ValueError(
                f"A column cannot be called {KEY_COLUMN}: the table's first column is"
            )
        return DeclaredTable(
            place_id=found.place_id, name=request.name, columns=request.columns
        )

    def model(self, node_id: str) -> RelationModel:
        place, table = self.declared(node_id)
        return RelationModel(
            node_id=node_id,
            name=table.name,
            kind="declared_table",
            comment=f"Declared over the hashes in {place.prefix}",
            columns=model_columns(table_shape(table)),
        )

    # --- rows --------------------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        """One page of rows: the folder's hashes in key order, at most a ceiling of them."""
        place, table = self.declared(request.node_id)
        key = key_asked(request.filters, request.sort)
        if key is not None:
            found = await self._looked_up(place, table, key)
            return _page(
                table, found[request.offset : request.offset + request.limit], False, None
            )
        names, complete = await self._keyspace.scan_names(
            place.database, pattern_under(place.prefix), TABLE_CEILING
        )
        # A scan's last batch may overshoot; the ceiling holds all the same.
        if len(names) > TABLE_CEILING:
            names, complete = sorted(names)[:TABLE_CEILING], False
        direct = sorted(name for name in names if is_direct(name, place.prefix))
        types = await self._keyspace.types_of(place.database, direct)
        hashes = [name for name, kind in zip(direct, types, strict=True) if kind == "hash"]
        others = sum(1 for kind in types if kind not in ("hash", "none"))
        page = hashes[request.offset : request.offset + request.limit]
        return _page(
            table,
            await self._rows(place, table, page),
            len(hashes) > request.offset + request.limit,
            _notice(others, complete),
        )

    async def one(self, node_id: str, key: str) -> AsyncIterator[list[list[str | None]]]:
        """The row a key names, for an export filtered to it."""
        place, table = self.declared(node_id)
        found = await self._looked_up(place, table, key)
        if found:
            yield found

    async def _looked_up(
        self, place: PlaceRef, table: DeclaredTable, key: str
    ) -> list[list[str | None]]:
        """The one hash a key names, read in one round trip, or no row.

        Exactly the name within the folder: a key of another type, or one that
        lies in a folder below — `42:x` — is not a row of this table.
        """
        name = f"{place.prefix}{key}"
        if not is_direct(name, place.prefix):
            return []
        async with self._session.connection(place.database) as client:
            pipe = client.pipeline(transaction=False)
            pipe.type(name)
            pipe.hmget(name, [column.name for column in table.columns])
            kind, values = await pipe.execute(raise_on_error=False)
        if text(kind) != "hash" or not isinstance(values, list):
            return []
        return [_row(place, name, values)]

    async def scanned(self, node_id: str) -> AsyncIterator[list[list[str | None]]]:
        """Every row, batch by batch as `SCAN` finds the keys: no ceiling, no order.

        The type and the declared fields of a batch are asked in one pipeline;
        what is not a hash answers with an error there and is left out.
        """
        place, table = self.declared(node_id)
        fields = [column.name for column in table.columns]
        async with self._session.connection(place.database) as client:
            cursor = 0
            while True:
                cursor, batch = await client.scan(
                    cursor=cursor, match=pattern_under(place.prefix), count=SCAN_BATCH
                )
                names = [
                    name
                    for name in (text(raw) for raw in batch)
                    if is_direct(name, place.prefix)
                ]
                if names:
                    pipe = client.pipeline(transaction=False)
                    for name in names:
                        pipe.type(name)
                        pipe.hmget(name, fields)
                    answers = await pipe.execute(raise_on_error=False)
                    rows = [
                        _row(place, name, answers[index * 2 + 1])
                        for index, name in enumerate(names)
                        if text(answers[index * 2]) == "hash"
                        and isinstance(answers[index * 2 + 1], list)
                    ]
                    if rows:
                        yield rows
                if cursor == 0:
                    return

    async def _rows(
        self, place: PlaceRef, table: DeclaredTable, names: Sequence[str]
    ) -> list[list[str | None]]:
        if not names:
            return []
        fields = [column.name for column in table.columns]
        async with self._session.connection(place.database) as client:
            pipe = client.pipeline(transaction=False)
            for name in names:
                pipe.hmget(name, fields)
            answers = await pipe.execute(raise_on_error=False)
        # A key that stopped being a hash since it was typed answers with an
        # error, and is shown with its cells empty rather than failing the page.
        return [
            _row(place, name, values if isinstance(values, list) else [None] * len(fields))
            for name, values in zip(names, answers, strict=True)
        ]

    async def _sample(self, place: PlaceRef) -> list[dict[str, str]]:
        """What the first hashes of the folder hold, by name, each looked at boundedly."""
        names, _ = await self._keyspace.scan_names(
            place.database, pattern_under(place.prefix), SCAN_CEILING
        )
        direct = sorted(name for name in names if is_direct(name, place.prefix))
        hashes: list[str] = []
        for start in range(0, len(direct), SCAN_BATCH):
            chunk = direct[start : start + SCAN_BATCH]
            types = await self._keyspace.types_of(place.database, chunk)
            hashes.extend(
                name for name, kind in zip(chunk, types, strict=True) if kind == "hash"
            )
            if len(hashes) >= SAMPLE_KEYS:
                break
        chosen = hashes[:SAMPLE_KEYS]
        if not chosen:
            return []
        async with self._session.connection(place.database) as client:
            pipe = client.pipeline(transaction=False)
            for name in chosen:
                pipe.hscan(name, cursor=0, count=SAMPLE_FIELDS)
            answers = await pipe.execute(raise_on_error=False)
        return [
            {text(field): text(value) for field, value in answer[1].items()}
            for answer in answers
            if isinstance(answer, (list, tuple)) and len(answer) == 2
        ]


def key_asked(filters: Sequence[Filter], sort: Sequence[Sort]) -> str | None:
    """The key a request looks up, or nothing for the whole table.

    Equality on `key` and nothing else: every other filter and any sort would
    mean reading every hash of the folder (D172).
    """
    if sort:
        raise ValueError("A Redis table cannot be sorted")
    if not filters:
        return None
    [only, *rest] = filters
    if rest or not isinstance(only, ScalarFilter):
        raise ValueError(KEY_ONLY)
    if only.column != KEY_COLUMN or only.op != "eq":
        raise ValueError(KEY_ONLY)
    return only.value


def _page(
    table: DeclaredTable,
    rows: list[list[str | None]],
    has_more: bool,
    notice: str | None,
) -> FetchResult:
    """A page, editable as its rows (D173): every field, never the key."""
    return FetchResult(
        columns=[
            column.model_copy(
                update={
                    "editable": column.name != KEY_COLUMN,
                    "nullable": column.name != KEY_COLUMN,
                    "insertable": True,
                    "insert_required": column.name == KEY_COLUMN,
                }
            )
            for column in table_columns(table)
        ],
        rows=rows,
        has_more=has_more,
        row_handles=[table_row_handle(row[0] or "", row[1:]) for row in rows],
        update_supported=True,
        insert_supported=True,
        delete_supported=True,
        page_commands=["download", "share"],
        notice=notice,
    )


def table_fingerprint(values: Sequence[str | None]) -> str:
    """What a row's declared fields held, a lacking one marked apart from any value."""
    return fingerprint(*(_ABSENT if value is None else value for value in values))


def table_row_handle(key: str, values: Sequence[str | None]) -> str:
    """One row of a declared table as it was read: its key and its fields."""
    return encode_row_handle(
        TABLE_ROW, key, *(_ABSENT if value is None else value for value in values)
    )


def reads_as(declared: DeclaredType, value: str) -> bool:
    """Whether a typed value is one its declared column holds (D173)."""
    stripped = value.strip()
    if declared == "number":
        return _NUMBER.match(stripped) is not None
    if declared == "boolean":
        return stripped.lower() in ("true", "false")
    if declared == "datetime":
        return _is_datetime(stripped)
    return True


def guessed_type(values: Sequence[str]) -> DeclaredType:
    """The narrowest type every sampled value reads as; text when any does not."""
    present = [value.strip() for value in values if value.strip()]
    if not present:
        return "text"
    if all(_NUMBER.match(value) for value in present):
        return "number"
    if all(value.lower() in ("true", "false") for value in present):
        return "boolean"
    if all(_is_datetime(value) for value in present):
        return "datetime"
    return "text"


def _is_datetime(value: str) -> bool:
    if _DATE.match(value) is None:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _row(place: PlaceRef, name: str, values: list[Any]) -> list[str | None]:
    return [name[len(place.prefix) :], *(None if one is None else text(one) for one in values)]


def _notice(others: int, complete: bool) -> str | None:
    said: list[str] = []
    if others == 1:
        said.append("1 key of another type is not a row")
    elif others:
        said.append(f"{others:,} keys of other types are not rows")
    if not complete:
        said.append(
            f"Only {TABLE_CEILING:,} keys under this folder were read; "
            "the rest are not shown"
        )
    return ". ".join(said) or None
