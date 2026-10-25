"""The reports a ClickHouse server publishes about itself (D55, D275).

Every statement is written here and is never composed from a request; a node
id selects one entry. Each reads the server's `system` tables, chosen and
named for a person: the raw tables are in the catalog too, under `system`,
for anybody who wants all of them.

A report's id begins with a backslash followed by a letter, which a
database's id never does: `database_id` writes every backslash in a name as
two (D229).
"""

from dataclasses import dataclass, field

from app.core.translation import N_

SECTION_ID = "\\system"
SECTION_TITLE = N_("System")
SECTION_DESCRIPTION = N_("What this server says about itself")


@dataclass(frozen=True)
class SystemReport:
    key: str
    title: str
    description: str
    statement: str
    refresh_seconds: int | None = None
    stable_order: tuple[str, ...] = field(default=())

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="processes",
        title=N_("Processes"),
        description=N_("Queries running now, who runs them and what they cost"),
        refresh_seconds=5,
        statement="""
            SELECT query_id AS id, user, address, round(elapsed, 1) AS seconds,
                   read_rows, written_rows, formatReadableSize(memory_usage) AS memory,
                   query_kind AS kind, query
            FROM system.processes
        """,
        stable_order=("id",),
    ),
    SystemReport(
        key="mutations",
        title=N_("Mutations"),
        description=N_("Changes rewriting a table's parts, and why one is stuck"),
        refresh_seconds=10,
        # The id names one mutation of one table: a mutation's own id repeats
        # from table to table.
        statement="""
            SELECT toString(cityHash64(database, table, mutation_id)) AS id,
                   database, table, mutation_id AS mutation, command,
                   create_time AS created, is_done AS done, parts_to_do AS parts_left,
                   latest_fail_reason AS failure
            FROM system.mutations
        """,
        stable_order=("created", "id"),
    ),
    SystemReport(
        key="merges",
        title=N_("Merges"),
        description=N_("Parts being merged in the background now"),
        refresh_seconds=5,
        statement="""
            SELECT database, table, round(elapsed, 1) AS seconds,
                   round(progress * 100, 1) AS percent, num_parts AS parts,
                   result_part_name AS result, formatReadableSize(total_size_bytes_compressed) AS size
            FROM system.merges
        """,
        stable_order=("database", "table", "result"),
    ),
    SystemReport(
        key="tables",
        title=N_("Table sizes"),
        description=N_("Rows, parts and bytes on disk of every table"),
        statement="""
            SELECT database, table, sum(rows) AS rows, count() AS parts,
                   sum(bytes_on_disk) AS bytes_on_disk,
                   sum(data_uncompressed_bytes) AS bytes_uncompressed,
                   max(modification_time) AS written
            FROM system.parts
            WHERE active
            GROUP BY database, table
        """,
        stable_order=("database", "table"),
    ),
    SystemReport(
        key="disks",
        title=N_("Disks"),
        description=N_("Where the server keeps its data, and how full each place is"),
        statement="""
            SELECT name, path, free_space AS free_bytes, total_space AS total_bytes,
                   type
            FROM system.disks
        """,
        stable_order=("name",),
    ),
    SystemReport(
        key="settings",
        title=N_("Changed settings"),
        description=N_("Server settings that differ from their defaults"),
        # The server's, not the session's: every request here carries settings
        # of its own (D268), which would fill a list of the session's.
        statement="""
            SELECT name, value, default, type, description
            FROM system.server_settings
            WHERE changed
        """,
        stable_order=("name",),
    ),
    SystemReport(
        key="metrics",
        title=N_("Metrics"),
        description=N_("What the server counts right now: connections, queries, merges"),
        refresh_seconds=5,
        statement="""
            SELECT metric, value, description
            FROM system.metrics
        """,
        stable_order=("metric",),
    ),
    SystemReport(
        key="users",
        title=N_("Users"),
        description=N_("Accounts of this server and where each is kept"),
        statement="""
            SELECT name, storage, auth_type, default_database
            FROM system.users
        """,
        stable_order=("name",),
    ),
)

_BY_ID = {report.node_id: report for report in REPORTS}

PROCESSES_REPORT_ID = f"{SECTION_ID}/processes"
MUTATIONS_REPORT_ID = f"{SECTION_ID}/mutations"


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    """Whether an id is the section's or below it, whether or not it names a report."""
    return node_id == SECTION_ID or node_id.startswith(f"{SECTION_ID}/")


def report_for(node_id: str) -> SystemReport | None:
    return _BY_ID.get(node_id)
