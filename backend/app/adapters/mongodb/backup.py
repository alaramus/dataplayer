"""What copies a MongoDB database out, and what puts it back (D87, D292).

The vendor's own tools, `mongodump` and `mongorestore`, from the image the
console runs in (D286): one gzipped archive of the connection's database, its
collections, views and indexes. Neither tool reads a password from the
environment, so a line of shell writes the address from the environment into
a configuration file inside the container, readable by nobody else, and the
tool reads it there; the password is never an argument.

Nothing here runs anything. It says what to run; a job runs it.
"""

import re
from collections.abc import Sequence

from app.adapters.mongodb.console import IMAGE
from app.adapters.mongodb.options import MongodbOptions
from app.adapters.mongodb.session import MongodbSession, compose_url_with_password
from app.adapters.protocol import AdapterError, BackupAvailability, BackupProgram
from app.adapters.tunnels import backup_through
from app.core.translation import say

ADDRESS = "DP_MONGODB_URI"
# The first bytes of a gzip stream, which a `--gzip` archive is.
GZIP = b"\x1f\x8b"

_CONFIG = f'umask 077; printf \'uri: "%s"\\n\' "${ADDRESS}" > /tmp/dataplayer.yaml && unset {ADDRESS} && '

# The address is quoted part by part (`compose_url_with_password`), so it holds
# no quote or backslash to break out of the YAML string.
_SCRIPTS = {
    "out": _CONFIG + 'exec mongodump --config=/tmp/dataplayer.yaml --db="$1" --archive="$2" --gzip --quiet',
    "in": _CONFIG
    + 'exec mongorestore --config=/tmp/dataplayer.yaml --archive="$2" --gzip --drop'
    + ' --nsInclude="$1.*" --quiet',
    # Whole when gzip reads it to its end; what it holds from the archive's
    # prelude, which a dry run lists without writing anything.
    # A dry run still signs in to the server, so it reads the address as well.
    "check": _CONFIG
    + 'gzip -t "$2" && mongorestore --config=/tmp/dataplayer.yaml --archive="$2" --gzip'
    + ' --dryRun -v --nsInclude="*" && echo dataplayer-whole',
}

_PRELUDE = re.compile(r"archive prelude `([^`]+)`")


class MongodbBackup:
    def __init__(self, session: MongodbSession, options: MongodbOptions) -> None:
        self._session = session
        self._options = options

    async def backup_availability(self) -> BackupAvailability:
        if (through := backup_through(self._options.ssh_tunnel)) is not None:
            return through
        if not self._options.database:
            return BackupAvailability(
                available=False, reason=say("Name a database in the connection to back it up")
            )
        try:
            await self._session.profile()
        except AdapterError:
            return BackupAvailability(
                available=False, reason=say("The server could not be asked which it is")
            )
        return BackupAvailability(available=True)

    async def backup_program(self, *, into: str) -> BackupProgram:
        """The connection's database, its collections, views and indexes, to one archive."""
        return await self._program("out", into)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """The archive, written over the connection's database.

        Every collection the archive holds is dropped first and made again;
        what the database holds that the archive does not is left alone.
        """
        return await self._program("in", from_file)

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        return await self._program("check", from_file)

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        """A whole archive of this connection's database and of no other."""
        if not any(line.strip() == "dataplayer-whole" for line in lines):
            raise ValueError(say("This backup is not whole and cannot be restored"))
        databases = {
            found.group(1).split(".", 1)[0] for line in lines if (found := _PRELUDE.search(line))
        }
        others = sorted(databases - {self._options.database})
        if others:
            raise ValueError(
                say(
                    "This is a backup of the database {name}, and is restored into a connection naming it",
                    name=others[0],
                )
            )

    def restore_archive_reason(self, head: bytes) -> str | None:
        if head.startswith(GZIP):
            return None
        return say("This file is not a MongoDB backup")

    async def _program(self, what: str, path: str) -> BackupProgram:
        offer = await self.backup_availability()
        if not offer.available:
            raise ValueError(offer.reason)
        user, password, auth_source = self._session.credentials()
        options = self._options
        address = compose_url_with_password(
            host=options.host,
            port=options.port,
            user=user,
            auth_source=auth_source,
            tls=options.tls,
            password=password,
        )
        return BackupProgram(
            image=IMAGE,
            argv=("sh", "-c", _SCRIPTS[what], "sh", options.database, path),
            environment={ADDRESS: address},
        )
