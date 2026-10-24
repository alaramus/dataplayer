"""Walking the catalog of a SQLite file: `main`, then its relations (D248)."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.adapters.catalog import (
    CatalogNode,
    ReportNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.frameworks import detect_frameworks
from app.adapters.protocol import NodeNotFound
from app.adapters.sqlite import ids
from app.adapters.sqlite.inspection import (
    SCHEMA,
    estimates,
    find_relation,
    is_system_relation,
    list_relations,
)
from app.adapters.sqlite.reports import (
    REPORTS,
    SECTION_DESCRIPTION,
    SECTION_ID,
    SECTION_TITLE,
    SystemReport,
    in_section,
    is_section,
    report_for,
)
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.words import worded_titles
from app.core.translation import N_, say

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View DDL"))
# A report has no DDL, but the statement it is made of answers the same
# question: what is this, really (D55).
REPORT_SQL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View the statement"))


def section_node() -> ReportNode:
    """The file's own section of reports, listed after `main`."""
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=worded_titles([TABLE_REPRESENTATION, REPORT_SQL_REPRESENTATION]),
    )


def schema_node(relations: Sequence[Mapping[str, Any]]) -> SchemaNode:
    tables = [
        str(row["name"])
        for row in relations
        if row["type"] == "table" and not is_system_relation(str(row["name"]), str(row["type"]))
    ]
    return SchemaNode(
        id=SCHEMA,
        name=SCHEMA,
        has_children=True,
        representations=[],
        frameworks=detect_frameworks(tables),
    )


def relation_node(row: Mapping[str, Any]) -> CatalogNode:
    """One relation as a node; shared by the listing and `path_to`."""
    name = str(row["name"])
    system = is_system_relation(name, str(row["type"]))
    representations = worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION])
    if row["type"] == "view":
        return ViewNode(
            id=ids.relation_id(name),
            name=name,
            has_children=False,
            is_system=system,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    estimate = row.get("row_estimate")
    return TableNode(
        id=ids.relation_id(name),
        name=name,
        has_children=False,
        row_count_estimate=None if estimate is None else int(estimate),
        is_system=system,
        representations=representations,
        describable=True,
        summarizable=True,
    )


def _listing(reading: Reading) -> list[dict[str, Any]]:
    counted = estimates(reading)
    return [
        {**row, "row_estimate": counted.get(str(row["name"]))}
        for row in list_relations(reading)
    ]


class SqliteCatalog:
    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [schema_node(await self._session.inspection(list_relations)), section_node()]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            await self.path_to(node_id)
            return []
        schema, relation = ids.parse(node_id)
        if schema != SCHEMA:
            raise NodeNotFound(node_id)
        if relation is not None:
            await self.path_to(node_id)
            return []
        return [relation_node(row) for row in await self._session.inspection(_listing)]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed in the file."""
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        schema, relation = ids.parse(node_id)
        if schema != SCHEMA:
            raise NodeNotFound(node_id)

        def read(reading: Reading) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            found = None if relation is None else find_relation(reading, relation)
            return list_relations(reading), found

        relations, found = await self._session.inspection(read)
        path: list[CatalogNode] = [schema_node(relations)]
        if relation is None:
            return path
        if found is None:
            raise NodeNotFound(node_id)
        path.append(relation_node(found))
        return path
