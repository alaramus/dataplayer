"""`rabbitmqadmin` as a RabbitMQ connection's terminal (D286, D328).

bash in the management image, where `rabbitmqadmin` 2 reads its node from a
TOML file the server composes: address, user, password, virtual host, CA
bundle. The file is written inside the container at start from a variable
that is unset before the prompt; every value reaches the shell through its
environment and is written with `printf '%s'`, so none is ever read as shell
syntax.
"""

from app.adapters.protocol import AdapterError
from app.adapters.rabbitmq.options import RabbitmqOptions
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import tunnel_of
from app.core.translation import say

# The test server's release (D328): its image carries rabbitmqadmin 2.
IMAGE = "rabbitmq:4.3.7-management"

CONFIG_PATH_VARIABLE = "RABBITMQADMIN_CONFIG_FILE_PATH"
CONFIG_VARIABLE = "DP_CONFIG"
CA_VARIABLE = "DP_CA"
RC_VARIABLE = "DP_RC"
NOTE_VARIABLE = "DP_NOTE"

CONFIG_PATH = "/tmp/rabbitmqadmin.conf"
CA_PATH = "/tmp/ca.pem"
RC_PATH = "/tmp/rabbitrc"

_TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def toml_string(text: str) -> str:
    """A TOML basic string: a quote, a backslash and every control character
    escaped, so nothing in the value can end it."""
    escaped = []
    for character in text:
        if character in _TOML_ESCAPES:
            escaped.append(_TOML_ESCAPES[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            escaped.append(f"\\u{ord(character):04X}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def node_config(options: RabbitmqOptions) -> str:
    """The `[default]` node rabbitmqadmin uses unless told another."""
    management = options.management()
    lines = [
        "[default]",
        f"base_uri = {toml_string(management)}",
        f"username = {toml_string(options.user)}",
        f"password = {toml_string(options.password.get_secret_value())}",
        f"virtual_host = {toml_string(options.vhost or '/')}",
    ]
    if management.startswith("https://"):
        lines.append("tls = true")
    if options.ca_certificate.strip():
        lines.append(f"ca_certificate_bundle_path = {toml_string(CA_PATH)}")
    return "\n".join(lines) + "\n"


def _rc() -> str:
    """bash's start file: the variables gone, completion, the greeting."""
    return (
        "\n".join(
            [
                f"unset {CONFIG_VARIABLE} {CA_VARIABLE} {RC_VARIABLE}",
                "source <(rabbitmqadmin shell completions --shell bash 2>/dev/null)",
                "PS1='rabbitmq> '",
                f'printf "%s\\n\\n" "${NOTE_VARIABLE}"',
                f"unset {NOTE_VARIABLE}",
            ]
        )
        + "\n"
    )


# The settings and the start file written, then bash in the shell's place.
_SCRIPT = (
    f'umask 077; printf "%s" "${CONFIG_VARIABLE}" > {CONFIG_PATH}; '
    f'[ -n "${CA_VARIABLE}" ] && printf "%s" "${CA_VARIABLE}" > {CA_PATH}; '
    f'printf "%s" "${RC_VARIABLE}" > {RC_PATH}; '
    f"exec bash --rcfile {RC_PATH} -i"
)


def console_program(options: RabbitmqOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # Its container cannot reach a port on this process's loopback (D339).
        raise AdapterError("config", say("A console does not go through an SSH tunnel yet"))
    environment = {
        CONFIG_PATH_VARIABLE: CONFIG_PATH,
        CONFIG_VARIABLE: node_config(options),
        RC_VARIABLE: _rc(),
        NOTE_VARIABLE: say(
            "rabbitmqadmin is set up for this connection. Try: "
            "rabbitmqadmin show overview · "
            "rabbitmqadmin list queues · "
            "rabbitmqadmin list exchanges"
        ),
    }
    if options.ca_certificate.strip():
        environment[CA_VARIABLE] = options.ca_certificate
    return ConsoleProgram(
        image=IMAGE, argv=("sh", "-c", _SCRIPT), environment=environment
    )
