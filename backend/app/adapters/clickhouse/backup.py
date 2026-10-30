"""What copies a ClickHouse database out, and what puts it back (D87, D278).

ClickHouse's own client speaks the native protocol, on a port the connection
does not know and a server need not publish; its `BACKUP` statement writes
where the server is, not where this application keeps files. So the program
is a short script in the official Python image — the one SQLite's backup runs
in — talking to the same HTTP interface the connection does.

The file is text: a heading line, one JSON line per object the database holds
with the statement that makes it as the server wrote it, then each table's
rows as tab-separated values ending in a line `\\.`, which no row can be, and a
last line saying the file is whole. A materialized view keeping its own rows
has them carried as a table's are.

Nothing here runs anything. It says what to run; a job runs it.
"""

import json
from collections.abc import Sequence

from app.adapters.clickhouse.options import ClickhouseOptions, ClickhouseUserPassword
from app.adapters.clickhouse.session import ClickhouseSession, read_profile
from app.adapters.protocol import AdapterError, BackupAvailability, BackupProgram
from app.adapters.tunnels import backup_through
from app.core.translation import say

IMAGE = "python:3.14-slim"

HEADING = b"-- DataPlayer ClickHouse backup 1\n"

# One script for the three: copy the database out, write a backup back over
# it, or say what a backup is of and whether it is whole. Tables are read one
# after another, not at one moment: ClickHouse has no transaction to read them
# in. A restore makes tables, loads their rows and only then makes views, so a
# materialized view is not fed the rows a second time.
_SCRIPT = r'''
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request

HEADING = b"-- DataPlayer ClickHouse backup 1\n"
END = b"-- end of backup\n"
ROWS_END = b"\\.\n"
EXCEPTION = b"\n__exception__\n"
HELD = 65536
KINDS = ("table", "view", "materialized")

what, base, user, database, path = sys.argv[1:6]
headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": os.environ.get("CLICKHOUSE_PASSWORD", "")}
context = ssl.create_default_context() if base.startswith("https") else None


class Refused(Exception):
    pass


def call(query, body=None, **settings):
    params = dict(settings, database=database)
    if body is None:
        body = query.encode()
    else:
        params["query"] = query
    request = urllib.request.Request(
        base + "?" + urllib.parse.urlencode(params), data=body, headers=headers, method="POST"
    )
    try:
        return urllib.request.urlopen(request, context=context)
    except urllib.error.HTTPError as error:
        raise Refused(error.read().decode(errors="replace")) from None


def rows(query):
    answer = call(query + " FORMAT JSONEachRow").read()
    return [json.loads(line) for line in answer.splitlines() if line]


def name(text):
    return "`" + text.replace("\\", "\\\\").replace("`", "\\`") + "`"


def item(line):
    return b"-- " + json.dumps(line).encode() + b"\n"


def copyable(engine):
    if engine in ("Log", "TinyLog", "StripeLog", "Memory"):
        return True
    return engine.endswith("MergeTree") and not engine.startswith(("Replicated", "Shared"))


def dump():
    version = rows("SELECT version() AS v")[0]["v"]
    found = rows(
        "SELECT name, engine, toString(uuid) AS uuid, create_table_query AS q FROM system.tables "
        "WHERE database = currentDatabase() AND NOT is_temporary ORDER BY name"
    )
    names = {table["name"] for table in found}
    made, left = [], []
    for table in found:
        title, engine = table["name"], table["engine"]
        if title.startswith((".inner.", ".inner_id.")):
            continue
        kind = {"View": "view", "MaterializedView": "materialized"}.get(engine)
        if kind is None and copyable(engine):
            kind = "table"
        if kind is None:
            left.append({"left_out": title, "engine": engine})
            continue
        own = kind == "table" or ".inner_id." + table["uuid"] in names or ".inner." + title in names
        made.append({"kind": kind, "name": title, "create": table["q"], "rows": own})
    made.sort(key=lambda entry: KINDS.index(entry["kind"]))
    columns = {}
    for column in rows(
        "SELECT table, name FROM system.columns WHERE database = currentDatabase() "
        "AND default_kind IN ('', 'DEFAULT') ORDER BY table, position"
    ):
        columns.setdefault(column["table"], []).append(column["name"])
    part = path + ".part"
    try:
        with open(part, "wb") as out:
            out.write(HEADING)
            for line in [{"server": version}, {"database": database}, *left]:
                out.write(item(line))
            for entry in made:
                out.write(item({key: entry[key] for key in ("kind", "name", "create")}))
            for entry in made:
                listed = columns.get(entry["name"], [])
                if not entry["rows"] or not listed:
                    continue
                out.write(item({"rows": entry["name"], "columns": listed}))
                answer = call(
                    "SELECT " + ", ".join(map(name, listed)) + " FROM " + name(entry["name"])
                    + " FORMAT TabSeparated"
                )
                held, wrote = b"", False
                while chunk := answer.read(1 << 20):
                    held += chunk
                    if len(held) > HELD:
                        out.write(held[:-HELD])
                        held, wrote = held[-HELD:], True
                framed = held if wrote else b"\n" + held
                at = framed.rfind(EXCEPTION)
                if at >= 0 and b"Code:" in framed[at:]:
                    raise Refused(framed[at + len(EXCEPTION):].decode(errors="replace"))
                out.write(held)
                out.write(ROWS_END)
            out.write(END)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)


def heading(source):
    if source.readline() != HEADING:
        raise Refused("This file is not a ClickHouse backup")
    said, line = [], source.readline()
    while line.startswith(b"-- {"):
        entry = json.loads(line[3:])
        if "rows" in entry:
            break
        said.append(entry)
        line = source.readline()
    return said, line


def restore():
    with open(path, "rb") as source:
        said, line = heading(source)
        made = [entry for entry in said if "create" in entry]
        for entry in reversed(made):
            call("DROP TABLE IF EXISTS " + name(entry["name"]) + " SYNC")
        for entry in made:
            if entry["kind"] == "table":
                call(entry["create"])
        kinds = {entry["name"]: entry["kind"] for entry in made}
        waiting = [entry for entry in made if entry["kind"] != "table"]

        def views():
            # A view may read another view: what fails waits for the rest.
            nonlocal waiting
            while waiting:
                failed = []
                for entry in waiting:
                    try:
                        call(entry["create"])
                    except Refused as refused:
                        failed.append((entry, refused))
                if len(failed) == len(waiting):
                    raise failed[-1][1]
                waiting = [entry for entry, _ in failed]

        def body():
            batch, size = [], 0
            while True:
                row = source.readline()
                if not row:
                    raise Refused("The backup ends partway through a table")
                if row == ROWS_END:
                    break
                batch.append(row)
                size += len(row)
                if size >= 1 << 20:
                    yield b"".join(batch)
                    batch, size = [], 0
            if batch:
                yield b"".join(batch)

        while line.startswith(b"-- {"):
            entry = json.loads(line[3:])
            if kinds.get(entry["rows"]) != "table":
                views()
            call(
                "INSERT INTO " + name(entry["rows"]) + " (" + ", ".join(map(name, entry["columns"]))
                + ") FORMAT TabSeparated",
                body(),
                input_format_tsv_empty_as_default="0",
            ).read()
            line = source.readline()
        views()
        if line != END:
            raise Refused("The backup is not whole")


def check():
    with open(path, "rb") as source:
        said, _ = heading(source)
        source.seek(0, os.SEEK_END)
        source.seek(max(0, source.tell() - HELD))
        tail = source.read()
    print("backup")
    for entry in said:
        if "server" in entry or "database" in entry:
            print(json.dumps(entry))
    before = tail[: -len(END)].rsplit(b"\n", 2)[-2:-1] if tail.endswith(END) else []
    whole = bool(before) and (before[0] == ROWS_END[:-1] or before[0].startswith(b"-- {"))
    print("whole" if whole else "partial")


try:
    {"out": dump, "in": restore, "check": check}[what]()
except Refused as refused:
    print((refused.args[0].strip().splitlines() or ["The program stopped"])[0][:400])
    sys.exit(1)
'''


class ClickhouseBackup:
    """How a ClickHouse database is copied out and put back."""

    def __init__(self, session: ClickhouseSession, options: ClickhouseOptions) -> None:
        self._session = session
        self._options = options
        # The server's release, read when the programs are named, which is
        # always before the archive is inspected.
        self._release: tuple[int, ...] | None = None

    async def backup_availability(self) -> BackupAvailability:
        if (through := backup_through(self._options.ssh_tunnel)) is not None:
            return through
        if not self._options.database:
            return BackupAvailability(
                available=False,
                reason=say("Name a database in the connection to back it up"),
            )
        try:
            await self._session.profile()
        except AdapterError:
            return BackupAvailability(
                available=False, reason=say("The server could not be asked which it is")
            )
        return BackupAvailability(available=True)

    async def backup_program(self, *, into: str) -> BackupProgram:
        """The connection's database, its objects and its rows, to one file."""
        return await self._program("out", into)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """The backup, written over the connection's database.

        Every object the backup holds is dropped first and made again, which
        is what makes this a restore rather than a merge and is why the route
        that asks for it insists on being told so. What the database holds
        that the backup does not is left alone.
        """
        return await self._program("in", from_file)

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        """What the backup is of, which server made it, and whether it is whole."""
        return await self._program("check", from_file)

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        """A whole backup of this database by this release or an older one.

        The statements in a backup name its database, so it is written back
        only into a database of that name; and they are in the words of the
        server that made it, which an older one may not know.
        """
        said = [line.strip() for line in lines if line.strip()]
        if not said or said[0] != "backup":
            raise ValueError(say("This file is not a ClickHouse backup"))
        facts: dict[str, str] = {}
        for line in said[1:-1]:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                facts.update({key: str(value) for key, value in entry.items()})
        if facts.get("database") != self._options.database:
            raise ValueError(
                say(
                    "This is a backup of the database {name}, and is restored into a connection naming it",
                    name=facts.get("database", "?"),
                )
            )
        made = read_profile(facts.get("server", "0.0"))
        if self._release is not None and made.version[:2] > self._release[:2]:
            raise ValueError(
                say(
                    "This backup was made by ClickHouse {made}, newer than this server",
                    made=made.text,
                )
            )
        if said[-1] != "whole":
            raise ValueError(say("This backup is not whole and cannot be restored"))

    def restore_archive_reason(self, head: bytes) -> str | None:
        if head.startswith(HEADING):
            return None
        return say("This file is not a ClickHouse backup")

    async def _program(self, what: str, path: str) -> BackupProgram:
        offer = await self.backup_availability()
        if not offer.available:
            raise ValueError(offer.reason)
        self._release = (await self._session.profile()).version
        options = self._options
        scheme = "https" if options.secure else "http"
        host = f"[{options.host}]" if ":" in options.host else options.host
        return BackupProgram(
            image=IMAGE,
            argv=(
                "python",
                "-I",
                "-c",
                _SCRIPT,
                what,
                f"{scheme}://{host}:{options.port}/",
                options.user,
                options.database,
                path,
            ),
            environment=self._environment(),
        )

    def _environment(self) -> dict[str, str]:
        """The password in the environment: an argument is visible to anything
        on the machine that can list processes."""
        if isinstance(self._options, ClickhouseUserPassword):
            return {"CLICKHOUSE_PASSWORD": self._options.password.get_secret_value()}
        return {}
