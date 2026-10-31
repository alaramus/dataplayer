"""`zkCli.sh` as a ZooKeeper connection's terminal (D286, D299).

The real client from the image the test server runs, connected to the server
and root path the connection names. zkCli takes a digest identity only as the
interactive `addauth`, never from its environment or arguments, so a digest
connection's terminal opens anonymous with one line above it saying how to
sign in; the password is not printed and not passed (D299).

The address and that line reach the shell through its environment and are
expanded in double quotes, so neither is ever read as shell syntax.
"""

from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import tunnel_of
from app.adapters.zookeeper.options import ZookeeperDigest, ZookeeperOptions
from app.adapters.zookeeper.session import compose_url
from app.core.translation import say

IMAGE = "zookeeper:3.9"

SERVER_VARIABLE = "ZK_SERVER"
NOTE_VARIABLE = "ZK_NOTE"

# zkCli logs every step of its session to the screen at INFO, two dozen lines
# above its prompt; the image's own logback.xml sets that and a system property
# cannot lower it, so the client is given a configuration of its own.
_QUIET = "/tmp/zkcli-logback.xml"
_FLAGS = f"-Dlogback.configurationFile={_QUIET}"

# Quiet logging, the note when there is one, then zkCli in the shell's place.
_SCRIPT = (
    "printf '%s' '<configuration><root level=\"OFF\"/></configuration>' "
    f"> {_QUIET}; "
    f'[ -n "${NOTE_VARIABLE}" ] && printf "%s\\n\\n" "${NOTE_VARIABLE}"; '
    f'exec zkCli.sh -server "${SERVER_VARIABLE}"'
)


def console_program(options: ZookeeperOptions) -> ConsoleProgram:
    if tunnel_of(options.ssh_tunnel) is not None:
        # The container cannot reach a port on this process's loopback.
        raise AdapterError(
            "config", say("A console does not go through an SSH tunnel yet")
        )
    environment = {
        "CLIENT_JVMFLAGS": _FLAGS,
        SERVER_VARIABLE: compose_url(
            host=options.host, port=options.port, chroot=options.chroot
        ),
    }
    if isinstance(options, ZookeeperDigest):
        environment[NOTE_VARIABLE] = say(
            "zkCli is not signed in. To read znodes with a digest ACL, type: "
            "addauth digest {user}:<password>",
            user=options.user,
        )
    return ConsoleProgram(
        image=IMAGE, argv=("sh", "-c", _SCRIPT), environment=environment
    )
