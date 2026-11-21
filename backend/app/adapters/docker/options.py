"""Which SSH connection reaches the daemon, and where its socket is (D405).

No address of its own: the daemon is on the machine the SSH connection signs
in to, and its socket is forwarded through that connection. The daemon this
server runs on is never a source, so there is nothing to choose between.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.layout import layout
from app.adapters.options import TUNNEL_REFERENCE
from app.core.translation import N_, say

DEFAULT_SOCKET = "/var/run/docker.sock"
PODMAN_SOCKET = "/run/podman/podman.sock"

_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_SOCKET = re.compile(r"^/[^\x00]*$")


def socket_problem(path: str) -> str | None:
    """Why a socket path is not one to forward, or nothing."""
    if not _SOCKET.match(path) or len(path.encode()) > 255:
        return say("A socket is an absolute path of at most 255 bytes")
    if any(part in {".", ".."} for part in path.split("/")):
        return say("A socket path has no . or .. parts")
    return None


class DockerOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required: there is no "directly" — this server's own daemon is never a
    # source (D405).
    ssh_connection: str = Field(
        pattern=_UUID,
        title=N_("SSH connection"),
        description=N_(
            "One of your SSH connections, signed in to the machine the daemon runs on"
        ),
        json_schema_extra=layout(purpose=TUNNEL_REFERENCE),
    )
    socket: str = Field(
        default=DEFAULT_SOCKET,
        title=N_("Socket"),
        description=N_(
            "The daemon's socket on that machine; rootless Docker and Podman keep it elsewhere"
        ),
        json_schema_extra=layout(),
    )

    @field_validator("socket")
    @classmethod
    def _socket_is_a_path(cls, path: str) -> str:
        problem = socket_problem(path)
        if problem is not None:
            raise ValueError(problem)
        return path
