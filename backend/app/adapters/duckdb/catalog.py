"""Walking the catalog of a DuckDB file: its schemas, then their relations (D389)."""

from collections.abc import Mapping
from typing import Any

from app.adapters import database_ids as ids
from app.adapters.catalog import CatalogNode, SchemaNode, TableNode, ViewNode
from app.adapters.content import NodeRepresentation
from app.adapters.duckdb.inspection import find_relation, list_relations, list_schemas
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.frameworks import detect_frameworks
from app.adapters.protocol import NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View DDL"))


def schema_node(schema: str, tables: list[str]) -> SchemaNode:
    return SchemaNode(
        id=ids.database_id(schema),
        name=schema,
        has_children=True,
        representations=[],
        frameworks=detect_frameworks(tables),
    )


def relation_node(row: Mapping[str, Any]) -> CatalogNode:
    """One relation as a node; shared by the listing and `path_to`."""
    schema, name = str(row["schema_name"]), str(row["name"])
    node_id = ids.relation_id(schema, name)
    representations = worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION])
    if row["type"] == "view":
        return ViewNode(
            id=node_id,
            name=name,
            has_children=False,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    estimate = row["estimated_size"]
    return TableNode(
        id=node_id,
        name=name,
        has_children=False,
        row_count_estimate=None if estimate is None else int(estimate),
        representations=representations,
        describable=True,
        summarizable=True,
    )


def _schemas(reading: Reading) -> list[SchemaNode]:
    tables: dict[str, list[str]] = {}
    for row in list_relations(reading):
        if row["type"] == "table":
            tables.setdefault(str(row["schema_name"]), []).append(str(row["name"]))
    return [schema_node(schema, tables.get(schema, [])) for schema in list_schemas(reading)]


class DuckdbCatalog:
    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return list(await self._session.inspection(_schemas))
        schema, relation = ids.parse(node_id)
        if relation is not None:
            await self.path_to(node_id)
            return []

        def read(reading: Reading) -> list[dict[str, Any]] | None:
            if schema not in list_schemas(reading):
                return None
            return list_relations(reading, schema)

        rows = await self._session.inspection(read)
        if rows is None:
            raise NodeNotFound(node_id)
        return [relation_node(row) for row in rows]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed in the file."""
        schema, relation = ids.parse(node_id)

        def read(reading: Reading) -> tuple[list[str], list[str], dict[str, Any] | None]:
            schemas = list_schemas(reading)
            if schema not in schemas:
                return schemas, [], None
            tables = [
                str(row["name"])
                for row in list_relations(reading, schema)
                if row["type"] == "table"
            ]
            found = None if relation is None else find_relation(reading, schema, relation)
            return schemas, tables, found

        schemas, tables, found = await self._session.inspection(read)
        if schema not in schemas:
            raise NodeNotFound(node_id)
        path: list[CatalogNode] = [schema_node(schema, tables)]
        if relation is None:
            return path
        if found is None:
            raise NodeNotFound(node_id)
        path.append(relation_node(found))
        return path
