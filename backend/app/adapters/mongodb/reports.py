"""The reports a MongoDB server publishes about itself (D55, D289).

Each is a pipeline written here, never composed from a request: a node id
selects one entry. A pipeline rather than a command, so the page's filters,
order and paging are stages the server runs after it, the way a view's are
(D285). Its columns and their types are written beside it, since a report
has no documents to learn them from before it is read.

A report's id begins with a backslash, which a database's id never does
(D229).
"""

from dataclasses import dataclass, field
from typing import Any

from app.adapters.mongodb.values import Tag
from app.core.translation import N_

SECTION_ID = "\\server"
SECTION_TITLE = N_("Server")
SECTION_DESCRIPTION = N_("What this server says about itself")


@dataclass(frozen=True)
class ServerReport:
    key: str
    title: str
    description: str
    # Where the pipeline runs: a database, and a collection of it or none for
    # a database-wide stage such as `$currentOp`.
    database: str
    collection: str | None
    pipeline: tuple[dict[str, Any], ...]
    columns: tuple[tuple[str, Tag], ...]
    refresh_seconds: int | None = None
    stable_order: tuple[str, ...] = field(default=())

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


def _current(*, idle: bool) -> dict[str, Any]:
    return {"$currentOp": {"allUsers": True, "idleConnections": idle, "idleSessions": False}}


_OPERATION_FIELDS: dict[str, Any] = {
    "_id": 0,
    "id": "$opid",
    "kind": "$op",
    "namespace": "$ns",
    "seconds": "$secs_running",
    "client": "$client",
    "application": "$appName",
    "user": {"$first": "$effectiveUsers.user"},
    "command": "$command",
}

REPORTS: tuple[ServerReport, ...] = (
    ServerReport(
        key="operations",
        title=N_("Operations"),
        description=N_("What the server is doing now, for whom, and for how long"),
        database="admin",
        collection=None,
        pipeline=(
            _current(idle=False),
            {"$match": {"active": True, "opid": {"$exists": True}}},
            {"$project": _OPERATION_FIELDS},
        ),
        columns=(
            ("id", "int"),
            ("kind", "string"),
            ("namespace", "string"),
            ("seconds", "number"),
            ("client", "string"),
            ("application", "string"),
            ("user", "string"),
            ("command", "object"),
        ),
        refresh_seconds=5,
        stable_order=("id",),
    ),
    ServerReport(
        key="connections",
        title=N_("Connections"),
        description=N_("Every client connected now, busy or waiting"),
        database="admin",
        collection=None,
        pipeline=(
            _current(idle=True),
            {"$match": {"client": {"$exists": True}}},
            {
                "$project": {
                    "_id": 0,
                    "connection": "$connectionId",
                    "client": "$client",
                    "application": "$appName",
                    "user": {"$first": "$effectiveUsers.user"},
                    "active": "$active",
                    "driver": "$clientMetadata.driver.name",
                }
            },
        ),
        columns=(
            ("connection", "int"),
            ("client", "string"),
            ("application", "string"),
            ("user", "string"),
            ("active", "bool"),
            ("driver", "string"),
        ),
        refresh_seconds=10,
        stable_order=("connection",),
    ),
    ServerReport(
        key="users",
        title=N_("Users"),
        description=N_("Who may sign in, where each is defined and with which roles"),
        database="admin",
        collection="system.users",
        pipeline=(
            {
                "$project": {
                    "_id": 0,
                    "user": "$user",
                    "database": "$db",
                    "roles": {
                        "$map": {
                            "input": "$roles",
                            "in": {"$concat": ["$$this.role", "@", "$$this.db"]},
                        }
                    },
                    "mechanisms": "$mechanisms",
                }
            },
        ),
        columns=(
            ("user", "string"),
            ("database", "string"),
            ("roles", "array"),
            ("mechanisms", "array"),
        ),
        stable_order=("database", "user"),
    ),
    ServerReport(
        key="roles",
        title=N_("Roles"),
        description=N_("Roles made on this server, what they grant and what they inherit"),
        database="admin",
        collection="system.roles",
        pipeline=(
            {
                "$project": {
                    "_id": 0,
                    "role": "$role",
                    "database": "$db",
                    "privileges": {"$size": {"$ifNull": ["$privileges", []]}},
                    "inherits": {
                        "$map": {
                            "input": {"$ifNull": ["$roles", []]},
                            "in": {"$concat": ["$$this.role", "@", "$$this.db"]},
                        }
                    },
                }
            },
        ),
        columns=(
            ("role", "string"),
            ("database", "string"),
            ("privileges", "int"),
            ("inherits", "array"),
        ),
        stable_order=("database", "role"),
    ),
)


def report_for(node_id: str) -> ServerReport | None:
    for report in REPORTS:
        if report.node_id == node_id:
            return report
    return None


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    return node_id.startswith(SECTION_ID + "/")
