from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.relation import ColumnType

ScalarFilterOp = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "starts_with",
]
FilterOp = ScalarFilterOp | Literal["in", "is_null", "is_not_null"]

MAX_LIMIT = 1000


class ScalarFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: ScalarFilterOp
    value: str


class InFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Literal["in"]
    values: list[str] = Field(min_length=1)


class NullFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Literal["is_null", "is_not_null"]


# A closed set. In the old application a client could pass a raw SQL fragment
# through `sql_conditions`, guarded only by a blacklist.
Filter = Annotated[
    ScalarFilter | InFilter | NullFilter,
    Field(discriminator="op"),
]


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
    model_config = ConfigDict(extra="forbid")

    name: str
    type: ColumnType
    sortable: bool = False
    filter_operators: list[FilterOp] = Field(default_factory=list)


class FetchResult(BaseModel):
    """Rows as arrays, with the columns listed once.

    Repeating column names in every row multiplies the size of a wide result,
    and the grid addresses cells by index anyway.
    """

    columns: list[FetchColumn]
    model_config = ConfigDict(extra="forbid")

    rows: list[list[str | None]]
    has_more: bool
