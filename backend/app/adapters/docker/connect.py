"""A container as a connection of its own type, as a form to finish (D417).

The types declare the images their servers run as (`ContainerImage`), so this
module keeps no list of them. The draft goes through the Docker source's own
SSH connection (D282): the published port at `127.0.0.1` when the container
publishes the server's port, its address on its network otherwise, both as the
SSH server sees them.
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActsOn,
    ConnectorDraft,
)
from app.adapters.catalog import NodeKind
from app.adapters.docker.actions import NoParams
from app.adapters.docker.catalog import parse
from app.adapters.docker.session import DockerSession, segment
from app.adapters.registry import AdapterType, ContainerImage, type_for_image
from app.core.access import Access
from app.core.translation import N_, say

# A port published on every address, or on this machine's own, is reached at
# the loopback address of the SSH server.
_LOOPBACK_BINDINGS = frozenset({"", "0.0.0.0", "::", "127.0.0.1", "::1"})


def environment(inspected: dict[str, Any]) -> dict[str, str]:
    """`Config.Env` as names and values; the first of a repeated name wins, as
    nothing here can say which one the program read."""
    found: dict[str, str] = {}
    for item in (inspected.get("Config") or {}).get("Env") or []:
        name, equals, value = str(item).partition("=")
        if equals and name not in found:
            found[name] = value
    return found


def image_of(inspected: dict[str, Any]) -> str:
    return str((inspected.get("Config") or {}).get("Image") or "")


def address(inspected: dict[str, Any], port: int) -> tuple[str, int] | None:
    """Where the server is, as the daemon's machine sees it, or None."""
    wanted = f"{port}/tcp"
    settings = inspected.get("NetworkSettings") or {}
    host_config = inspected.get("HostConfig") or {}
    # The live bindings of a running container, else the ones it asked for.
    for bindings in (
        (settings.get("Ports") or {}).get(wanted),
        (host_config.get("PortBindings") or {}).get(wanted),
    ):
        for binding in bindings or []:
            if not isinstance(binding, dict):
                continue
            published = str(binding.get("HostPort") or "")
            if not published.isdigit():
                continue
            host_ip = str(binding.get("HostIp") or "")
            return ("127.0.0.1" if host_ip in _LOOPBACK_BINDINGS else host_ip), int(published)
    if host_config.get("NetworkMode") == "host":
        return "127.0.0.1", port
    for network in (settings.get("Networks") or {}).values():
        ip = network.get("IPAddress") if isinstance(network, dict) else None
        if ip:
            return str(ip), port
    return None


def declared_for(inspected: dict[str, Any]) -> tuple[AdapterType, ContainerImage] | None:
    return type_for_image(image_of(inspected))


class OpenAsConnection(Action[NoParams]):
    name: ClassVar[str] = "docker_open_as_connection"
    title: ClassVar[str] = N_("Open as connection")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"container"})
    acts_on: ClassVar[ActsOn] = "node"
    # The draft carries passwords read from the container's environment, and
    # the new connection is its creator's through their own SSH connection.
    requires: ClassVar[Access] = "own"
    params_model = NoParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def inspected(self, node_id: str | None) -> dict[str, Any]:
        named = parse(node_id or "")
        if named.leaf != "container" or named.view is not None:
            raise ActionRefused("not_applicable", say("Choose one container"))
        _, found = await self._session.get(
            f"/containers/{segment(named.key)}/json", node_id=node_id or ""
        )
        return found if isinstance(found, dict) else {}

    async def offered(self, node_id: str) -> bool:
        """Whether a type declares this container's image."""
        return declared_for(await self.inspected(node_id)) is not None

    async def prepare_connector(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ConnectorDraft:
        self._validated(raw)
        inspected = await self.inspected(node_id)
        declared = declared_for(inspected)
        if declared is None:
            raise ActionRefused(
                "not_applicable",
                say("No connection type here runs as {image}", image=image_of(inspected)),
            )
        adapter_type, image = declared
        where = address(inspected, image.port)
        if where is None:
            raise ActionRefused(
                "not_applicable",
                say("The container has no address: start it, or publish port {port}", port=image.port),
            )
        host, port = where
        name = str(inspected.get("Name") or "").lstrip("/") or adapter_type.name
        return ConnectorDraft(
            name=name[:255],
            adapter_type=adapter_type.name,
            options={
                **image.options(environment(inspected)),
                "host": host,
                "port": port,
                "ssh_tunnel": self._session.options.ssh_connection,
            },
        )
