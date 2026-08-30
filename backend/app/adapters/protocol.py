from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.constraints import (
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
)
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.references import FollowReferenceRequest, ReferenceTarget
from app.adapters.relation import RelationModel
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
)

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class AdapterError(Exception):
    """Failure of an adapter operation, already reduced to safe values.

    Raised instead of letting a driver exception escape: driver messages
    regularly contain the connection string together with the password.
    """

    def __init__(self, error_kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.error_kind = error_kind
        self.message = message


class NodeNotFound(Exception):
    """The id does not name anything the source holds now.

    Not an `AdapterError`: that one means the source failed, and is answered
    with 502. This is an answer rather than a failure — the node was deleted,
    or never existed — and is answered with 404. Returning None instead was
    rejected because `list_children` already fixes the meaning of an empty
    answer as "an empty node, never a failure", and a second way of saying
    "no" beside it would read ambiguously.
    """

    def __init__(self, node_id: str) -> None:
        super().__init__(f"No such node: {node_id}")
        self.node_id = node_id


class ConnectionCheckResult(BaseModel):
    """Outcome of a connection check.

    Drivers never let their own exceptions escape: the text of those regularly
    contains the connection string together with the password.
    """

    ok: bool
    message: str
    latency_ms: int | None = None
    error_kind: ErrorKind | None = None


@runtime_checkable
class DataAdapter(Protocol):
    """What every source can do, whatever it is.

    Kept to the minimum on purpose. Everything else is an optional capability
    below, because capabilities are independent: a queue has no columns, an
    object store has no SQL. A single contract that demanded all of them would
    force meaningless implementations, and a single inheritance chain would
    force them into one line — which is how the old application ended up with
    four levels of base classes.
    """

    async def check_connection(self) -> ConnectionCheckResult: ...


@runtime_checkable
class SupportsCatalog(Protocol):
    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        """Children of a catalog node; the root when node_id is None.

        Raises AdapterError for source failures and ValueError for a node_id
        the source cannot or may not reach — a path leaving the root of a file
        source, for instance. An empty list means an empty node, never a
        failure: the old application returned an empty result for both.
        """
        ...


@runtime_checkable
class SupportsNodePath(Protocol):
    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, the node itself last.

        The root of the connector is not in the answer: the root is the
        connector, and the caller already knows what it is called. A node
        lying in the root therefore answers with itself alone.

        Full nodes rather than a lighter pair of id and name: a second model
        of a node beside `CatalogNode` would let the two meanings of `name`
        drift apart, and the last element doubles as the answer to "what is
        this" — with its kind, its row estimate and everything else it knows
        about itself.

        A capability of its own rather than part of `SupportsCatalog`: a
        source whose ids are opaque handles from someone else's API may have
        no way back up at all, and would be left to either lie or give up
        having a catalog. Answering 501 is the honest third option.

        Raises NodeNotFound for an id that names nothing, AdapterError for
        source failures, and ValueError for an id the source may not reach —
        the same rule that guards list_children.
        """
        ...


@runtime_checkable
class SupportsFetch(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult:
        """Read a page of rows.

        Raises AdapterError for source failures and ValueError for a request
        that names a column the relation does not have — that check happens
        before any SQL is built.
        """
        ...


@runtime_checkable
class SupportsReferences(Protocol):
    async def follow_reference(
        self, request: FollowReferenceRequest
    ) -> ReferenceTarget:
        """Where one row's foreign key points, with the predicate built.

        Separate from `SupportsFetch` because having rows says nothing about
        having references: a delimited file has columns and no keys at all. A
        source that lists references in its fetch result implements this, and
        one that does not answers 501.

        Raises NodeNotFound when the relation or the relation it points at is
        gone, AdapterError for source failures, and ValueError for a request
        that names a reference the relation does not have or supplies values
        that are not exactly its key.
        """
        ...


@runtime_checkable
class SupportsUpdate(Protocol):
    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        """Change one cell if the row still has the fetched version."""
        ...

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        """Change a block of cells across several rows, or none of them.

        Part of the same capability rather than its own: a source that can
        version a row and change a cell in it can do so for twenty rows, and
        offering only one of the two would be a distinction with no source
        behind it.

        Answers rather than raises when a value cannot be read as its column's
        type, naming every such cell and writing nothing. Raises RowConflict
        when any row no longer holds the version it was read with.
        """
        ...


@runtime_checkable
class SupportsInsert(Protocol):
    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        """Insert one row while leaving omitted values to the source."""
        ...

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        """Insert a block of rows, or none of them.

        Part of the same capability rather than its own, for the reason
        `update_cells` is part of `SupportsUpdate`: a source that can accept a
        row can accept five thousand, and splitting them would be a
        distinction with no source behind it.

        Answers rather than raises when a value cannot be read as its column's
        type, naming those cells and writing nothing.
        """
        ...


@runtime_checkable
class SupportsDelete(Protocol):
    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        """Delete versioned rows as one all-or-nothing operation."""
        ...


@runtime_checkable
class SupportsRelationModel(Protocol):
    async def relation_model(self, node_id: str) -> RelationModel:
        """Describe one relation in full: columns, constraints, indexes.

        Raises NodeNotFound for an id that names nothing, AdapterError for
        source failures, and ValueError for an id this source may not reach.
        """
        ...


@runtime_checkable
class SupportsAddColumn(Protocol):
    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        """Add one column from the source-owned type vocabulary."""
        ...


@runtime_checkable
class SupportsDropColumn(Protocol):
    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        """Drop one exact column without an implicit cascade."""
        ...


@runtime_checkable
class SupportsRenameColumn(Protocol):
    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        """Rename one exact column while preserving its source identity."""
        ...


@runtime_checkable
class SupportsColumnDefault(Protocol):
    async def change_column_default(
        self, request: ColumnDefaultRequest
    ) -> ColumnChangeResult:
        """Set a literal column default or remove it."""
        ...


@runtime_checkable
class SupportsColumnNullability(Protocol):
    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        """Require a value in one column, or stop requiring one.

        Answers rather than raises when the rows already there contradict the
        constraint: that is a fact about the data, and the number of rows in
        the way is the useful part of it. Raises ValueError for a request that
        is wrong about the relation — an unknown column, a relation that
        cannot change columns, a column that already says what is asked — and
        AdapterError for source failures.
        """
        ...


@runtime_checkable
class SupportsColumnType(Protocol):
    async def change_column_type(
        self, request: ColumnTypeRequest
    ) -> ColumnTypeChangeResult:
        """Give one column another type from the source's published list.

        Answers rather than raises when rows hold values the target cannot
        read and the source can count them without attempting the conversion.
        Raises ValueError for a request that is wrong about the relation, for
        two types with no conversion between them, and for a refusal the
        source can name — a default that cannot be cast, a view built on the
        column. Raises AdapterError for source failures.
        """
        ...


@runtime_checkable
class SupportsIndexes(Protocol):
    """One capability for both halves, deliberately.

    Unlike adding and dropping a column, which are independent enough to be
    asked for separately, an index that can be made and not unmade is a trap:
    the user is offered a way to build something they cannot remove.
    """

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        """Index the named columns, letting the source name the index.

        Answers rather than raises when a unique index is asked for and the
        rows already repeat. Raises ValueError for a request that is wrong
        about the relation — an unknown column or method, a method that cannot
        do what was asked — and AdapterError for source failures.
        """
        ...

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        """Drop one index of this relation, without an implicit cascade.

        Raises ValueError for an index this relation does not have and for one
        that belongs to a constraint, which is dropped through the constraint.
        """
        ...


@runtime_checkable
class SupportsConstraints(Protocol):
    """One capability for both halves, for the reason SupportsIndexes is one."""

    async def create_constraint(
        self, request: CreateConstraintRequest
    ) -> CreateConstraintResult:
        """Promise uniqueness, or a reference to another relation.

        Answers rather than raises when the rows already contradict the
        promise, with a count of what repeats or of what points at nothing.
        Raises ValueError for a request that is wrong about either relation,
        NodeNotFound when the target is gone, and AdapterError for failures.
        """
        ...

    async def drop_constraint(
        self, request: DropConstraintRequest
    ) -> ConstraintDropped:
        """Drop one constraint of this relation, without an implicit cascade."""
        ...


@runtime_checkable
class SupportsConnectionString(Protocol):
    def connection_string(self) -> str:
        """How to reach this source, in one line, for a human to copy.

        Never carries the password: it is shown on screen and pasted into
        other tools, and the one place that composes it is the one place
        already obliged to keep the password out of anything the caller sees.

        A capability rather than part of the contract because a source may
        genuinely have none — a personal directory is not addressed by a URL,
        and answering with an invented one would be worse than answering 501.
        """
        ...


@runtime_checkable
class ParsesConnectionString(Protocol):
    """A source type that can take a pasted address apart again.

    Asked of the class, not of an instance: an adapter cannot be built until
    there are options, and parsing is what produces them. The same reason
    `action_types` is a classmethod — and, as there, a classmethod rather than
    data so that `issubclass` can answer it.

    The answer is options in the shape the schema declares, discriminator
    included: which way of connecting a string describes is the driver's
    inference. A form that read it off the presence of a substring would be
    the `isFieldShowing` of the old application.

    Raises ValueError for a string the driver cannot read as an address. What
    counts as one is the driver's own rule; nothing here inspects the text.
    """

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]: ...


@runtime_checkable
class DescribesDraft(Protocol):
    """A source type that can address a form that is not filled in yet.

    The mirror of `ParsesConnectionString`, and a classmethod for the same
    reason: there is no valid options object while a form is half-typed, which
    is precisely the moment this is asked. `SupportsConnectionString` cannot
    answer it — that one is a method on a built adapter.

    It exists so that the client never has to compose an address of its own.
    Defaults put a host and a port in the form before anything is typed, and
    they already make an address worth showing; a screen that wrote it itself
    would be a second implementation of the driver's grammar and would differ
    from it in the quoting first.

    The values are whatever the form holds — unvalidated, of whatever types
    JSON produced — so an implementation reads what it recognises and ignores
    the rest. None means there is not enough yet to write anything, which is
    a different answer from a source having no address at all: that one is
    still the absence of `SupportsConnectionString`.
    """

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None: ...
