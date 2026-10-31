"""`redis-cli` as a Redis connection's terminal (D286).

The real client, run in a container of the vendor's image with the terminal as
its screen, rather than a query console: Redis has commands, not statements,
and what is worth typing by hand — `MONITOR`, `SUBSCRIBE`, `MULTI` — is a
conversation rather than a result. `redis-cli` reads the password from
`REDISCLI_AUTH` itself, so it is never an argument.
"""

from app.adapters.protocol import AdapterError
from app.adapters.redis.options import RedisOptions, RedisPassword
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# The image the managed Redis service runs, so a console on it fetches nothing
# new; one client speaks to every server this source supports.
IMAGE = "redis:8"

PASSWORD_VARIABLE = "REDISCLI_AUTH"


def console_program(options: RedisOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    environment = (
        {PASSWORD_VARIABLE: options.password.get_secret_value()}
        if isinstance(options, RedisPassword)
        else {}
    )
    return ConsoleProgram(
        image=IMAGE,
        argv=(
            "redis-cli",
            "-h",
            options.host,
            "-p",
            str(options.port),
            "-n",
            str(options.database),
        ),
        environment=environment,
    )
