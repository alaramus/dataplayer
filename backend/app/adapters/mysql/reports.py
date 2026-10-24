"""The reports a MySQL or MariaDB server publishes about itself (D55, D237).

Every statement is written here and is never composed from a request; a node
id selects one entry. The two servers keep some of these in different places —
MySQL's variables and status are in performance_schema, MariaDB's in
information_schema — so an entry has a statement per flavour where they
differ. No statement holds a `%`: each runs with parameters (see
`identifier`).

A report's id begins with a backslash followed by a letter, which a database's
id never does: `ids.database_id` writes every backslash in a name as two.
"""

from dataclasses import dataclass, field

from app.adapters.mysql.session import ServerProfile
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
    # The statement where MariaDB keeps the answer elsewhere.
    mariadb: str | None = None
    # The statement for a MySQL older than the version it names.
    mysql_before: tuple[tuple[int, ...], str] | None = None
    refresh_seconds: int | None = None
    stable_order: tuple[str, ...] = field(default=())

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"

    def statement_for(self, profile: ServerProfile) -> str:
        if profile.mariadb:
            return self.mariadb or self.statement
        if self.mysql_before is not None and profile.version < self.mysql_before[0]:
            return self.mysql_before[1]
        return self.statement


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="processes",
        title=N_("Processes"),
        description=N_("Connections open now, and what each is running"),
        refresh_seconds=5,
        # MySQL warns on every read of information_schema.PROCESSLIST that it
        # will go. Its replacement arrived in 8.0.22; performance_schema.threads
        # is older but refused to a user without SELECT on it, where both lists
        # show such a user its own connections.
        statement="""
            SELECT ID AS id, USER AS user, HOST AS host, DB AS `database`,
                   COMMAND AS command, TIME AS seconds, STATE AS state, INFO AS query
            FROM performance_schema.processlist
        """,
        mysql_before=(
            (8, 0, 22),
            """
            SELECT ID AS id, USER AS user, HOST AS host, DB AS `database`,
                   COMMAND AS command, TIME AS seconds, STATE AS state, INFO AS query
            FROM information_schema.PROCESSLIST
        """,
        ),
        mariadb="""
            SELECT ID AS id, USER AS user, HOST AS host, DB AS `database`,
                   COMMAND AS command, TIME AS seconds, STATE AS state, INFO AS query
            FROM information_schema.PROCESSLIST
        """,
        stable_order=("id",),
    ),
    SystemReport(
        key="variables",
        title=N_("Variables"),
        description=N_("Every global setting of the server, as it is now"),
        statement="""
            SELECT VARIABLE_NAME AS name, VARIABLE_VALUE AS value
            FROM performance_schema.global_variables
        """,
        mariadb="""
            SELECT LOWER(VARIABLE_NAME) AS name, VARIABLE_VALUE AS value
            FROM information_schema.GLOBAL_VARIABLES
        """,
        stable_order=("name",),
    ),
    SystemReport(
        key="status",
        title=N_("Status"),
        description=N_("Counters the server keeps about itself since it started"),
        refresh_seconds=10,
        statement="""
            SELECT VARIABLE_NAME AS name, VARIABLE_VALUE AS value
            FROM performance_schema.global_status
        """,
        mariadb="""
            SELECT LOWER(VARIABLE_NAME) AS name, VARIABLE_VALUE AS value
            FROM information_schema.GLOBAL_STATUS
        """,
        stable_order=("name",),
    ),
    SystemReport(
        key="users",
        title=N_("Users"),
        description=N_("Accounts that may connect, and from where"),
        statement="""
            SELECT User AS user, Host AS host, plugin AS authentication,
                   account_locked AS locked, password_expired AS password_expired
            FROM mysql.user
        """,
        # MariaDB's mysql.user is a view that keeps no lock flag, and holds
        # roles beside accounts.
        mariadb="""
            SELECT User AS user, Host AS host, plugin AS authentication,
                   is_role AS role, password_expired AS password_expired
            FROM mysql.user
        """,
        stable_order=("user", "host"),
    ),
    SystemReport(
        key="routines",
        title=N_("Routines"),
        description=N_("Functions and procedures outside the server's own databases"),
        statement="""
            SELECT ROUTINE_SCHEMA AS `database`, ROUTINE_NAME AS name,
                   ROUTINE_TYPE AS kind, DTD_IDENTIFIER AS returns,
                   DEFINER AS definer, CREATED AS created
            FROM information_schema.ROUTINES
            WHERE ROUTINE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
        """,
        stable_order=("database", "name"),
    ),
    SystemReport(
        key="triggers",
        title=N_("Triggers"),
        description=N_("What runs when rows of a table change"),
        statement="""
            SELECT TRIGGER_SCHEMA AS `database`, TRIGGER_NAME AS name,
                   EVENT_OBJECT_TABLE AS `table`, ACTION_TIMING AS timing,
                   EVENT_MANIPULATION AS event, DEFINER AS definer
            FROM information_schema.TRIGGERS
            WHERE TRIGGER_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
        """,
        stable_order=("database", "name"),
    ),
    SystemReport(
        key="events",
        title=N_("Events"),
        description=N_("What the server's scheduler runs, and when"),
        statement="""
            SELECT EVENT_SCHEMA AS `database`, EVENT_NAME AS name, STATUS AS status,
                   EVENT_TYPE AS kind, INTERVAL_VALUE AS every, INTERVAL_FIELD AS unit,
                   LAST_EXECUTED AS last_run, DEFINER AS definer
            FROM information_schema.EVENTS
        """,
        stable_order=("database", "name"),
    ),
    SystemReport(
        key="engines",
        title=N_("Engines"),
        description=N_("Storage engines this server offers, and which is the default"),
        statement="""
            SELECT ENGINE AS engine, SUPPORT AS support, TRANSACTIONS AS transactions,
                   COMMENT AS description
            FROM information_schema.ENGINES
        """,
        stable_order=("engine",),
    ),
)

_BY_ID = {report.node_id: report for report in REPORTS}

PROCESSES_REPORT_ID = _BY_ID[f"{SECTION_ID}/processes"].node_id


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str) -> bool:
    """Whether an id is the section's or below it, whether or not it names a report."""
    return node_id == SECTION_ID or node_id.startswith(f"{SECTION_ID}/")


def report_for(node_id: str) -> SystemReport | None:
    return _BY_ID.get(node_id)
