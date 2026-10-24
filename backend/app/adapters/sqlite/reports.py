"""The reports a SQLite file and its library give about themselves (D55, D257).

Every statement is written here and is never composed from a request; a node
id selects one entry. Each reads SQLite's pragma functions or `sqlite_schema`,
on a connection that cannot write.

A report's id begins with a backslash, which no schema's id here does: the
one schema is `main` (D248).
"""

from dataclasses import dataclass, field

from app.core.translation import N_

SECTION_ID = "\\system"
SECTION_TITLE = N_("System")
SECTION_DESCRIPTION = N_("What this file and SQLite say about themselves")


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


def _setting(name: str, pragma: str) -> str:
    return f"SELECT '{name}' AS name, {pragma} AS value FROM pragma_{pragma}"  # noqa: S608 — names written in this module


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="file",
        title=N_("File"),
        description=N_("How the file is laid out: pages, its size, encoding and journal"),
        statement="\nUNION ALL\n".join(
            [
                "SELECT 'size_bytes' AS name, page_size * page_count AS value "
                "FROM pragma_page_size, pragma_page_count",
                _setting("page_size", "page_size"),
                _setting("page_count", "page_count"),
                _setting("freelist_count", "freelist_count"),
                _setting("encoding", "encoding"),
                _setting("journal_mode", "journal_mode"),
                _setting("auto_vacuum", "auto_vacuum"),
                _setting("user_version", "user_version"),
                _setting("application_id", "application_id"),
                _setting("schema_version", "schema_version"),
            ]
        ),
        stable_order=("name",),
    ),
    SystemReport(
        key="integrity",
        title=N_("Integrity"),
        description=N_("SQLite's quick check of the file: ok, or what is damaged"),
        statement="SELECT quick_check AS finding FROM pragma_quick_check",
        stable_order=("finding",),
    ),
    SystemReport(
        key="broken_keys",
        title=N_("Broken foreign keys"),
        description=N_("Rows whose foreign key points at a row that is not there"),
        statement=(
            'SELECT "table" AS "table", rowid AS row_id, parent AS refers_to, fkid AS key_number '
            "FROM pragma_foreign_key_check"
        ),
        stable_order=("table", "row_id", "key_number"),
    ),
    SystemReport(
        key="triggers",
        title=N_("Triggers"),
        description=N_("What runs when a table's rows change"),
        statement=(
            'SELECT name, tbl_name AS "table", sql AS definition '
            "FROM sqlite_schema WHERE type = 'trigger'"
        ),
        stable_order=("name",),
    ),
    SystemReport(
        key="functions",
        title=N_("Functions"),
        description=N_("The functions SQL can call here"),
        statement=(
            "SELECT name, type, narg AS arguments, builtin, enc AS encoding "
            "FROM pragma_function_list"
        ),
        stable_order=("name", "arguments", "type", "encoding"),
    ),
    SystemReport(
        key="modules",
        title=N_("Modules"),
        description=N_("The modules a virtual table can be made with here"),
        # Every pragma is a module of its own; they are not what this lists.
        statement="SELECT name FROM pragma_module_list WHERE substr(name, 1, 7) <> 'pragma_'",
        stable_order=("name",),
    ),
    SystemReport(
        key="collations",
        title=N_("Collations"),
        description=N_("The rules text can be compared by"),
        statement="SELECT name FROM pragma_collation_list",
        stable_order=("name",),
    ),
    SystemReport(
        key="compile_options",
        title=N_("Compile options"),
        description=N_("How this server's SQLite library was built"),
        statement="SELECT compile_options AS option FROM pragma_compile_options",
        stable_order=("option",),
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    return node_id.startswith(SECTION_ID + "/")


def report_for(node_id: str) -> SystemReport | None:
    return _BY_ID.get(node_id)
