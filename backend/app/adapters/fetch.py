from typing import Any, Literal

from pydantic import BaseModel, Field

# A closed set. In the old application a client could pass a raw SQL fragment
# through `sql_conditions`, guarded only by a blacklist.
FilterOp = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "starts_with",
    "in",
    "is_null",
    "is_not_null",
]

# Operators that take no value at all.
NULLARY_OPS: frozenset[str] = frozenset({"is_null", "is_not_null"})

MAX_LIMIT = 1000


class Filter(BaseModel):
    column: str
    op: FilterOp
    value: Any | None = None


class Sort(BaseModel):
    column: str
    descending: bool = False


class FetchRequest(BaseModel):
    # The same opaque identifier the catalog produces; only the adapter that
    # issued it knows how to read it.
    node_id: str
    # There is no unlimited option: the old application defaulted to -1.
    limit: int = Field(default=100, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    filters: list[Filter] = Field(default_factory=list)
    sort: list[Sort] = Field(default_factory=list)


class FetchColumn(BaseModel):
    name: str
    data_type: str


class FetchResult(BaseModel):
    """Rows as arrays, with the columns listed once.

    Repeating column names in every row multiplies the size of a wide result,
    and the grid addresses cells by index anyway.
    """

    columns: list[FetchColumn]
    rows: list[list[Any]]
    has_more: bool
    # Not every source can order or filter: a file has no index, and the
    # columns of a CSV have no types. Stating it in the answer keeps the grid
    # from offering what the source cannot do, without the frontend ever
    # branching on the type of the source.
    sortable: bool = True
    filterable: bool = True
