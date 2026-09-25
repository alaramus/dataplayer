"""Rows pasted into another connection: a new table, or into a ticked one (D166).

What runs is D43's and D45's own work, from `imports`: the same bounded read,
the same check of every value, the same transaction.
"""

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchColumn, FetchRequest
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsCreateRelation,
    SupportsFetch,
    SupportsInsert,
)
from app.adapters.update import ValuesRejected
from app.connectors import imports
from app.connectors.paste.files import TransfersFiles
from app.connectors.paste.kinds import counted, offered, refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    PasteKindName,
    PasteOffer,
    PastePair,
    PasteResult,
    PasteRun,
    PasteWorkflow,
)
from app.core.access import Access

NOT_ROWS = "This cannot be read as rows"


async def columns_of(source: DataAdapter, node_ids: list[str]) -> list[FetchColumn] | str:
    """The columns of the one node on the clipboard, or why it has none."""
    if not isinstance(source, SupportsFetch):
        return NOT_ROWS
    if len(node_ids) != 1:
        return "Paste one table at a time"
    return await _columns(source, node_ids[0], gone="The copied node no longer exists")


async def _columns(source: SupportsFetch, node_id: str, *, gone: str) -> list[FetchColumn] | str:
    try:
        page = await source.fetch(FetchRequest(node_id=node_id, limit=1))
    except NodeNotFound:
        return gone
    except ValueError:
        return NOT_ROWS
    except AdapterError:
        return "The connection is unavailable"
    return page.columns or NOT_ROWS


def rejected(result: ValuesRejected) -> str:
    """The first value that could not cross, and how many more there are."""
    first = result.cells[0]
    more = len(result.cells) - 1
    said = f"{first.value!r} cannot be read by {first.column} (row {first.row + 1})"
    return said if more == 0 else f"{said}, and {counted(more, 'other value')}"


class _Rows:
    """A folder is not a destination: it takes a file as it is (D161) or a
    table as CSV (D165), and a second answer beside those would be a second
    meaning for the same Paste."""

    name: PasteKindName
    title: str
    workflow: PasteWorkflow
    destination_requires: Access
    mode: ClipboardMode = "copy"
    converts = True
    can_replace = False
    source_requires: Access = "read"
    changes_source = False

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsFetch)

    def _takes_rows(self, destination: DataAdapter) -> bool:
        return not isinstance(destination, TransfersFiles)

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        found = await columns_of(source, node_ids)
        if isinstance(found, str):
            return Availability(available=False, reason=found)
        return Availability(available=True)


class RowsNewRelation(_Rows):
    name: PasteKindName = "rows_new_relation"
    title = "Create a table"
    workflow: PasteWorkflow = "new-relation"
    # What D45 asks of the place the table is made in.
    destination_requires: Access = "structure"

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsCreateRelation)
            and self._takes_rows(destination)
        )

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        columns = await columns_of(source, pair.source_node_ids)
        if isinstance(columns, str):
            return refused(self, columns)
        if not isinstance(destination, SupportsCreateRelation):
            return refused(self, "This connection cannot create tables")
        try:
            options = await destination.new_relation_options(
                pair.destination_node_id or ""
            )
        except (NodeNotFound, ValueError):
            return refused(self, "Choose the schema the table goes in")
        except AdapterError:
            return refused(self, "The connection is unavailable")
        if not options.supported:
            return refused(self, options.reason or "This place cannot take a new table")
        return offered(self, available=True, source_columns=columns)

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        if not isinstance(source, SupportsFetch) or not isinstance(
            destination, SupportsCreateRelation
        ):
            raise ActionRefused("not_applicable", "These connections cannot create a table")
        if len(request.source_node_ids) != 1:
            raise ActionRefused("not_applicable", "Paste one table at a time")
        if request.name is None or not request.columns:
            raise ActionRefused("not_applicable", "Name the table and choose its columns")
        if any(column.type_code is None for column in request.columns):
            raise ActionRefused("not_applicable", "Choose a type for every column")
        creation = imports.CreateRelationFromSourceRequest(
            parent_node_id=request.destination_node_id or "",
            name=request.name.strip(),
            source_connector_id=str(request.source_connector_id),
            source_node_id=request.source_node_ids[0],
            columns=[
                imports.NewRelationColumn(
                    source=column.source,
                    target=column.target,
                    type_code=column.type_code or "",
                )
                for column in request.columns
            ],
        )
        try:
            result = await imports.create_from_source(destination, source, creation)
        except imports.SourceTooLarge:
            raise ActionRefused(
                "too_large",
                f"A new table may be filled with at most {imports.IMPORT_CEILING} rows",
            ) from None
        if isinstance(result, ValuesRejected):
            raise ValueError(rejected(result))
        return PasteResult(
            kind=self.name,
            message=f"{result.node.name} created with {counted(result.inserted, 'row')}",
            written=1,
            rows=result.inserted,
            name=result.node.name,
            reload_node_ids=[request.destination_node_id],
        )


class RowsIntoRelation(_Rows):
    name: PasteKindName = "rows_into_relation"
    title = "Add rows to a table"
    workflow: PasteWorkflow = "into-relation"
    # What D43 asks of the relation written.
    destination_requires: Access = "write"

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsInsert)
            and isinstance(destination, SupportsFetch)
            and self._takes_rows(destination)
        )

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        if pair.target_node_id is None:
            return refused(self, "Tick the table the rows go into")
        columns = await columns_of(source, pair.source_node_ids)
        if isinstance(columns, str):
            return refused(self, columns)
        if not isinstance(destination, SupportsFetch):
            return refused(self, "This connection cannot take rows")
        target = await _columns(
            destination, pair.target_node_id, gone="The ticked table no longer exists"
        )
        if isinstance(target, str):
            return refused(self, "The ticked node cannot take rows")
        insertable = [column for column in target if column.insertable]
        if not insertable:
            return refused(self, "The ticked table takes no rows")
        return offered(
            self, available=True, source_columns=columns, target_columns=insertable
        )

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        if not isinstance(source, SupportsFetch) or not isinstance(
            destination, SupportsInsert
        ):
            raise ActionRefused("not_applicable", "These connections cannot move rows")
        if len(request.source_node_ids) != 1:
            raise ActionRefused("not_applicable", "Paste one table at a time")
        if request.target_node_id is None:
            raise ActionRefused("not_applicable", "Tick the table the rows go into")
        if not request.columns:
            raise ActionRefused("not_applicable", "Pair at least one column")
        importing = imports.ImportRowsRequest(
            node_id=request.target_node_id,
            source_connector_id=str(request.source_connector_id),
            source_node_id=request.source_node_ids[0],
            columns=[
                imports.ColumnPair(source=column.source, target=column.target)
                for column in request.columns
            ],
        )
        result, truncated = await imports.insert_from_source(
            destination, source, importing
        )
        if isinstance(result, ValuesRejected):
            raise ValueError(rejected(result))
        message = f"{counted(result.inserted, 'row')} added"
        if truncated:
            message += f", the first {imports.IMPORT_CEILING} of the source"
        return PasteResult(
            kind=self.name,
            message=message,
            written=result.inserted,
            rows=result.inserted,
            reload_node_ids=[request.destination_node_id],
        )
