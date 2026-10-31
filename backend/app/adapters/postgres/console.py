"""`psql` as a PostgreSQL connection's terminal (D286).

The real client, run in a container of the vendor's image with the terminal as
its screen, beside the query console rather than instead of it: what is worth
typing by hand here — `\\d`, `\\watch`, `LISTEN` — is a conversation rather than
a result. The password is in `PGPASSWORD`, as for a backup, never an argument.
"""

from app.adapters.postgres.options import PostgresOptions, PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# One image rather than the server's own major, which a backup needs: psql
# speaks to every older server, and this is the family the services registry
# pins, so a console on a managed database fetches nothing new.
IMAGE = "postgres:18"


def console_program(session: PostgresSession, options: PostgresOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    environment = (
        {"PGPASSWORD": options.password.get_secret_value()}
        if isinstance(options, PostgresUserPassword)
        else {}
    )
    return ConsoleProgram(
        image=IMAGE,
        argv=("psql", session.conninfo_without_password()),
        environment=environment,
    )
