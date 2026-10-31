"""Walking the catalog of a MongoDB server: databases, then their collections (D283)."""

import asyncio
from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import (
    CatalogNode,
    ReportNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.mongodb.inspection import collection_info, collection_type, statistics
from app.adapters.mongodb.reports import (
    REPORTS,
    SECTION_DESCRIPTION,
    SECTION_ID,
    SECTION_TITLE,
    ServerReport,
    in_section,
    is_section,
    report_for,
)
from app.adapters.mongodb.session import MongodbSession
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# The server's own databases. Read like any other and never changed.
SYSTEM_DATABASES = frozenset({"admin", "local", "config"})

# Past this many collections in one database, counting each would make
# opening it slow, and the catalog lists them without their counts.
MAX_COUNTED = 200

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
# A collection has no DDL; its options, validator, indexes and a view's
# pipeline answer the same question (D55), as the JSON they are.
OPTIONS_REPRESENTATION = NodeRepresentation(kind="json", title=N_("View the definition"))
# Every document whole, a page at a time (D287).
DOCUMENTS_REPRESENTATION = NodeRepresentation(kind="jsonl", title=N_("View as documents"))
REPRESENTATIONS = [TABLE_REPRESENTATION, DOCUMENTS_REPRESENTATION, OPTIONS_REPRESENTATION]


# A report has no definition of its own; the pipeline it runs answers the
# same question.
REPORT_DEFINITION = NodeRepresentation(kind="json", title=N_("View the pipeline"))


def section_node() -> ReportNode:
    """The server's own section of reports, listed after the databases."""
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: ServerReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=worded_titles([TABLE_REPRESENTATION, REPORT_DEFINITION]),
    )


def is_buckets(name: str) -> bool:
    """Where a time series keeps its documents. Read through the series, which
    is the thing a person made, so not listed beside it."""
    return name.startswith("system.buckets.")


def is_system_database(name: str) -> bool:
    return name in SYSTEM_DATABASES


def is_system_collection(database: str, name: str) -> bool:
    return is_system_database(database) or name.startswith("system.")


def database_node(name: str) -> SchemaNode:
    return SchemaNode(
        id=database_id(name),
        name=name,
        term="database",
        has_children=True,
        is_system=is_system_database(name),
        representations=[],
    )


def collection_node(
    database: str, info: Mapping[str, Any], counted: tuple[int | None, int | None] = (None, None)
) -> CatalogNode:
    """One collection or view as a node; shared by the listing and `path_to`."""
    name = str(info["name"])
    system = is_system_collection(database, name)
    representations = worded_titles(REPRESENTATIONS)
    if collection_type(info) == "view":
        return ViewNode(
            id=relation_id(database, name),
            name=name,
            has_children=False,
            is_system=system,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    rows, size = counted
    return TableNode(
        id=relation_id(database, name),
        name=name,
        term="collection",
        has_children=False,
        row_count_estimate=rows,
        size_bytes=size,
        is_system=system,
        representations=representations,
        describable=True,
        summarizable=True,
    )


class MongodbCatalog:
    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    async def database_names(self) -> list[str]:
        """Every database the user may see, the connection's own first.

        A database with nothing in it does not exist to MongoDB, so the one
        the connection names is listed whether or not it is there yet.
        """
        async with self._session.client() as client:
            with self._session.failures():
                listed = await client.admin.command(
                    "listDatabases", nameOnly=True, authorizedDatabases=True
                )
        names = [str(database["name"]) for database in listed.get("databases", [])]
        own = self._session.database()
        if own and own not in names:
            names.append(own)
        names.sort(key=lambda name: (name != own, is_system_database(name), name))
        return names

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [*(database_node(name) for name in await self.database_names()), section_node()]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            await self.path_to(node_id)
            return []
        database, collection = parse(node_id)
        if collection is not None:
            await self.path_to(node_id)
            return []
        if database not in await self.database_names():
            raise AdapterError("config", say('Database "{name}" does not exist', name=database))
        async with self._session.client() as client:
            with self._session.failures():
                cursor = await client[database].list_collections()
                infos = sorted(
                    (info for info in await cursor.to_list() if not is_buckets(str(info["name"]))),
                    key=lambda info: str(info["name"]),
                )
                stored = [
                    str(info["name"]) for info in infos if collection_type(info) == "collection"
                ]
                counts: dict[str, tuple[int | None, int | None]] = {}
                if len(stored) <= MAX_COUNTED:
                    found = await asyncio.gather(
                        *(statistics(client, database, name) for name in stored)
                    )
                    counts = dict(zip(stored, found, strict=True))
        return [
            collection_node(database, info, counts.get(str(info["name"]), (None, None)))
            for info in infos
        ]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed on the server."""
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        database, collection = parse(node_id)
        if database not in await self.database_names():
            raise NodeNotFound(node_id)
        path: list[CatalogNode] = [database_node(database)]
        if collection is None:
            return path
        async with self._session.client() as client:
            with self._session.failures():
                info = await collection_info(client, database, collection)
                if info is None:
                    raise NodeNotFound(node_id)
                counted = (
                    await statistics(client, database, collection)
                    if collection_type(info) == "collection"
                    else (None, None)
                )
        path.append(collection_node(database, info, counted))
        return path
