"""Moving a bounded set of rows from one source into another.

The first thing in this application that names two connectors. It lives here
rather than in an adapter on purpose: an adapter knows itself and nothing else,
and asking one to read another would be the first crack in that (D43).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.catalog import CatalogNode
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch
from app.adapters.fetch import MAX_LIMIT, FetchColumn, FetchRequest
from app.adapters.protocol import SupportsCreateRelation, SupportsFetch, SupportsInsert
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.update import InsertRowsRequest, RowsInserted, ValuesRejected
from app.core.translation import say

# How many rows one move carries inside its request, in one transaction. More
# is carried by a job, a block of this many at a time (`carry_rows`).
IMPORT_CEILING = 5000

# How many rows are shown before the move is made. Enough to see whether the
# columns are paired correctly, which is the mistake that actually happens.
PREVIEW_ROWS = 20


class ColumnPair(BaseModel):
    """One column of the source, and the column of the target it fills."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str


class ImportRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The relation being written, in the connector the route addresses.
    node_id: str
    source_connector_id: str
    source_node_id: str
    columns: Annotated[list[ColumnPair], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def distinct_targets(self) -> ImportRowsRequest:
        targets = [pair.target for pair in self.columns]
        if len(targets) != len(set(targets)):
            raise ValueError(say("A target column may be filled only once"))
        return self


class ImportPreview(BaseModel):
    """The first rows as they would arrive, and nothing about the target."""

    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[list[str | None]]
    # True when the source has more rows than were shown.
    more: bool


class RowsMoved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["moved"] = "moved"
    inserted: int
    # True when the source held more rows than the ceiling allows.
    truncated: bool


class NewRelationColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type_code: str


class CreateRelationFromSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_node_id: str
    name: str = Field(min_length=1, max_length=63)
    source_connector_id: str
    source_node_id: str
    columns: Annotated[list[NewRelationColumn], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def distinct_columns(self) -> CreateRelationFromSourceRequest:
        sources = [column.source for column in self.columns]
        targets = [column.target for column in self.columns]
        if len(sources) != len(set(sources)):
            raise ValueError(say("A source column may be selected only once"))
        if len(targets) != len(set(targets)):
            raise ValueError(say("A new column may be named only once"))
        return self

    def pairs(self) -> list[ColumnPair]:
        return [
            ColumnPair(source=column.source, target=column.target)
            for column in self.columns
        ]

    def new_columns(self) -> list[NewColumn]:
        return [
            NewColumn(name=column.target, type_code=column.type_code)
            for column in self.columns
        ]


class NewRelationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_node_id: str


class ReadRows(BaseModel):
    """What came out of the source, already in the target's column order."""

    columns: list[str]
    rows: list[list[str | None]]
    truncated: bool


def _pick(
    pairs: list[ColumnPair], available: list[FetchColumn]
) -> tuple[list[str], list[int]]:
    """The target columns and where each one's value sits in a fetched row.

    Both sides are checked against what they say they have before anything is
    read: matching by position or by equal names would turn a wrong pairing
    into an import that looks right.
    """
    positions = {column.name: index for index, column in enumerate(available)}
    targets: list[str] = []
    indexes: list[int] = []
    for pair in pairs:
        index = positions.get(pair.source)
        if index is None:
            raise ValueError(
                say('The source has no column "{column}"', column=pair.source)
            )
        targets.append(pair.target)
        indexes.append(index)
    return targets, indexes


async def read_rows(
    adapter: SupportsFetch,
    node_id: str,
    pairs: list[ColumnPair],
    ceiling: int,
) -> ReadRows:
    """Read up to `ceiling` rows, mapped, paging the source at its own limit.

    Truncation is reported rather than refused: a file with more rows than the
    ceiling is exactly the case this exists for, and saying nothing would leave
    the reader believing the whole of it arrived.
    """
    page_size = min(MAX_LIMIT, ceiling)
    rows: list[list[str | None]] = []
    targets: list[str] = []
    indexes: list[int] = []
    more = False
    offset = 0
    while len(rows) < ceiling:
        page = await adapter.fetch(
            FetchRequest(node_id=node_id, limit=page_size, offset=offset)
        )
        if offset == 0:
            targets, indexes = _pick(pairs, page.columns)
        for row in page.rows:
            if len(rows) == ceiling:
                more = True
                break
            rows.append([row[index] for index in indexes])
        if not page.has_more:
            break
        if len(rows) == ceiling:
            more = True
            break
        offset += len(page.rows)
    if not targets:
        # An empty source still has to say which columns it has, so this is
        # only reachable when the first page came back with none at all.
        targets, indexes = _pick(pairs, [])
    return ReadRows(columns=targets, rows=rows, truncated=more)


class SourceTooLarge(Exception):
    """A new relation would hold only the first part of its source."""


async def create_from_source(
    target: SupportsCreateRelation,
    source: SupportsFetch,
    request: CreateRelationFromSourceRequest,
) -> RelationCreated | ValuesRejected:
    """Create one relation holding the whole of a bounded source (D45).

    Refused rather than truncated: a new table made from only the first part
    of one would carry a false identity.
    """
    read = await read_rows(
        source, request.source_node_id, request.pairs(), IMPORT_CEILING
    )
    if read.truncated:
        raise SourceTooLarge
    return await target.create_relation(
        CreateRelationRequest(
            parent_node_id=request.parent_node_id,
            name=request.name,
            columns=request.new_columns(),
            rows=read.rows,
        )
    )


async def insert_from_source(
    target: SupportsInsert, source: SupportsFetch, request: ImportRowsRequest
) -> tuple[RowsInserted | ValuesRejected, bool]:
    """Insert up to the ceiling of a source into one relation, and whether the
    rest was cut off (D43)."""
    read = await read_rows(
        source, request.source_node_id, request.columns, IMPORT_CEILING
    )
    if not read.rows:
        return RowsInserted(inserted=0), False
    result = await target.insert_rows(
        InsertRowsRequest(node_id=request.node_id, columns=read.columns, rows=read.rows)
    )
    return result, read.truncated


BlockWriter = Callable[
    [list[str], list[list[str | None]]], Awaitable[RowsInserted | ValuesRejected]
]


class BlockRefused(Exception):
    """A block the target would not take, its cells counted from the source's
    first row rather than from the block's."""

    def __init__(self, rejected: ValuesRejected) -> None:
        super().__init__("values rejected")
        self.rejected = rejected


async def exceeds_ceiling(source: SupportsFetch, node_id: str) -> bool:
    """Whether the source holds more rows than one request carries.

    One row read past the ceiling, which every source answers without
    counting the rest.
    """
    page = await source.fetch(FetchRequest(node_id=node_id, limit=1, offset=IMPORT_CEILING))
    return bool(page.rows)


async def carry_rows(
    source: SupportsFetch,
    node_id: str,
    pairs: list[ColumnPair],
    write: BlockWriter,
    arrived: Callable[[int], Awaitable[None]],
) -> int:
    """Every row of a source, written a block at a time; how many arrived.

    Each block is its own transaction, so what arrived before a refusal, a
    failure or a Stop stays (a job's answer says how much). A block the target
    refuses ends the carrying with its cells, numbered from the source's
    first row. Paged by offset at the source's own limit, as `read_rows` is.
    """
    block: list[list[str | None]] = []
    targets: list[str] = []
    indexes: list[int] = []
    done = 0
    offset = 0
    first = True

    async def flush() -> None:
        nonlocal done
        result = await write(targets, block)
        if isinstance(result, ValuesRejected):
            raise BlockRefused(
                ValuesRejected(
                    cells=[
                        cell.model_copy(update={"row": cell.row + done})
                        for cell in result.cells
                    ]
                )
            )
        done += len(block)
        block.clear()
        await arrived(done)

    while True:
        page = await source.fetch(
            FetchRequest(node_id=node_id, limit=MAX_LIMIT, offset=offset)
        )
        if first:
            targets, indexes = _pick(pairs, page.columns)
            first = False
        for row in page.rows:
            block.append([row[index] for index in indexes])
            if len(block) == IMPORT_CEILING:
                await flush()
        if not page.has_more or not page.rows:
            break
        offset += len(page.rows)
    if block:
        await flush()
    return done


def into_relation(target: SupportsInsert, node_id: str) -> BlockWriter:
    """Blocks written into a relation that is there."""

    async def write(columns: list[str], rows: list[list[str | None]]) -> RowsInserted | ValuesRejected:
        return await target.insert_rows(
            InsertRowsRequest(node_id=node_id, columns=columns, rows=rows)
        )

    return write


class NewRelationBlocks:
    """Blocks of which the first makes the relation, with its rows, and the
    rest are added to it."""

    def __init__(
        self,
        target: SupportsCreateRelation,
        inserting: SupportsInsert,
        request: CreateRelationFromSourceRequest,
    ) -> None:
        self._target = target
        self._inserting = inserting
        self._request = request
        self.node: CatalogNode | None = None

    async def write(
        self, columns: list[str], rows: list[list[str | None]]
    ) -> RowsInserted | ValuesRejected:
        if self.node is not None:
            return await into_relation(self._inserting, self.node.id)(columns, rows)
        made = await self._target.create_relation(
            CreateRelationRequest(
                parent_node_id=self._request.parent_node_id,
                name=self._request.name,
                columns=self._request.new_columns(),
                rows=rows,
            )
        )
        if isinstance(made, ValuesRejected):
            return made
        self.node = made.node
        return RowsInserted(inserted=made.inserted)


async def paired_columns(source: SupportsFetch, node_id: str, pairs: list[ColumnPair]) -> list[str]:
    """The target names of a pairing, once the source has every column it names."""
    page = await source.fetch(FetchRequest(node_id=node_id, limit=1))
    targets, _ = _pick(pairs, page.columns)
    return targets


async def paired_batches(
    source: SupportsFetch, node_id: str, pairs: list[ColumnPair]
) -> AsyncIterator[ExportBatch]:
    """Every row of a source through a pairing, a page at a time, for a file
    written as the rows arrive (D45)."""
    offset = 0
    indexes: list[int] | None = None
    while True:
        page = await source.fetch(FetchRequest(node_id=node_id, limit=MAX_LIMIT, offset=offset))
        if indexes is None:
            _, indexes = _pick(pairs, page.columns)
        mapped = [[row[index] for index in indexes] for row in page.rows]
        for start in range(0, len(mapped), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=mapped[start : start + EXPORT_BATCH_SIZE])
        if not page.has_more or not page.rows:
            return
        offset += len(page.rows)

