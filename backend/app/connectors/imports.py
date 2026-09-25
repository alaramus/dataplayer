"""Moving a bounded set of rows from one source into another.

The first thing in this application that names two connectors. It lives here
rather than in an adapter on purpose: an adapter knows itself and nothing else,
and asking one to read another would be the first crack in that (D43).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.fetch import MAX_LIMIT, FetchColumn, FetchRequest
from app.adapters.protocol import SupportsCreateRelation, SupportsFetch, SupportsInsert
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.update import InsertRowsRequest, RowsInserted, ValuesRejected

# How many rows one move may carry. More than this is a durable job with
# progress and cancellation, which is Phase 4; a larger number here would only
# move the point at which the request times out.
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
            raise ValueError("A target column may be filled only once")
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
            raise ValueError("A source column may be selected only once")
        if len(targets) != len(set(targets)):
            raise ValueError("A new column may be named only once")
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
            raise ValueError(f'The source has no column "{pair.source}"')
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
