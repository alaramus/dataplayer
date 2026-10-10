from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.relation import ColumnType
from app.adapters.row_commands import PickedRowsAction, RowCommand

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

# What the toolbar over a page offers beyond reading it: take a copy away,
# draw it, address it, make a relation of it, or write SQL about the node it
# came from. A closed vocabulary rather than a flag each, because they are one
# statement — what this page is for — and a source that withdraws one usually
# withdraws several.
PageCommand = Literal[
    "download",
    "chart",
    "share",
    "create_relation",
    "query",
]

PAGE_COMMANDS: tuple[PageCommand, ...] = (
    "download",
    "chart",
    "share",
    "create_relation",
    "query",
)


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


class FetchReference(BaseModel):
    """One foreign key of the fetched relation, as the grid needs to see it.

    A whole key rather than a mark on each of its columns: the old application
    copied a constraint onto every column it touched, which split a composite
    foreign key into independent one-column links. `columns` is the key in its
    own order, and `name` is the source's own name for it — the handle the
    caller sends back to follow it, never a predicate the caller composes.

    `target_title` is for the tooltip and nothing else. The identity of the
    target is not in the answer at all: it arrives from the source when the
    reference is actually followed, so there is no id here for a client to be
    tempted to take apart (D21).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str] = Field(min_length=1)
    target_title: str


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
    # Empty for a source that has no such notion at all; a source that has
    # references but no capability to follow them cannot arise, because the
    # same module answers both.
    references: list[FetchReference] = Field(default_factory=list)
    update_supported: bool = False
    update_reason: str | None = None
    insert_supported: bool = False
    insert_reason: str | None = None
    delete_supported: bool = False
    delete_reason: str | None = None
    # Filled by the connector route from the facade's optional capability.
    # A capability belongs to the composed adapter, not to the fetch module
    # that produced this page.
    export_supported: bool = False
    export_reason: str | None = None
    # Whether one of these rows can be opened on its own, read downwards
    # (D111). True for anything a source holds; false where a "row" is a line
    # of an answer rather than a thing — a report has no relation model, no
    # key and no reference to follow (D55), so the panel would be these same
    # values in a column and nothing else.
    record_supported: bool = True
    record_reason: str | None = None
    # How often the source thinks this relation is worth reading again, when
    # it has an opinion. A list of server processes is about what is happening
    # this second; a table of invoices is not, and says nothing (D67).
    refresh_seconds: int | None = None
    # What may be done with this page beyond reading it. Everything, unless
    # the source says otherwise: a page is ordinarily somebody's own data, and
    # only a source knows when it is not (D72).
    page_commands: list[PageCommand] = Field(
        default_factory=lambda: list(PAGE_COMMANDS)
    )
    # What this relation offers to do to rows somebody selects. Filled by the
    # route from the composed adapter's capability, like export above (D70).
    row_commands: list[RowCommand] = Field(default_factory=list)
    # What this relation offers to do, after a review, to rows somebody picks
    # (D209). Filled by the route the same way.
    picked_rows_actions: list[PickedRowsAction] = Field(default_factory=list)


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
