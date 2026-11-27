"""What program copies a MySQL database out, and what puts it back (D87, D240).

`mysqldump` and the `mysql` client are programs, and MariaDB ships its own:
`mariadb-dump` and `mariadb`. A dump by a program of another family or an
older version is a dump that may not restore, so the server is asked which it
is and the answer decides the image — `mysql:8.4`, `mariadb:11.4` — the same
families the services registry pins.

One database: the one the connection names. A dump of every database a user
can see would restore into databases the restoring connection never named.

Nothing here runs anything. It says what to run; a job runs it.
"""

import re
from collections.abc import Sequence

from app.adapters.cloud.signin import SignIn
from app.adapters.mysql.options import MysqlOptions
from app.adapters.mysql.session import MysqlSession, ServerProfile
from app.adapters.protocol import AdapterError, BackupAvailability, BackupProgram
from app.adapters.tls import program_paths, with_program_files
from app.adapters.tunnels import backup_through
from app.core.translation import say

# The first lines a dump begins with: MariaDB's newer programs put a line that
# turns on their sandbox mode before the heading.
_MYSQL_TLS = {
    "disabled": "DISABLED",
    "preferred": "PREFERRED",
    "required": "REQUIRED",
    "verify_ca": "VERIFY_CA",
    "verify_full": "VERIFY_IDENTITY",
}
_MARIADB_TLS = {
    "disabled": ["--skip-ssl"],
    "preferred": ["--skip-ssl-verify-server-cert"],
    "required": ["--ssl", "--skip-ssl-verify-server-cert"],
    "verify_ca": ["--ssl", "--ssl-verify-server-cert"],
    "verify_full": ["--ssl", "--ssl-verify-server-cert"],
}
_HEADING = re.compile(r"-- (MySQL|MariaDB) dump [0-9]")
_INSPECTED_LINES = 5


class MysqlBackup:
    """How a MySQL or MariaDB database is copied out and put back."""

    def __init__(self, session: MysqlSession, options: MysqlOptions) -> None:
        self._session = session
        self._options = options
        # Which server the archive is checked against: read when the programs
        # are named, which is always before the archive is inspected.
        self._flavour: str | None = None

    async def backup_availability(self) -> BackupAvailability:
        if (through := backup_through(self._options.ssh_tunnel)) is not None:
            return through
        if not self._options.database:
            return BackupAvailability(
                available=False,
                reason=say("Name a database in the connection to back it up"),
            )
        if self._options.database.startswith("-"):
            # The dump program takes the database as an argument of its own,
            # and one beginning with a dash would be read as an option.
            return BackupAvailability(
                available=False,
                reason=say("A database whose name begins with a dash cannot be backed up here"),
            )
        try:
            profile = await self._session.profile()
        except AdapterError:
            return BackupAvailability(
                available=False, reason=say("The server could not be asked which it is")
            )
        if profile.tidb:
            # Its own dump program is Dumpling, which no image here runs (D378).
            return BackupAvailability(
                available=False, reason=say("TiDB is not backed up here yet")
            )
        return BackupAvailability(available=True)

    async def backup_program(self, *, into: str) -> BackupProgram:
        """A dump of one database as SQL, to one file.

        One transaction for a consistent dump of InnoDB tables without locking
        them; routines, triggers and events with their tables; binary values
        as hexadecimal, so the file is text. No tablespaces, which need a
        privilege the dump does not otherwise. No GTID statement on MySQL,
        which a restore into a server with its own replication would refuse.
        """
        profile = await self._profile()
        signed = await self._session.sign_in()
        program = "mariadb-dump" if profile.mariadb else "mysqldump"
        argv = [
            program,
            *self._reach(profile, signed.user),
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            "--hex-blob",
            "--no-tablespaces",
        ]
        if not profile.mariadb:
            argv.append("--set-gtid-purged=OFF")
        argv += [f"--result-file={into}", self._database()]
        return self._program(_image(profile), tuple(argv), signed)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """The client, reading the dump into the connection's database.

        A dump drops each table, view and routine it holds before it makes it
        again, which is what makes this a restore rather than a merge and is
        why the route that asks for it insists on being told so. The client
        stops at the first statement the server refuses.
        """
        profile = await self._profile()
        signed = await self._session.sign_in()
        program = "mariadb" if profile.mariadb else "mysql"
        return self._program(
            _image(profile),
            (
                program,
                *self._reach(profile, signed.user),
                f"--database={self._database()}",
                f"--execute=source {from_file}",
            ),
            signed,
        )

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        """The first lines of the archive, which say what made it."""
        profile = await self._profile()
        return BackupProgram(
            image=_image(profile),
            argv=("head", "-n", str(_INSPECTED_LINES), from_file),
            environment={"LC_ALL": "C"},
        )

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        """A dump of this family of server, or a refusal before anything runs.

        A file in the backups folder is anything somebody put there; a dump by
        the other family carries collations and statements this server may not
        know, and fails part of the way through.
        """
        made_by = next(
            (match[1].lower() for line in lines[:_INSPECTED_LINES] if (match := _HEADING.match(line))),
            None,
        )
        if made_by is None:
            raise ValueError(say("This file is not a MySQL or MariaDB backup"))
        if self._flavour is not None and made_by != self._flavour:
            raise ValueError(
                say("A MariaDB backup is restored into MariaDB")
                if made_by == "mariadb"
                else say("A MySQL backup is restored into MySQL")
            )

    def restore_archive_reason(self, head: bytes) -> str | None:
        """A dump says what made it in its first lines; which family is
        checked against the server once the inventory is read."""
        lines = head.decode("utf-8", errors="replace").splitlines()[:_INSPECTED_LINES]
        if any(_HEADING.match(line) for line in lines):
            return None
        return say("This file is not a MySQL or MariaDB backup")

    async def _profile(self) -> ServerProfile:
        offer = await self.backup_availability()
        if not offer.available:
            raise ValueError(offer.reason)
        profile = await self._session.profile()
        self._flavour = profile.flavour
        return profile

    def _program(self, image: str, argv: tuple[str, ...], signed: SignIn) -> BackupProgram:
        """The client, signed in as it starts, its TLS files written (D447).

        The password goes in the variable both clients read for it: an
        argument is visible to anything that can list processes. An issued
        token is fresh when the program starts; the connection it opens
        outlives it (D449).
        """
        wrapped, files = with_program_files(argv, self._options.tls())
        environment = {} if signed.password is None else {"MYSQL_PWD": signed.password}
        return BackupProgram(image=image, argv=wrapped, environment={**environment, **files})

    def _reach(self, profile: ServerProfile, user: str) -> list[str]:
        """Where to connect, with no password: that goes in the environment.

        TLS as the connection has it (D446). MySQL's client names the modes as
        this does; MariaDB's has a switch and a check of the certificate that
        includes its name, so Verify CA is held to the name there too.
        """
        options = self._options
        reach = [
            f"--host={options.host}",
            f"--port={options.port}",
            f"--user={user}",
            "--default-character-set=utf8mb4",
        ]
        # An RDS token goes over TLS in the clear, which MySQL's client does
        # only when told; MariaDB's offers the plugin by itself (D453).
        if options.cleartext and not profile.mariadb:
            reach.append("--enable-cleartext-plugin")
        settings = options.tls()
        if profile.mariadb:
            reach += _MARIADB_TLS[settings.mode]
        else:
            reach.append(f"--ssl-mode={_MYSQL_TLS[settings.mode]}")
        paths = program_paths(settings)
        if settings.verifies:
            reach.append(f"--ssl-ca={paths.ca}" if paths.ca else "--ssl-capath=/etc/ssl/certs")
        if paths.certificate and paths.key:
            reach += [f"--ssl-cert={paths.certificate}", f"--ssl-key={paths.key}"]
        return reach

    def _database(self) -> str:
        return self._options.database or ""



def _image(profile: ServerProfile) -> str:
    """The image of the server's own family and release: `mysql:8.4`."""
    release = ".".join(str(part) for part in profile.version[:2])
    return f"{'mariadb' if profile.mariadb else 'mysql'}:{release}"
