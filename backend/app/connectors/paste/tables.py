"""Tables copied with their structure, into a schema anywhere (D182).

The ticked tables, what their links bring with them and what the window
added, resolved here into one set; the destination composes and runs the copy,
and the source reads every table's rows in one snapshot.
"""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.adapters.actions import ActionRefused
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsTableCopy,
)
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    CopiedLink,
    CopiedTable,
    CopyLoad,
    CopyProblem,
    CopyStatement,
    LinkDecision,
    TableCopyRequest,
    TableCopyTarget,
)
from app.connectors.paste.kinds import counted, offered, refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    Foreseen,
    PairEnd,
    PasteColumn,
    PasteKindName,
    PasteOffer,
    PastePair,
    PasteRun,
    PasteWorkflow,
    TableLinks,
    TablesChoice,
)
from app.connectors.paste.transfer import (
    Transfer,
    TransferItem,
    TransferPlan,
    TransferReport,
    TransferStopped,
)
from app.core.access import Access

GONE = "A copied table no longer exists"
UNAVAILABLE = "The copied connection is unavailable"
CHANGED = "The tables changed since the copy was planned; paste again"

Origin = Literal["ticked", "linked", "added"]


class CopiedRow(BaseModel):
    """One table of the copy, as the window lists it."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    name: str
    # Ticked by the person, brought in by a link, or added in the window.
    origin: Origin
    rows: int | None = None
    left_behind: list[str]


class OutsideLink(BaseModel):
    """A link from the copied tables to one that was not ticked."""

    model_config = ConfigDict(extra="forbid")

    table: str
    target: str


class PointingTable(BaseModel):
    """A table that points at a ticked one, which the window may add."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    points_at: list[str]
    chosen: bool


class TablesPreview(BaseModel):
    """What the copy would be with these choices; nothing has run."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    tables: list[CopiedRow]
    links: TableLinks
    keep_allowed: bool
    outside: list[OutsideLink]
    pointing: list[PointingTable]
    rows: bool
    place: str
    statements: list[CopyStatement]
    loads: list[CopyLoad]
    problems: list[CopyProblem]
    warnings: list[str]


class TablesPreviewRequest(PastePair):
    tables: TablesChoice = TablesChoice()


@dataclass
class Resolved:
    """The set a copy is made of, and the request that makes it."""

    request: TableCopyRequest
    origins: dict[str, Origin]
    links: TableLinks
    keep_allowed: bool
    outside: list[OutsideLink]
    pointing: list[PointingTable]
    problems: list[CopyProblem] = field(default_factory=list)

    @property
    def choice(self) -> TablesChoice:
        """The choice with every name decided, as the job plans it again."""
        return TablesChoice(
            names={target.table.node_id: target.name for target in self.request.tables},
            rows=self.request.rows,
            links=self.links,
            also=[node_id for node_id, origin in self.origins.items() if origin == "added"],
        )


def copying(adapter: DataAdapter) -> SupportsTableCopy:
    if not isinstance(adapter, SupportsTableCopy):
        raise ActionRefused("not_applicable", "This connection cannot copy tables")
    return adapter


async def resolve(
    source: SupportsTableCopy,
    destination: SupportsTableCopy,
    ticked: list[str],
    place: str,
    choice: TablesChoice,
) -> Resolved:
    """The tables a copy is made of, named, with a decision for every link."""
    described: dict[str, CopiedTable] = {}

    async def describe(node_ids: list[str]) -> None:
        missing = [node_id for node_id in dict.fromkeys(node_ids) if node_id not in described]
        if missing:
            for table in await source.describe_for_copy(missing):
                described[table.node_id] = table

    ticked = list(dict.fromkeys(ticked))
    await describe(ticked)
    candidates: dict[str, list[str]] = {}
    for node_id in ticked:
        for pointing in described[node_id].referenced_by:
            if pointing not in ticked:
                candidates.setdefault(pointing, []).append(described[node_id].label)
    also = [node_id for node_id in dict.fromkeys(choice.also) if node_id in candidates]
    await describe(also)
    base = ticked + also
    outside = [
        OutsideLink(table=described[node_id].label, target=link.target_node_id)
        for node_id in base
        for link in described[node_id].links
        if link.target_node_id not in base
    ]
    same_database = source.table_copy_database == destination.table_copy_database
    links: TableLinks = choice.links or ("keep" if same_database else "copy")
    if links == "keep" and not same_database:
        links = "copy"
    origins: dict[str, Origin] = dict.fromkeys(ticked, "ticked")
    origins.update(dict.fromkeys(also, "added"))
    problems: list[CopyProblem] = []
    if links == "copy":
        frontier = [link.target_node_id for link in _links_of(described, base)]
        while frontier and len(origins) <= MAX_COPIED_TABLES:
            fresh = [node_id for node_id in dict.fromkeys(frontier) if node_id not in origins]
            try:
                await describe(fresh)
            except NodeNotFound as gone:
                problems.append(CopyProblem(message=f"{gone} is linked to and no longer exists"))
                break
            origins.update(dict.fromkeys(fresh, "linked"))
            frontier = [
                link.target_node_id
                for link in _links_of(described, fresh)
                if link.target_node_id not in origins
            ]
    members = list(origins)
    if len(members) > MAX_COPIED_TABLES:
        problems.append(
            CopyProblem(
                message=f"The links bring in more than {MAX_COPIED_TABLES} tables; "
                "drop the links or copy fewer"
            )
        )
        members = members[:MAX_COPIED_TABLES]
    explicit = {node_id: name for node_id, name in choice.names.items() if node_id in origins}
    unnamed = [node_id for node_id in members if node_id not in explicit]
    suggested = await destination.free_table_names(
        place, [described[node_id].name for node_id in unnamed]
    )
    names = {**dict(zip(unnamed, suggested, strict=True)), **explicit}
    targets = [
        TableCopyTarget(
            table=described[node_id],
            name=names[node_id],
            links={
                link.name: _decided(link.target_node_id, origins, links)
                for link in described[node_id].links
            },
        )
        for node_id in members
    ]
    return Resolved(
        request=TableCopyRequest(
            dialect=source.table_copy_dialect,
            place_node_id=place,
            same_database=same_database,
            tables=targets,
            rows=choice.rows,
        ),
        origins=origins,
        links=links,
        keep_allowed=same_database,
        outside=outside,
        pointing=[
            PointingTable(
                node_id=node_id,
                label=node_id,
                points_at=labels,
                chosen=node_id in also,
            )
            for node_id, labels in candidates.items()
        ],
        problems=problems,
    )


def _links_of(described: dict[str, CopiedTable], node_ids: list[str]) -> Iterator[CopiedLink]:
    for node_id in node_ids:
        yield from described[node_id].links


def _decided(target: str, origins: dict[str, Origin], links: TableLinks) -> LinkDecision:
    if target in origins:
        return "copy"
    return "original" if links == "keep" else "drop"


async def preview(
    source: DataAdapter, destination: DataAdapter, request: TablesPreviewRequest
) -> TablesPreview:
    """What the window shows for these choices: the copy planned, not run."""
    if request.destination_node_id is None:
        raise ActionRefused("not_applicable", "Paste into a schema")
    resolved = await resolve(
        copying(source),
        copying(destination),
        request.source_node_ids,
        request.destination_node_id,
        request.tables,
    )
    plan = await copying(destination).plan_table_copy(resolved.request)
    return TablesPreview(
        tables=[
            CopiedRow(
                node_id=target.table.node_id,
                label=target.table.label,
                name=target.name,
                origin=resolved.origins[target.table.node_id],
                rows=target.table.row_estimate,
                left_behind=target.table.left_behind,
            )
            for target in resolved.request.tables
        ],
        links=resolved.links,
        keep_allowed=resolved.keep_allowed,
        outside=resolved.outside,
        pointing=resolved.pointing,
        rows=resolved.request.rows,
        place=request.destination_node_id,
        statements=plan.statements,
        loads=plan.loads,
        problems=resolved.problems + plan.problems,
        warnings=plan.warnings,
    )


class TablesCopy:
    name: PasteKindName = "tables_copy"
    title = "Copy tables"
    needs = "Tick a table"
    doing = "Copying tables"
    done = "copied"
    mode: ClipboardMode = "copy"
    workflow: PasteWorkflow = "copy-tables"
    # Its window comes first: the names, the rows and the links are choices.
    converts = True
    can_replace = False
    source_requires: Access = "read"
    destination_requires: Access = "structure"
    changes_source = False
    makes = True
    # A link keeps a name and columns, not a choice about every link of every
    # table: this is run from the catalog.
    pipelines = False
    # Made again from its rows, a table loses its keys, links and types.
    outranks: tuple[PasteKindName, ...] = ("rows_new_relation",)

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsTableCopy)

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            isinstance(source, SupportsTableCopy)
            and isinstance(destination, SupportsTableCopy)
            and source.table_copy_dialect == destination.table_copy_dialect
        )

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        refusal = await _refusal(source, node_ids, gone="Tick a table")
        if refusal is not None:
            return Availability(available=False, reason=refusal)
        return Availability(available=True)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        # Where the catalog stood is only where the window starts: the schema
        # is chosen in it, whatever was selected when Paste was.
        del destination
        refusal = await _refusal(source, pair.source_node_ids, gone=GONE)
        if refusal is not None:
            return refused(self, refusal)
        return offered(self, available=True)

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del source, name, columns
        return None

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        del source, destination, source_end, target_end
        return refused(self, "Tables are copied from the catalog")

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        if request.destination_node_id is None:
            raise ActionRefused("not_applicable", "Paste into a schema")
        resolved = await resolve(
            copying(source),
            copying(destination),
            request.source_node_ids,
            request.destination_node_id,
            request.tables or TablesChoice(),
        )
        plan = await copying(destination).plan_table_copy(resolved.request)
        _refuse(resolved.problems + plan.problems)
        return TransferPlan(
            items=[
                TransferItem(
                    node_id=target.table.node_id,
                    name=target.table.label[:255],
                    published_as=target.name,
                )
                for target in resolved.request.tables
            ],
            bytes_total=None,
            place=request.destination_node_id,
            tables=resolved.choice,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        """Every table at once, in one transaction: all of them arrive or none."""
        reading, making = copying(source), copying(destination)
        items = {item.node_id: item for item in transfer.items}
        try:
            resolved = await resolve(
                reading,
                making,
                list(items),
                transfer.destination_node_id or "",
                transfer.tables or TablesChoice(),
            )
            if [target.table.node_id for target in resolved.request.tables] != list(items):
                raise ActionRefused("not_applicable", CHANGED)
            _refuse(resolved.problems)
        except (ActionRefused, NodeNotFound, AdapterError, ValueError) as failure:
            raise _stopped(transfer, _said(failure)) from None
        sizes: dict[str, int] = {}

        async def arrived(load: CopyLoad, rows: int, size: int) -> None:
            item = items[load.node_id]
            item.outcome = "running"
            item.rows = rows
            transfer.current = item.name
            sizes[load.node_id] = size
            transfer.bytes_done = sum(sizes.values())
            await report.progressed()

        for item in transfer.items:
            item.outcome = "running"
        await report.progressed()
        try:
            async with reading.reading_tables() as tables:
                await making.carry_table_copy(
                    resolved.request,
                    lambda load: tables.rows(load.node_id, load.columns),
                    arrived,
                )
        except asyncio.CancelledError:
            for item in transfer.items:
                item.outcome = "stopped"
            raise
        except (AdapterError, ValueError) as failure:
            raise _stopped(transfer, _said(failure)) from None
        for item in transfer.items:
            item.outcome = "done"
            item.arrived = 1
            item.rows = (item.rows or 0) if resolved.request.rows else None
            item.published_id = f"{transfer.destination_node_id}.{item.published_as}"
        transfer.current = None
        transfer.published += len(transfer.items)

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        items = transfer.items
        where = f"into {transfer.place_label}"
        if all(item.outcome == "done" for item in items):
            copied = (
                counted(len(items), "table")
                if len(items) > 1
                else f"{items[0].name} as {items[0].published_as}"
            )
            with_rows = (
                f" with {counted(sum(item.rows or 0 for item in items), 'row')}"
                if transfer.tables is None or transfer.tables.rows
                else ", structure only"
            )
            return f"{copied} copied {where}{with_rows}"
        if any(item.outcome == "stopped" for item in items):
            return "Nothing was copied: it was stopped"
        return f"Nothing was copied: {stopped or 'it failed'}"


def _refuse(problems: list[CopyProblem]) -> None:
    if problems:
        first = problems[0]
        raise ActionRefused(
            "conflict" if first.kind == "conflict" else "not_applicable", first.message
        )


def _said(failure: Exception) -> str:
    if isinstance(failure, ActionRefused | AdapterError):
        return failure.message
    if isinstance(failure, NodeNotFound):
        return GONE
    return str(failure)


def _stopped(transfer: Transfer, message: str) -> TransferStopped:
    """Nothing arrived: every table failed together, and the reason says why."""
    for item in transfer.items:
        item.outcome = "failed"
        item.failed = 1
        item.message = f"{item.name} was not copied: {message[:1].lower()}{message[1:]}"[:600]
    transfer.current = None
    return TransferStopped(message)


async def _refusal(source: DataAdapter, node_ids: list[str], *, gone: str) -> str | None:
    """Why these nodes cannot be copied as tables, or None."""
    if not isinstance(source, SupportsTableCopy):
        return "This connection cannot copy tables"
    if len(node_ids) > MAX_COPIED_TABLES:
        return f"Copy at most {MAX_COPIED_TABLES} tables at a time"
    try:
        described = await source.describe_for_copy(list(dict.fromkeys(node_ids)))
    except NodeNotFound:
        return gone
    except ValueError:
        return "Tick a table"
    except AdapterError:
        return UNAVAILABLE
    refused_one = next((table for table in described if table.refusal is not None), None)
    if refused_one is not None:
        return f"{refused_one.label}: {refused_one.refusal}"
    return None

