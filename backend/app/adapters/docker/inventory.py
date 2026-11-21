"""What a daemon holds, read whole and bounded, and the facts it leaves out (D407).

The API pages nothing, so a list is read at once and at most `CEILING` of a
kind are kept. The counts the daemon's lists leave empty — which containers
use an image, mount a volume or sit on a network — are counted here from the
containers, which are always read with them.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.adapters.catalog import ContainerState, NetworkKind
from app.adapters.docker.session import DockerSession
from app.core.translation import say

CEILING = 10_000

COMPOSE_PROJECT = "com.docker.compose.project"
COMPOSE_SERVICE = "com.docker.compose.service"
COMPOSE_NETWORK = "com.docker.compose.network"
BUILT_IN_NETWORKS = frozenset({"bridge", "host", "none"})

_EXIT = re.compile(r"^Exited \((-?\d+)\)")


def moment(seconds: Any) -> str | None:
    """A Unix time as the grid's moment."""
    if not isinstance(seconds, int | float) or isinstance(seconds, bool) or seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat().replace("+00:00", "Z")


def instant(text: Any) -> str | None:
    """An RFC 3339 time from the daemon, as the grid's moment; the zero time is none."""
    if not isinstance(text, str) or not text or text.startswith("0001-01-01"):
        return None
    try:
        # Nanoseconds are read to microseconds.
        at = datetime.fromisoformat(text)
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def datetime_of(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text.replace("Z", "+00:00"))


def name_of(container: dict[str, Any]) -> str:
    """A container's name without the slash the daemon writes before it."""
    names = container.get("Names") or []
    if names:
        return str(names[0]).lstrip("/")
    return str(container.get("Id", ""))[:12]


def labels_of(item: dict[str, Any]) -> dict[str, str]:
    labels = item.get("Labels")
    return {str(k): str(v) for k, v in labels.items()} if isinstance(labels, dict) else {}


def state_of(container: dict[str, Any]) -> ContainerState:
    """One word from the state, the status and the health check (D407)."""
    state = str(container.get("State") or "")
    status = str(container.get("Status") or "")
    health = container.get("Health")
    health_status = health.get("Status") if isinstance(health, dict) else None
    if state == "running":
        # The list carries health only in newer APIs; the status says it in all.
        if health_status == "healthy" or "(healthy)" in status:
            return "healthy"
        if health_status == "unhealthy" or "(unhealthy)" in status:
            return "unhealthy"
        if health_status == "starting" or "(health: starting)" in status:
            return "starting"
        return "running"
    if state == "exited":
        exit_code = _EXIT.match(status)
        return "stopped" if exit_code is None or exit_code.group(1) == "0" else "failed"
    if state in {"paused", "restarting", "created", "removing", "dead"}:
        return state  # type: ignore[return-value] # narrowed by the set above
    return "unknown"


def ports_of(container: dict[str, Any]) -> list[str]:
    """Published ports, `host:container/protocol`, each once whatever the family."""
    found: list[str] = []
    for port in container.get("Ports") or []:
        if not isinstance(port, dict) or not port.get("PublicPort"):
            continue
        text = f"{port['PublicPort']}:{port.get('PrivatePort')}/{port.get('Type', 'tcp')}"
        if text not in found:
            found.append(text)
    return found


def network_kind(network: dict[str, Any]) -> NetworkKind:
    if str(network.get("Name")) in BUILT_IN_NETWORKS:
        return "built_in"
    if COMPOSE_NETWORK in labels_of(network):
        return "compose"
    return "user"


@dataclass
class Listed:
    """One kind of thing, as many as were kept, and whether there were more."""

    items: list[dict[str, Any]] = field(default_factory=list)
    cut: bool = False


def _kept(items: Any) -> Listed:
    found = [item for item in items or [] if isinstance(item, dict)]
    return Listed(found[:CEILING], len(found) > CEILING)


def cut_notice(listed: Listed) -> str | None:
    if not listed.cut:
        return None
    return say("Only the first {count} are listed", count=CEILING)


async def read_containers(session: DockerSession) -> Listed:
    # Every container, running or not; never `size`, which walks every
    # container's filesystem.
    _, body = await session.get("/containers/json", {"all": "true"})
    return _kept(body)


async def read_images(session: DockerSession) -> Listed:
    _, body = await session.get("/images/json")
    return _kept(body)


async def read_volumes(session: DockerSession) -> Listed:
    _, body = await session.get("/volumes")
    return _kept(body.get("Volumes") if isinstance(body, dict) else None)


async def read_networks(session: DockerSession) -> Listed:
    _, body = await session.get("/networks")
    return _kept(body)


def users_of_image(containers: list[dict[str, Any]], image_id: str) -> list[dict[str, Any]]:
    return [one for one in containers if one.get("ImageID") == image_id]


def users_of_volume(containers: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [
        one
        for one in containers
        if any(
            isinstance(mount, dict) and mount.get("Type") == "volume" and mount.get("Name") == name
            for mount in one.get("Mounts") or []
        )
    ]


def users_of_network(
    containers: list[dict[str, Any]], network: dict[str, Any]
) -> list[dict[str, Any]]:
    """Containers on a network, by its id; the list of networks leaves them out."""
    network_id = network.get("Id")
    found = []
    for one in containers:
        attached = ((one.get("NetworkSettings") or {}).get("Networks")) or {}
        if any(
            isinstance(endpoint, dict) and endpoint.get("NetworkID") == network_id
            for endpoint in attached.values()
        ):
            found.append(one)
    return found
