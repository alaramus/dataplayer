"""What program copies this server out, and what puts it back.

`pg_dump` and `pg_restore` are programs rather than statements, and their
version has to match: a dump of a server newer than the program is refused by
the program itself. So the source is asked what its version is, and the answer
decides the image — `postgres:<major>`, the same family the services registry
pins (D87).

Nothing here runs anything. It says what to run; a job runs it.
"""

from app.adapters.postgres.options import PostgresOptions, PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import BackupProgram

# The oldest image family this will ask for. A server older than this is a
# server whose dump belongs to somebody with the right tools, not to a guess.
OLDEST_SUPPORTED_MAJOR = 13


class PostgresBackup:
    """How a PostgreSQL server is copied out and put back."""

    def __init__(self, session: PostgresSession, options: PostgresOptions) -> None:
        self._session = session
        self._options = options

    async def backup_program(self, *, into: str) -> BackupProgram:
        """`pg_dump` in its own custom format, to one file.

        The custom format rather than plain SQL: it is what `pg_restore` reads,
        it compresses, and it can be restored selectively later. `--no-owner`
        and `--no-privileges` because the owner of a database somebody backs up
        here is a role of *that* server, and a restore elsewhere would fail on
        a role that does not exist.
        """
        return BackupProgram(
            image=await self._image(),
            argv=(
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--file={into}",
                self._connection_argument(),
            ),
            environment=self._environment(),
        )

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """`pg_restore`, which replaces what is there.

        `--clean --if-exists` is what makes a restore a restore rather than a
        merge: every object in the dump is dropped in the target first. That
        is the destructive part, and it is why the route that asks for this
        insists on being told so in as many words.
        """
        return BackupProgram(
            image=await self._image(),
            argv=(
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                f"--dbname={self._connection_argument()}",
                from_file,
            ),
            environment=self._environment(),
        )

    async def _image(self) -> str:
        """The image of the server's own major version.

        Asked of the server rather than assumed: a dump taken by an older
        program of a newer server is refused, and this is the one fact that
        decides whether it will work.
        """
        rows = await self._session.query("SHOW server_version_num")
        number = int(str(rows[0]["server_version_num"]))
        major = number // 10000
        if major < OLDEST_SUPPORTED_MAJOR:
            raise ValueError(
                "This server is older than any version this application can "
                "back up"
            )
        return f"postgres:{major}"

    def _connection_argument(self) -> str:
        """Where to connect, as one string, with no password in it.

        The password goes in the environment: an argument is visible to
        anything on the machine that can list processes, and libpq documents
        `PGPASSWORD` for exactly this.
        """
        return self._session.conninfo_without_password()

    def _environment(self) -> dict[str, str]:
        if isinstance(self._options, PostgresUserPassword):
            return {"PGPASSWORD": self._options.password.get_secret_value()}
        return {}
