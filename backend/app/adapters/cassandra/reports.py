"""The reports a Cassandra or ScyllaDB cluster publishes about itself (D55, D349).

Every statement is written here and is never composed from a request; a node
id selects one entry. CQL joins and groups nothing, and the tables read are
small, so a report reads its statements whole and shapes the rows here. The
products keep some of this in different places — Cassandra in its virtual
`system_views`, ScyllaDB in `system` — so a report says which it reads where.

A report's id begins with a backslash, which a keyspace's name never holds.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.adapters.cassandra.session import CassandraSession, ServerProfile
from app.adapters.cassandra.types import build_column_type, scalar_text
from app.adapters.relation import ColumnType
from app.core.translation import N_

SECTION_ID = "\\cluster"
SECTION_TITLE = N_("Cluster")
SECTION_DESCRIPTION = N_("What this cluster says about itself")

Rows = list[list[str | None]]


@dataclass(frozen=True)
class ReportColumn:
    name: str
    type: ColumnType


@dataclass(frozen=True)
class ReportAnswer:
    columns: list[ReportColumn]
    rows: Rows


Reader = Callable[[CassandraSession, ServerProfile], Awaitable[ReportAnswer]]


@dataclass(frozen=True)
class ClusterReport:
    key: str
    title: str
    description: str
    # The statements it reads, for the statement view (D55).
    statements: Callable[[ServerProfile], list[str]]
    read: Reader
    refresh_seconds: int | None = None

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple | set | frozenset):
        return ", ".join(sorted(str(item) for item in value))
    return scalar_text(value)


def _columns(*spec: tuple[str, str]) -> list[ReportColumn]:
    return [
        ReportColumn(name=name, type=build_column_type(type_text))
        for name, type_text in spec
    ]


async def _rows(session: CassandraSession, statement: str) -> list[dict[str, Any]]:
    return (await session.rows(statement, limit=10_000)).dicts()


_LOCAL = "SELECT broadcast_address, data_center, rack, release_version, host_id FROM system.local"
_PEERS = "SELECT peer, data_center, rack, release_version, host_id FROM system.peers"


async def _nodes(session: CassandraSession, profile: ServerProfile) -> ReportAnswer:
    rows: Rows = []
    for row in await _rows(session, _LOCAL):
        rows.append(
            [
                _text(row["broadcast_address"]),
                "yes",
                _text(row["data_center"]),
                _text(row["rack"]),
                profile.text if profile.scylla else _text(row["release_version"]),
                _text(row["host_id"]),
            ]
        )
    for row in await _rows(session, _PEERS):
        rows.append(
            [
                _text(row["peer"]),
                "no",
                _text(row["data_center"]),
                _text(row["rack"]),
                _text(row["release_version"]),
                _text(row["host_id"]),
            ]
        )
    return ReportAnswer(
        columns=_columns(
            ("address", "text"),
            ("this_node", "text"),
            ("data_center", "text"),
            ("rack", "text"),
            ("version", "text"),
            ("host_id", "uuid"),
        ),
        rows=sorted(rows, key=lambda row: (row[1] != "yes", row[0] or "")),
    )


_CASSANDRA_SETTINGS = "SELECT name, value FROM system_views.settings"
_SCYLLA_SETTINGS = "SELECT name, value, source, type FROM system.config"


async def _settings(session: CassandraSession, profile: ServerProfile) -> ReportAnswer:
    if profile.scylla:
        found = await _rows(session, _SCYLLA_SETTINGS)
        return ReportAnswer(
            columns=_columns(
                ("name", "text"),
                ("value", "text"),
                ("source", "text"),
                ("type", "text"),
            ),
            rows=sorted(
                (
                    [
                        _text(row["name"]),
                        _text(row["value"]),
                        _text(row["source"]),
                        _text(row["type"]),
                    ]
                    for row in found
                ),
                key=lambda row: row[0] or "",
            ),
        )
    found = await _rows(session, _CASSANDRA_SETTINGS)
    return ReportAnswer(
        columns=_columns(("name", "text"), ("value", "text")),
        rows=sorted(
            ([_text(row["name"]), _text(row["value"])] for row in found),
            key=lambda row: row[0] or "",
        ),
    )


_CASSANDRA_CLIENTS = (
    "SELECT address, port, username, driver_name, driver_version, protocol_version, "
    "request_count, ssl_enabled FROM system_views.clients"
)
_SCYLLA_CLIENTS = (
    "SELECT address, port, username, driver_name, driver_version, protocol_version, "
    "client_type, ssl_enabled FROM system.clients"
)


async def _clients(session: CassandraSession, profile: ServerProfile) -> ReportAnswer:
    statement = _SCYLLA_CLIENTS if profile.scylla else _CASSANDRA_CLIENTS
    last = "client_type" if profile.scylla else "request_count"
    found = await _rows(session, statement)
    return ReportAnswer(
        columns=_columns(
            ("address", "inet"),
            ("port", "int"),
            ("username", "text"),
            ("driver", "text"),
            ("driver_version", "text"),
            ("protocol", "int"),
            (last, "text" if profile.scylla else "bigint"),
            ("tls", "boolean"),
        ),
        rows=sorted(
            (
                [
                    _text(row["address"]),
                    _text(row["port"]),
                    _text(row["username"]),
                    _text(row["driver_name"]),
                    _text(row["driver_version"]),
                    _text(row["protocol_version"]),
                    _text(row[last]),
                    _text(row["ssl_enabled"]),
                ]
                for row in found
            ),
            key=lambda row: (row[0] or "", row[1] or ""),
        ),
    )


_SIZES = (
    "SELECT keyspace_name, table_name, partitions_count, mean_partition_size "
    "FROM system.size_estimates"
)


async def _sizes(session: CassandraSession, _profile: ServerProfile) -> ReportAnswer:
    """Partitions and bytes per table, summed over the node's token ranges.

    The node's own estimate of what it holds, which is all a client can ask.
    """
    totals: dict[tuple[str, str], list[int]] = {}
    for row in await _rows(session, _SIZES):
        key = (str(row["keyspace_name"]), str(row["table_name"]))
        partitions = int(row["partitions_count"] or 0)
        size = int(row["mean_partition_size"] or 0)
        total = totals.setdefault(key, [0, 0])
        total[0] += partitions
        total[1] += partitions * size
    return ReportAnswer(
        columns=_columns(
            ("keyspace", "text"),
            ("table", "text"),
            ("partitions", "bigint"),
            ("bytes", "bigint"),
        ),
        rows=[
            [keyspace, table, str(partitions), str(size)]
            for (keyspace, table), (partitions, size) in sorted(totals.items())
        ],
    )


_ROLES = "SELECT role, can_login, is_superuser, member_of FROM system_auth.roles"
# ScyllaDB keeps its roles in group 0 since 2025, in `system.roles`.
_SCYLLA_ROLES = "SELECT role, can_login, is_superuser, member_of FROM system.roles"


async def _roles(session: CassandraSession, profile: ServerProfile) -> ReportAnswer:
    found = await _rows(session, _SCYLLA_ROLES if profile.scylla else _ROLES)
    return ReportAnswer(
        columns=_columns(
            ("role", "text"),
            ("can_login", "boolean"),
            ("superuser", "boolean"),
            ("member_of", "text"),
        ),
        rows=sorted(
            (
                [
                    _text(row["role"]),
                    _text(row["can_login"]),
                    _text(row["is_superuser"]),
                    _text(row["member_of"]),
                ]
                for row in found
            ),
            key=lambda row: row[0] or "",
        ),
    )


REPORTS: tuple[ClusterReport, ...] = (
    ClusterReport(
        key="nodes",
        title=N_("Nodes"),
        description=N_(
            "The nodes of the cluster, their data centres, racks and versions"
        ),
        statements=lambda profile: [_LOCAL, _PEERS],
        read=_nodes,
    ),
    ClusterReport(
        key="clients",
        title=N_("Clients"),
        description=N_("Connections to the node asked, and the drivers that made them"),
        statements=lambda profile: [
            _SCYLLA_CLIENTS if profile.scylla else _CASSANDRA_CLIENTS
        ],
        read=_clients,
        refresh_seconds=10,
    ),
    ClusterReport(
        key="sizes",
        title=N_("Table sizes"),
        description=N_(
            "Partitions and bytes of every table, as the node asked estimates them"
        ),
        statements=lambda profile: [_SIZES],
        read=_sizes,
    ),
    ClusterReport(
        key="settings",
        title=N_("Settings"),
        description=N_("The node's configuration as it runs"),
        statements=lambda profile: [
            _SCYLLA_SETTINGS if profile.scylla else _CASSANDRA_SETTINGS
        ],
        read=_settings,
    ),
    ClusterReport(
        key="roles",
        title=N_("Roles"),
        description=N_("Who may sign in, and who is a superuser"),
        statements=lambda profile: [_SCYLLA_ROLES if profile.scylla else _ROLES],
        read=_roles,
    ),
)

_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    """Whether an id is the section's or below it, whether or not it names a report."""
    return node_id == SECTION_ID or node_id.startswith(f"{SECTION_ID}/")


def report_for(node_id: str) -> ClusterReport | None:
    return _BY_ID.get(node_id)
