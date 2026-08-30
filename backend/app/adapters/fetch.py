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


class DownloadPageRequest(FetchRequest):
    """The bounded page to save, in the column order visible in the grid."""

    title: str = Field(min_length=1, max_length=255)
    columns: list[str] = Field(min_length=1)


class FetchColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: ColumnType
    sortable: bool = False
    filter_operators: list[FilterOp] = Field(default_factory=list)
    editable: bool = False
    nullable: bool = False
    insertable: bool = False
    insert_required: bool = False
    has_default: bool = False


class FetchResult(BaseModel):
    """Rows as arrays, with the columns listed once.

    Repeating column names in every row multiplies the size of a wide result,
    and the grid addresses cells by index anyway.
    """

    columns: list[FetchColumn]
    model_config = ConfigDict(extra="forbid")

    rows: list[list[str | None]]
    has_more: bool
    row_handles: list[str | None] = Field(default_factory=list)
    update_supported: bool = False
    update_reason: str | None = None
    insert_supported: bool = False
    insert_reason: str | None = None
    delete_supported: bool = False
    delete_reason: str | None = None


def as_read_only(result: FetchResult, reason: str) -> FetchResult:
    """The same page, with everything that would change it withdrawn.

    A caller who may read a connection and no more is told so through the
    channel a source already uses to say what it cannot do (D2d), rather than
    by a client knowing the rule: the grid draws an editable cell from
    `editable` and offers insert and delete from the three flags, so
    withdrawing them here is the same statement in the same place.
    """
    return result.model_copy(
        update={
            "columns": [
                column.model_copy(update={"editable": False, "insertable": False})
                for column in result.columns
            ],
            "update_supported": False,
            "update_reason": reason,
            "insert_supported": False,
            "insert_reason": reason,
            "delete_supported": False,
            "delete_reason": reason,
        }
    )
