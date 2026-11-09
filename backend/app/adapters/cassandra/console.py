"""`cqlsh` as a Cassandra connection's terminal (D286, D344).

The shell people already know, run in a container of Cassandra's image with
the terminal as its screen. ScyllaDB's own image starts its server whatever
it is given, so Cassandra's cqlsh speaks to both; it is CQL either way.

The node is named in the variables cqlsh reads (`CQLSH_HOST`, `CQLSH_PORT`);
the user and password go into its credentials file, written inside the
container with `printf '%s'` from a variable that is unset before cqlsh
starts, so neither is an argument nor read as shell syntax. cqlsh reads the
user through ConfigParser, which reads `%` as the start of a substitution, so
a `%` in it is doubled; it reads the password raw.
"""

from app.adapters.cassandra.options import CassandraOptions, CassandraUserPassword
from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# The test server's release (D340); its image carries cqlsh 6.
IMAGE = "cassandra:5.0"

CREDENTIALS_VARIABLE = "DP_CREDENTIALS"
CREDENTIALS_PATH = "/tmp/cqlsh-credentials"
# Where cqlsh finds the CA bundle when TLS is checked.
CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def credentials(options: CassandraUserPassword) -> str:
    """cqlsh's credentials file: `[plain_text_auth]`, a user and a password."""
    user = options.user
    password = options.password.get_secret_value()
    if any(char in value for value in (user, password) for char in "\r\n"):
        raise AdapterError(
            "config",
            say("cqlsh cannot read a user or a password that holds a line break"),
        )
    return f"[plain_text_auth]\nusername = {user.replace('%', '%%')}\npassword = {password}\n"


def _script(signed_in: bool, keyspace: str, secure: bool) -> str:
    """The credentials written, the variable gone, then cqlsh in the shell's place."""
    arguments = []
    if signed_in:
        arguments.append(f"--credentials {CREDENTIALS_PATH}")
    if keyspace:
        arguments.append('-k "$DP_KEYSPACE"')
    if secure:
        arguments.append("--ssl")
    head = (
        f'umask 077; printf "%s" "${CREDENTIALS_VARIABLE}" > {CREDENTIALS_PATH}; '
        f"unset {CREDENTIALS_VARIABLE}; "
        if signed_in
        else ""
    )
    return head + "exec cqlsh " + " ".join(arguments)


def console_program(options: CassandraOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # Its container cannot reach a port on this process's loopback.
        raise AdapterError(
            "config", say("A console does not go through an SSH tunnel yet")
        )
    environment = {
        "CQLSH_HOST": options.host,
        "CQLSH_PORT": str(options.port),
    }
    signed_in = isinstance(options, CassandraUserPassword)
    if isinstance(options, CassandraUserPassword):
        environment[CREDENTIALS_VARIABLE] = credentials(options)
    if options.keyspace:
        environment["DP_KEYSPACE"] = options.keyspace
    if options.secure:
        environment["SSL_VALIDATE"] = "true"
        environment["SSL_CERTFILE"] = CA_BUNDLE
    return ConsoleProgram(
        image=IMAGE,
        argv=("bash", "-c", _script(signed_in, options.keyspace, options.secure)),
        environment=environment,
    )
