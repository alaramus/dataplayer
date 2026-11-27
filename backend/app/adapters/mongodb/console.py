"""`mongosh` as a MongoDB connection's terminal (D286).

The shell the user chose over a console that parses some of its syntax: the
real one, run in a container of the vendor's image with the terminal as its
screen. It starts without a connection and makes one from an address in its
environment, which it then forgets, so the password is never an argument.
"""

from app.adapters.mongodb.session import (
    MongodbSession,
    auth_query,
    compose_url_with_password,
    program_tls,
)
from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tls import with_program_files
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# The vendor's server image, which carries mongosh; one shell speaks to every
# server this source supports.
IMAGE = "mongo:8.0"

URI_VARIABLE = "DP_MONGODB_URI"

_CONNECT = (
    f"(() => {{ db = connect(process.env.{URI_VARIABLE}); delete process.env.{URI_VARIABLE} }})()"
)


async def console_program(session: MongodbSession) -> ConsoleProgram:
    options = session.options
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    # Signed in as the program starts; a role's keys last an hour (D449).
    signed = await session.credentials()
    address = compose_url_with_password(
        host=options.host,
        port=options.port,
        user=signed.user,
        database=options.database,
        auth_source=signed.auth_source,
        tls=options.tls().enabled,
        tls_query=[*program_tls(options.tls()), *auth_query(signed)],
        password=signed.password,
        srv=options.srv,
    )
    argv, files = with_program_files(
        ("mongosh", "--nodb", "--norc", "--quiet", "--shell", "--eval", _CONNECT), options.tls()
    )
    return ConsoleProgram(image=IMAGE, argv=argv, environment={URI_VARIABLE: address, **files})
