"""The reports PostgreSQL publishes about itself (D55).

Every statement here is written in this repository and is never composed from
anything a request carries. A node id selects one entry from `REPORTS`; an id
naming no entry does not resolve. What a caller may still influence is what
`FetchRequest` allows anywhere else — which columns to filter and sort by, and
how many rows — and those are validated against the columns the server
described, exactly as they are for a relation.

Each statement ends in an `ORDER BY` of its own, because a report has neither a
key nor a physical position to break ties by (D42).
"""

from dataclasses import dataclass

from psycopg import sql

# PostgreSQL refuses to create a schema whose name begins with "pg_", so this
# id cannot collide with one a user could make. That is the server's guarantee,
# not a convention this project hopes holds.
SECTION_ID = "pg_dataplayer"
SECTION_TITLE = "System"
SECTION_DESCRIPTION = "What this server says about itself"


@dataclass(frozen=True)
class SystemReport:
    """One named answer, and the statement that produces it."""

    key: str
    title: str
    description: str
    statement: sql.SQL
    # How often this answer is worth reading again, when the report has an
    # opinion. Most do not: a list of tablespaces is the same list tomorrow.
    refresh_seconds: int | None = None
    stable_order: tuple[str, ...] = ()

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}.{self.key}"


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="processes",
        title="Processes",
        description="Backends connected now, and what each is waiting for",
        # The one report whose whole subject is what is happening this second.
        # Five, because a page of it read every second is a page nobody can
        # read, and a minute is long enough for the statement to have finished.
        refresh_seconds=5,
        statement=sql.SQL("""
            SELECT pid,
                   datname AS database,
                   usename AS "user",
                   application_name,
                   client_addr,
                   state,
                   wait_event_type,
                   wait_event,
                   pg_blocking_pids(pid) AS blocked_by,
                   backend_start,
                   xact_start,
                   query_start,
                   state_change,
                   backend_type,
                   query
            FROM pg_stat_activity
            ORDER BY pid
        """),
    ),
    SystemReport(
        key="settings",
        title="Settings",
        description="Every server setting, its source, and what changing it takes",
        # `context` is the useful column and is unreadable on its own, so the
        # server is asked to say what it means. The old application computed
        # the same sentence and this is where that belongs: once, on the
        # server, rather than in every screen that shows a setting.
        statement=sql.SQL("""
            SELECT name,
                   setting,
                   unit,
                   boot_val AS default_setting,
                   source,
                   category,
                   short_desc AS description,
                   context,
                   CASE context
                       WHEN 'postmaster' THEN 'Restart the server'
                       WHEN 'sighup' THEN 'Edit the configuration and reload it'
                       WHEN 'superuser-backend' THEN 'Superuser, at the start of a session'
                       WHEN 'backend' THEN 'At the start of a session'
                       WHEN 'superuser' THEN 'Superuser, with SET'
                       WHEN 'user' THEN 'With SET, in this session'
                       WHEN 'internal' THEN 'Fixed when the server was built'
                       ELSE context
                   END AS changed_by,
                   pending_restart
            FROM pg_settings
            ORDER BY category, name
        """),
    ),
    SystemReport(
        key="tablespaces",
        title="Tablespaces",
        description="Where the server keeps its files, with size and object count",
        statement=sql.SQL("""
            SELECT t.spcname AS name,
                   pg_tablespace_location(t.oid) AS location,
                   r.rolname AS owner,
                   t.spcname IN ('pg_default', 'pg_global') AS built_in,
                   pg_tablespace_size(t.oid) AS size_bytes,
                   pg_size_pretty(pg_tablespace_size(t.oid)) AS size,
                   count(c.oid) AS objects
            FROM pg_tablespace t
            LEFT JOIN pg_roles r ON r.oid = t.spcowner
            LEFT JOIN pg_class c ON c.reltablespace = t.oid
            GROUP BY t.oid, t.spcname, r.rolname
            ORDER BY t.spcname
        """),
    ),
    SystemReport(
        key="roles",
        title="Roles",
        description="Who may connect, and what each role is allowed to do",
        statement=sql.SQL("""
            SELECT rolname AS name,
                   rolsuper AS superuser,
                   rolcanlogin AS can_login,
                   rolcreatedb AS can_create_databases,
                   rolcreaterole AS can_create_roles,
                   rolreplication AS replication,
                   rolinherit AS inherits,
                   rolconnlimit AS connection_limit,
                   rolvaliduntil AS valid_until
            FROM pg_roles
            ORDER BY rolname
        """),
    ),
    SystemReport(
        key="routines",
        title="Routines",
        description="Functions and procedures defined outside the system schemas",
        statement=sql.SQL("""
            SELECT n.nspname AS schema,
                   p.proname AS name,
                   CASE p.prokind
                       WHEN 'f' THEN 'function'
                       WHEN 'p' THEN 'procedure'
                       WHEN 'a' THEN 'aggregate'
                       WHEN 'w' THEN 'window'
                   END AS kind,
                   pg_get_function_result(p.oid) AS returns,
                   pg_get_function_arguments(p.oid) AS arguments,
                   l.lanname AS language,
                   r.rolname AS owner
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_language l ON l.oid = p.prolang
            LEFT JOIN pg_roles r ON r.oid = p.proowner
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname, p.proname
        """),
    ),
    SystemReport(
        key="extensions",
        title="Extensions",
        # One report where the old application had two: this view already
        # states the installed version, so "available" and "installed" are the
        # same question asked once.
        description="Extensions this server offers, and which are installed",
        statement=sql.SQL("""
            SELECT name,
                   installed_version,
                   default_version,
                   installed_version IS NOT NULL AS installed,
                   comment AS description
            FROM pg_available_extensions
            ORDER BY installed_version IS NULL, name
        """),
    ),
)

_BY_KEY = {report.key: report for report in REPORTS}

# Named because a command is offered on this report and on no other. In one
# place so the action and the registry cannot disagree about which one it is.
EXTENSIONS_REPORT_ID = _BY_KEY["extensions"].node_id
# The same, for the report whose rows can be acted on one at a time (D70).
PROCESSES_REPORT_ID = _BY_KEY["processes"].node_id
# And for the one a role is made from (D79).
ROLES_REPORT_ID = _BY_KEY["roles"].node_id
TABLESPACES_REPORT_ID = _BY_KEY["tablespaces"].node_id


def report_for(node_id: str) -> SystemReport | None:
    """The report a node id names, or nothing when it names no report.

    Answers `None` rather than raising so that a caller can tell "this id is
    not mine" from "this id is mine and wrong", which is the difference
    between falling through to the relation path and a 404.
    """
    section, _, key = node_id.partition(".")
    if section != SECTION_ID:
        return None
    return _BY_KEY.get(key)


def is_section(node_id: str) -> bool:
    return node_id == SECTION_ID
