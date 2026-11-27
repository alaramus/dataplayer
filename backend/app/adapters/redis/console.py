"""`redis-cli` as a Redis connection's terminal (D286).

The real client, run in a container of the vendor's image with the terminal as
its screen, rather than a query console: Redis has commands, not statements,
and what is worth typing by hand — `MONITOR`, `SUBSCRIBE`, `MULTI` — is a
conversation rather than a result. `redis-cli` reads the password from
`REDISCLI_AUTH` itself, so it is never an argument.
"""

from app.adapters.cloud.signin import SignIn
from app.adapters.protocol import AdapterError
from app.adapters.redis.options import RedisOptions
from app.adapters.terminal import ConsoleProgram
from app.adapters.tls import program_paths, with_program_files
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# The image the managed Redis service runs, so a console on it fetches nothing
# new; one client speaks to every server this source supports.
IMAGE = "redis:8"

PASSWORD_VARIABLE = "REDISCLI_AUTH"


async def console_program(options: RedisOptions, signed: SignIn) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    # Signed in as the program starts; an issued token is good for fifteen
    # minutes, the connection it opens for longer (D449).
    environment = {} if signed.password is None else {PASSWORD_VARIABLE: signed.password}
    argv = ["redis-cli", "-h", options.host, "-p", str(options.port), "-n", str(options.database)]
    if signed.password is not None and signed.user:
        argv += ["--user", signed.user]
    settings = options.tls()
    if settings.enabled:
        # redis-cli verifies the server's certificate or nothing at all (D446).
        argv.append("--tls")
        paths = program_paths(settings)
        if not settings.verifies:
            argv.append("--insecure")
        elif paths.ca:
            argv += ["--cacert", paths.ca]
        if paths.certificate and paths.key:
            argv += ["--cert", paths.certificate, "--key", paths.key]
    wrapped, files = with_program_files(tuple(argv), settings)
    return ConsoleProgram(image=IMAGE, argv=wrapped, environment={**environment, **files})
