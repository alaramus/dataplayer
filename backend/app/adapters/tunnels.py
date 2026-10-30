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

from pydantic import Field

from app.adapters.layout import layout
from app.adapters.options import TUNNEL_REFERENCE
from app.adapters.protocol import AdapterError, BackupAvailability
from app.core.translation import N_, say


def ssh_tunnel_field() -> Any:
    """The one declaration every source with an address shares.

    Text rather than `UUID | None`: an empty choice is what a form sends for
    "directly", the way an unpinned server key is empty (D145).
    """
    return Field(
        default="",
        pattern=r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})?$",
        title=N_("SSH tunnel"),
        description=N_(
            "Reach the server through one of your SSH connections; the host is then as that server sees it"
        ),
        json_schema_extra=layout(purpose=TUNNEL_REFERENCE),
    )


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


@runtime_checkable
class ForwardsPorts(Protocol):
    """A source that can carry connections to an address it reaches."""

    async def forward(self, host: str, port: int) -> tuple[str, int]: ...


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
