"""A database reached through one of its owner's SSH connections (D282).

The options name the SSH connection by id, the way they name a key (D146), and
the server hands the driver a way through it in `AdapterContext.tunnels`. The
driver learns a local address to dial and nothing else: it never holds an SSH
session, and `asyncssh` stays in its adapter.

What the database is called stays what the form says — the host as the SSH
server sees it — so the connection string, a copy's judgement of "the same
server" and every sentence name the database rather than a port on loopback.
"""

import uuid
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.layout import layout
from app.adapters.options import TUNNEL_REFERENCE
from app.adapters.protocol import AdapterError, BackupAvailability
from app.core.translation import N_, say

# What the form needs to know of a field naming the connection a server is
# reached through (D282, D479): what that connection must carry — a TCP port,
# or a Unix socket on its machine (D405) — and, for a port, which fields of the
# same form hold the host and the port it leads to.
TUNNEL_SHAPE = "x-ui-tunnel"


def tunnel_shape(carries: str, host: str | None = None, port: str | None = None) -> dict[str, Any]:
    shape: dict[str, Any] = {"carries": carries}
    if host is not None:
        shape["host"] = host
    if port is not None:
        shape["port"] = port
    return {TUNNEL_SHAPE: shape}


def ssh_tunnel_field() -> Any:
    """The one declaration every source with an address shares.

    Text rather than `UUID | None`: an empty choice is what a form sends for
    "directly", the way an unpinned server key is empty (D145). Its name stays
    `ssh_tunnel` in stored options; what a person reads is "Reach through"
    (D479), as a Kubernetes cluster carries one too (D474).
    """
    return Field(
        default="",
        pattern=r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})?$",
        title=N_("Reach through"),
        description=N_(
            "Directly, or through one of your connections that carries others: an SSH server or a Kubernetes cluster"
        ),
        json_schema_extra={
            **layout(purpose=TUNNEL_REFERENCE),
            **tunnel_shape("port", host="host", port="port"),
        },
    )


class TunnelTarget(BaseModel):
    """Somewhere a connection that carries others can lead (D479): the host a
    form fills in, how a person recognises it, and the ports it serves."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=300)
    ports: list[int] = Field(default_factory=list, max_length=50)


@runtime_checkable
class ListsTunnelTargets(Protocol):
    """A source that can say where it leads, so a form offers a choice
    rather than a host to type in a shape of its own."""

    async def tunnel_targets(self) -> list[TunnelTarget]: ...


def tunnel_of(value: str) -> uuid.UUID | None:
    """The SSH connection a stored value names, or None for directly."""
    return uuid.UUID(value) if value else None


@runtime_checkable
class TunnelAccess(Protocol):
    """The SSH connections of the person who owns a database's connection.

    Raises `AdapterError`: `locked` when the SSH key waits for its passphrase
    (D147), `config` when the connection is gone, switched off or not the
    owner's, and the SSH connection's own failures as they are.
    """

    async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
        """A local address that reaches `host:port` from the SSH server."""
        ...

    async def socket_endpoint(self, connection_id: uuid.UUID, path: str) -> tuple[str, int]:
        """A local address that reaches a Unix socket on the SSH server (D405)."""
        ...


@runtime_checkable
class ForwardsPorts(Protocol):
    """A source that can carry connections to an address it reaches."""

    async def forward(self, host: str, port: int) -> tuple[str, int]: ...


@runtime_checkable
class ForwardsSockets(Protocol):
    """A source that can carry connections to a Unix socket on its server (D405)."""

    async def forward_socket(self, path: str) -> tuple[str, int]: ...


async def reach(
    tunnels: TunnelAccess | None, tunnel: str, host: str, port: int
) -> tuple[str, int]:
    """Where a driver dials: the address itself, or the tunnel's end of it.

    Asked before every connection a driver makes, so a locked key or a closed
    SSH connection is said there rather than as a database that hung up.
    """
    connection_id = tunnel_of(tunnel)
    if connection_id is None:
        return host, port
    if tunnels is None:
        raise AdapterError(
            "config", say("This connection goes through an SSH tunnel, and none is at hand")
        )
    return await tunnels.endpoint(connection_id, host, port)


def backup_through(tunnel: str) -> BackupAvailability | None:
    """The refusal of a backup that would have to go through a tunnel.

    The dump runs in a container of its own, which cannot reach a port on this
    process's loopback.
    """
    if tunnel_of(tunnel) is None:
        return None
    return BackupAvailability(
        available=False, reason=say("A backup does not go through an SSH tunnel yet")
    )
