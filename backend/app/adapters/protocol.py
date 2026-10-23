from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

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
from app.adapters.content import (
    BoundedContentPreview,
    ContentRequest,
    ContentResult,
    ContentStream,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    UpdateContentRequest,
)

# Re-exported: every driver names the kind through this module.
from app.adapters.errors import ErrorKind as ErrorKind
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.hypertable_design import HypertableDesignState
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.references import (
    ArrivingReference,
    FollowReferenceRequest,
    ReferenceTarget,
)
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.search import (
    ExtractedText,
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.summary import NodeSummary
from app.adapters.table_copy import (
    Arrived,
    CopiedTable,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
    TableRows,
)
from app.adapters.table_design import (
    TableDesignOptions,
    TablePlan,
    TablePlanRequest,
)
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
from app.core.translation import say


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
        super().__init__(say("No such node: {node}", node=node_id))
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
    force them into one line of ever deeper base classes.
    """

    async def check_connection(self) -> ConnectionCheckResult: ...


@dataclass(frozen=True)
class BackupProgram:
    """How to back this source up, or put a backup back into it.

    The image and the arguments, and nothing about where either runs: a source
    knows that PostgreSQL is dumped by `pg_dump` of its own major version, and
    knows nothing about containers. What runs it is the job (D87).

    The password is in the environment rather than in the arguments, because
    arguments are visible to everything on the machine that can list
    processes, and because that is the way the program itself documents.
    """

    image: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]


class BackupAvailability(BaseModel):
    available: bool
    reason: str | None = None


@runtime_checkable
class SupportsBackup(Protocol):
    """A source that can be copied out whole and put back.

    Two methods rather than one, because the two are not symmetric: a dump is
    a read and a restore destroys what is there first. Both answer with a
    program to run, so a source that cannot say what program would do it does
    not implement this and the routes answer 501 — the rule every other
    capability follows.
    """

    async def backup_availability(self) -> BackupAvailability: ...

    async def backup_program(self, *, into: str) -> BackupProgram: ...

    async def restore_program(self, *, from_file: str) -> BackupProgram: ...

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram: ...

    def validate_restore_inventory(self, lines: Sequence[str]) -> None: ...

    def restore_archive_reason(self, head: bytes) -> str | None:
        """Why a file beginning with these bytes is not a backup this source
        restores, or None when it may be one.

        Asked before the file is staged, so a file of another kind is refused
        before any program is fetched or run. The inventory then says whether
        it is a whole one.
        """
        ...


@runtime_checkable
class SupportsSampleData(Protocol):
    """A source this application can fill with something worth looking at.

    Only for a source this server started itself: a database somebody asked
    for is empty, and an empty database demonstrates nothing. What goes in is
    the driver's own — this repository's script, shipped beside it — so
    nothing a client sends reaches a statement here.

    The answer is one line saying what is now there, which is what the job
    reports as its result.
    """

    async def install_sample_data(self) -> str: ...


@runtime_checkable
class SupportsCatalog(Protocol):
    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        """Children of a catalog node; the root when node_id is None.

        Raises AdapterError for source failures and ValueError for a node_id
        the source cannot or may not reach — a path leaving the root of a file
        source, for instance. An empty list means an empty node, never a
        failure, so a broken source cannot pass for an empty one.
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
class SupportsContent(Protocol):
    async def read_content(self, request: ContentRequest) -> ContentResult:
        """Read one bounded, content-native representation of a node.

        Separate from ``SupportsFetch``: opening a JSON document or a text
        file says nothing about rows, columns, sorting or filtering. Raises
        ValueError when the node or representation cannot be read and
        AdapterError for source failures.
        """
        ...


@runtime_checkable
class SupportsContentPreview(Protocol):
    async def preview_content(
        self, request: ContentRequest
    ) -> BoundedContentPreview:
        """Return verified bytes already below the representation's hard bound."""
        ...


@runtime_checkable
class SupportsContentStream(Protocol):
    async def open_content_stream(self, request: ContentRequest) -> ContentStream:
        """Verify a node's bytes and answer with a reader over byte ranges.

        Separate from `SupportsContentPreview`, which returns bytes already
        held whole: a recording is asked for by range and is never held (D52).
        Raises ValueError when the node or representation cannot be streamed
        and AdapterError for source failures.
        """
        ...


@runtime_checkable
class SupportsContentEdit(Protocol):
    async def read_editor_content(
        self, request: EditorContentRequest
    ) -> EditorContent:
        """Read bounded UTF-8 source together with an opaque version."""
        ...

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        """Atomically replace source only while its opaque version still matches."""
        ...


@runtime_checkable
class SupportsExport(Protocol):
    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        """Stream every matching row in bounded batches.

        Separate from `SupportsFetch`: paging until a source stops is neither
        one snapshot nor necessarily a streaming operation. The iterator
        raises AdapterError for source failures and ValueError for identifiers
        or query operations the source refuses.
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
class SupportsArrivingReferences(Protocol):
    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        """The keys of other relations that land on this one (D110).

        Separate from `SupportsReferences` because the two are different
        questions of a source: reading this relation's own keys is reading its
        definition, while finding the keys that point at it is a search of
        everything else. A source that can do the first and not the second
        answers 501 to this and stays useful.

        Following one is `follow_reference` with `direction="incoming"`, so a
        source that implements this implements that direction too.

        Raises NodeNotFound for a relation that is gone and AdapterError for
        source failures.
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
class SearchesContents(Protocol):
    """A source that can look inside its own files, not only at their names.

    Separate from `SupportsNodeSearch` because it is a different promise and a
    different cost: reading every file below a folder is minutes where matching
    a name is milliseconds, and a client has to be able to say so before it
    starts one. A source that lists names and cannot read them answers 501,
    and the client never offers the gesture.
    """

    async def search_contents(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        """Find nodes whose contents hold the words, bounded the same ways.

        Every word on one line, case-folded. Raises what `search_nodes`
        raises, for the same reasons.
        """
        ...


@runtime_checkable
class SupportsNodeSearch(Protocol):
    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        """Find nodes by name below one level, bounded, the best classes first.

        Separate from `SupportsCatalog` because walking a whole subtree is a
        different promise from listing one level: a source whose ids are
        handles from someone else's API can list and cannot search.

        Every word of the query in the name, case-folded, in any order (D202).
        A source that meets more matches than the limit keeps the best-classed
        ones and says it is not complete; `bounds` adds a clock and a stop to
        its own ceilings, checked between entries, and a search the clock
        stopped says so in its notice. Without bounds a source keeps only its own.

        Raises NodeNotFound for a level that is gone, ValueError for a node
        this source may not reach, for one that is not a level and for a query
        it cannot use, and AdapterError for source failures.
        """
        ...


@runtime_checkable
class EnumeratesNames(Protocol):
    """A source whose every name can be read for a kept list (D213).

    Its own promise rather than `SupportsNodeSearch` with no words: a search
    keeps the best few and stops, a pass reads everything once, in batches,
    and must say which parts it could not read so that nothing kept under them
    is deleted.
    """

    def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every name, at most `limit`, in batches, until `bounds` is over.

        A source that stops at the limit or the clock says so in the last
        batch's `notice`. Raises AdapterError when it cannot begin at all.
        """
        ...


@runtime_checkable
class ExtractsText(Protocol):
    """A source whose files' text can be read whole for kept contents (D218).

    The same rule as `SearchesContents` about what is text, so the kept and the
    live search never disagree about a file; the ceiling is the storage's.
    """

    async def extract_text(self, node_id: str, bounds: SearchBounds) -> ExtractedText:
        """The lines of one file. Raises NodeNotFound for one that is gone,
        ValueError for a node this source may not reach, AdapterError for
        source failures."""
        ...


@runtime_checkable
class SearchesColumns(Protocol):
    """A source whose relations are found by their columns and comments (S8).

    Its own promise, so only a source that can answer it is given the cell: a
    tree of files has no columns to look through without opening every file.
    """

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        """Relations a column name, a column's comment or their own comment holds
        the words in; the matched text is each match's excerpt.

        Raises what `search_nodes` raises, for the same reasons.
        """
        ...


@runtime_checkable
class StatesSearchCost(Protocol):
    """What a search of this type costs, stated without asking anybody (D200).

    A classmethod: the search plans before it asks, and a dead server must not
    hold the plan. A type that does not state it is costly.
    """

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost: ...


@runtime_checkable
class SupportsNodeSummary(Protocol):
    async def node_summary(self, node_id: str) -> NodeSummary:
        """Describe one node itself: its facts, and what its format states.

        Separate from `SupportsRelationModel` because the two answer different
        questions about different nodes: a relation model is the shape of
        something tabular, and this is what a node is — which a folder, a
        recording and an opaque binary all have.

        Raises NodeNotFound for an id that names nothing, AdapterError for
        source failures, and ValueError for an id this source may not reach.
        """
        ...


@runtime_checkable
class SupportsCreateRelation(Protocol):
    """One capability for both halves, because one is useless without the other.

    A screen cannot offer a new relation without knowing what a container will
    accept it with, and a source that publishes that and then refuses to
    create anything has said nothing. Unlike `SupportsIndexes`, which is one
    capability so that what can be made can also be unmade, this pairs a
    question with the command it exists to prepare.
    """

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        """What this container will accept a new relation with.

        Answers rather than raises when the container admits none — a schema
        the server owns is a real schema, and saying why is more use than
        pretending it is not there. Raises NodeNotFound for an id that names
        nothing, AdapterError for source failures, and ValueError for an id
        this source may not reach.
        """
        ...

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        """Create one relation from the published type vocabulary, with its rows.

        The relation and the rows arrive together or neither does: creating a
        relation whose rows were refused would leave behind something nobody
        asked for and nothing here can drop.

        Answers rather than raises when a value cannot be read as its column's
        type, naming those cells and creating nothing. Raises ValueError for a
        request the container refuses — a taken name, an unknown type code, a
        container that admits no relations — and AdapterError for failures.
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
class SupportsHypertableDesign(Protocol):
    """A source that can read a hypertable into the design its editor shows (D207).

    Reading only: the change is the `timescale_design_hypertable` action, so
    access, review and cache invalidation stay where every other change keeps
    them (D9).
    """

    async def hypertable_design_state(self, node_id: str) -> HypertableDesignState:
        """The design as it is now, or the reason this table cannot be edited.

        Answers rather than raises for a table that is not a hypertable this
        editor works on. Raises NodeNotFound for an id that names nothing and
        AdapterError for source failures.
        """
        ...


@runtime_checkable
class SupportsTableDesign(Protocol):
    """A source that can be asked what a whole new table would become.

    Two questions and no third: creating is done through the `create_table`
    action, so access, refusals, cache invalidation and which branch of the
    catalog to re-read stay where every other change keeps them (D9). A
    capability that also created would be a second door into the same DDL.
    """

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What this destination will accept a designed table with.

        Answers rather than raises when it will accept none, the way
        `new_relation_options` does. Raises NodeNotFound for an id that names
        nothing and AdapterError for source failures.
        """
        ...

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        """The statements this definition would become, without running them.

        Answers rather than raises when the definition is wrong: which object
        is at fault and why is the useful part, and an editor showing it needs
        every problem rather than the first. Raises ValueError when the request
        is wrong about the destination itself.
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
class SupportsTableCopy(Protocol):
    """Tables copied with their structure, at both ends of the copy (D182).

    One capability for both ends: a copy is made from a description only a
    source of the same dialect can read, so a source that can describe its
    tables and not make them, or the other way round, would be half a copy.
    """

    @property
    def table_copy_dialect(self) -> str:
        """Whose words the description is in; both ends must share them."""
        ...

    @property
    def table_copy_database(self) -> str:
        """Which database this is: two ends that say the same share one, and
        a link of the copy may point at an original there."""
        ...

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        """Each table as a copy of it would be made, in the order asked.

        A node that cannot be copied is described with its refusal. Raises
        NodeNotFound for an id that names nothing and AdapterError for
        source failures.
        """
        ...

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        """Each name if nothing in the place holds it, or the nearest free
        `…_copy` one; no two of the answers the same."""
        ...

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        """The statements the copy would run, and its problems; runs nothing."""
        ...

    def reading_tables(self) -> AbstractAsyncContextManager[TableRows]:
        """The rows of any of this source's tables, in one snapshot."""
        ...

    async def carry_table_copy(
        self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived
    ) -> None:
        """Plan the copy again and run it as one transaction.

        Raises ValueError with a safe sentence for a plan with problems and
        for anything the destination refuses, having changed nothing.
        """
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
    a second, weaker parser of the same string.

    Raises ValueError for a string the driver cannot read as an address. What
    counts as one is the driver's own rule; nothing here inspects the text.
    """

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]: ...


@runtime_checkable
class ComposesSecretUrl(Protocol):
    """A source type that can write its address with the password in it.

    Named so that the one thing it does differently is the first thing read.
    There is exactly one caller — the window that shows a started service's
    credentials once (D89) — because a person who has just been given a
    password wants to paste an address rather than assemble one.

    Everything else composes through `SupportsConnectionString`, which is
    obliged to leave the password out. Two methods rather than a flag, so that
    "does this string carry a secret" is answered by which one was called.

    A classmethod for the reason `draft_connection_string` is one: the values
    are the ones the caller assembled — a published port on the host, rather
    than the container name the connector holds — so there is no instance to
    ask.
    """

    @classmethod
    def connection_url_with_password(
        cls, options: Mapping[str, Any]
    ) -> str | None: ...


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
