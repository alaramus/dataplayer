"""`psql` as a PostgreSQL connection's terminal (D286).

The real client, run in a container of the vendor's image with the terminal as
its screen, beside the query console rather than instead of it: what is worth
typing by hand here — `\\d`, `\\watch`, `LISTEN` — is a conversation rather than
a result. The password is in `PGPASSWORD`, as for a backup, never an argument.
"""

from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tls import with_program_files
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# One image rather than the server's own major, which a backup needs: psql
# speaks to every older server, and this is the family the services registry
# pins, so a console on a managed database fetches nothing new.
IMAGE = "postgres:18"


async def console_program(session: PostgresSession, options: PostgresOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    # Asked as the program starts: an issued token is good for fifteen
    # minutes, the session it opens for as long as it lasts (D449).
    signed = await session.sign_in()
    environment = {} if signed.password is None else {"PGPASSWORD": signed.password}
    argv, files = with_program_files(
        ("psql", session.conninfo_without_password(signed.user)), options.tls()
    )
    return ConsoleProgram(image=IMAGE, argv=argv, environment={**environment, **files})
