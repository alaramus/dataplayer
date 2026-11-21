"""The reports a DuckDB file and its engine give about themselves (D55, D398).

Every statement is written here and is never composed from a request; a node
id selects one entry. Each reads DuckDB's catalog functions, limited to the
file's own database, and leaves out what names a path of the server (D388).

A report's id begins with a backslash followed by a letter, which a schema's
id never does: `database_id` writes every backslash in a name as two (D229).
"""

from dataclasses import dataclass, field

from app.core.translation import N_

SECTION_ID = "\\system"
SECTION_TITLE = N_("System")
SECTION_DESCRIPTION = N_("What this file and DuckDB say about themselves")

_OWN = "database_name = current_database()"


@dataclass(frozen=True)
class SystemReport:
    key: str
    title: str
    description: str
    statement: str
    stable_order: tuple[str, ...] = field(default=())

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="database",
        title=N_("Database"),
        description=N_("The file's size and blocks, and the engine that reads it"),
        # The memory figures are the server's, not the file's.
        statement="""
            SELECT 'version' AS name, CAST(version() AS VARCHAR) AS value
            UNION ALL SELECT 'database_size', database_size FROM pragma_database_size()
            UNION ALL SELECT 'block_size', CAST(block_size AS VARCHAR) FROM pragma_database_size()
            UNION ALL SELECT 'total_blocks', CAST(total_blocks AS VARCHAR) FROM pragma_database_size()
            UNION ALL SELECT 'used_blocks', CAST(used_blocks AS VARCHAR) FROM pragma_database_size()
            UNION ALL SELECT 'free_blocks', CAST(free_blocks AS VARCHAR) FROM pragma_database_size()
            UNION ALL SELECT 'wal_size', wal_size FROM pragma_database_size()
        """,
        stable_order=("name",),
    ),
    SystemReport(
        key="sequences",
        title=N_("Sequences"),
        description=N_("Counters a default takes its next value from, identities among them"),
        statement=f"""
            SELECT schema_name AS schema, sequence_name AS name, start_value AS start,
                   increment_by AS step, min_value AS minimum, max_value AS maximum,
                   cycle, sql AS definition
            FROM duckdb_sequences() WHERE {_OWN} AND NOT temporary
        """,  # noqa: S608 — conditions written in this module
        stable_order=("schema", "name"),
    ),
    SystemReport(
        key="types",
        title=N_("Types"),
        description=N_("The file's own types: enums, structs and other names for a type"),
        statement=f"""
            SELECT schema_name AS schema, type_name AS name, logical_type AS kind,
                   type_category AS category
            FROM duckdb_types() WHERE {_OWN} AND NOT internal
        """,  # noqa: S608 — conditions written in this module
        stable_order=("schema", "name"),
    ),
    SystemReport(
        key="macros",
        title=N_("Macros"),
        description=N_("Functions written in SQL and kept in the file"),
        statement=f"""
            SELECT schema_name AS schema, function_name AS name, function_type AS kind,
                   array_to_string(parameters, ', ') AS parameters,
                   macro_definition AS definition
            FROM duckdb_functions()
            WHERE {_OWN} AND NOT internal AND function_type IN ('macro', 'table_macro')
        """,  # noqa: S608 — conditions written in this module
        stable_order=("schema", "name", "parameters"),
    ),
    SystemReport(
        key="functions",
        title=N_("Functions"),
        description=N_("The functions DuckDB has built in, and how many signatures each has"),
        statement="""
            SELECT function_name AS name, function_type AS kind, count(*) AS signatures
            FROM duckdb_functions() WHERE internal
            GROUP BY function_name, function_type
        """,
        stable_order=("name", "kind"),
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    return node_id.startswith(SECTION_ID + "/")


def report_for(node_id: str) -> SystemReport | None:
    return _BY_ID.get(node_id)
