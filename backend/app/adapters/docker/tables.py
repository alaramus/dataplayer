"""The daemon's lists and a node's views as rows (D407, D408).

Lists are read whole and narrowed here (D2d). A container's logs are the one
view read from the end: newest first, as deep as `LOG_DEPTH` lines, a line cut
at `LINE_BYTES`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.adapters.docker.catalog import (
    Named,
    image_title,
    project_of,
    tags_of,
)
from app.adapters.docker.inventory import (
    Listed,
    cut_notice,
    instant,
    labels_of,
    moment,
    name_of,
    network_kind,
    ports_of,
    read_containers,
    read_images,
    read_networks,
    read_volumes,
    state_of,
    users_of_image,
    users_of_network,
    users_of_volume,
)
from app.adapters.docker.session import DockerSession, segment
from app.adapters.docker_api.frames import Stream, frames
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, PageCommand
from app.adapters.listed import column, listed_column, listed_page
from app.adapters.protocol import NodeNotFound
from app.core.translation import say

type Row = list[str | None]

# How far back the logs reach, and how long a line may be.
LOG_DEPTH = 10_000
LINE_BYTES = 16 * 1024

_PAGE: list[PageCommand] = ["download", "chart", "share"]

CONTAINER_COLUMNS = [
    listed_column("name", "string"),
    listed_column("state", "string"),
    listed_column("status", "string"),
    listed_column("image", "string"),
    listed_column("project", "string", nullable=True),
    listed_column("service", "string", nullable=True),
    listed_column("ports", "string", nullable=True),
    listed_column("created", "datetime"),
    listed_column("id", "string"),
]
IMAGE_COLUMNS = [
    listed_column("tags", "string"),
    listed_column("id", "string"),
    listed_column("size_bytes", "number"),
    listed_column("created", "datetime", nullable=True),
    listed_column("containers", "number"),
]
VOLUME_COLUMNS = [
    listed_column("name", "string"),
    listed_column("driver", "string"),
    listed_column("mountpoint", "string", nullable=True),
    listed_column("created", "datetime", nullable=True),
    listed_column("labels", "string", nullable=True),
    listed_column("containers", "string", nullable=True),
]
NETWORK_COLUMNS = [
    listed_column("name", "string"),
    listed_column("kind", "string"),
    listed_column("driver", "string"),
    listed_column("scope", "string", nullable=True),
    listed_column("internal", "boolean"),
    listed_column("containers", "number"),
    listed_column("id", "string"),
]
USER_COLUMNS = [
    listed_column("name", "string"),
    listed_column("state", "string"),
    listed_column("image", "string"),
    listed_column("id", "string"),
]
HISTORY_COLUMNS = [
    column("created", "datetime"),
    column("instruction", "string"),
    column("size_bytes", "number"),
    column("comment", "string", nullable=True),
]
LOG_COLUMNS = [
    column("time", "datetime"),
    column("stream", "string"),
    column("text", "string"),
]


def _boolean(value: Any) -> str:
    return "true" if value else "false"


def container_row(container: dict[str, Any]) -> Row:
    labels = labels_of(container)
    ports = ports_of(container)
    return [
        name_of(container),
        state_of(container),
        str(container.get("Status") or ""),
        str(container.get("Image") or ""),
        labels.get("com.docker.compose.project"),
        labels.get("com.docker.compose.service"),
        ", ".join(ports) if ports else None,
        moment(container.get("Created")),
        str(container.get("Id") or ""),
    ]


def image_row(image: dict[str, Any], containers: list[dict[str, Any]]) -> Row:
    image_id = str(image.get("Id") or "")
    size = image.get("Size")
    return [
        ", ".join(tags_of(image)) or image_title(image),
        image_id,
        str(size) if isinstance(size, int) and size >= 0 else None,
        moment(image.get("Created")),
        str(len(users_of_image(containers, image_id))),
    ]


def volume_row(volume: dict[str, Any], containers: list[dict[str, Any]]) -> Row:
    name = str(volume.get("Name") or "")
    labels = labels_of(volume)
    users = [name_of(one) for one in users_of_volume(containers, name)]
    return [
        name,
        str(volume.get("Driver") or ""),
        str(volume["Mountpoint"]) if volume.get("Mountpoint") else None,
        instant(volume.get("CreatedAt")),
        ", ".join(f"{key}={value}" for key, value in sorted(labels.items())) or None,
        ", ".join(sorted(users)) or None,
    ]


def network_row(network: dict[str, Any], containers: list[dict[str, Any]]) -> Row:
    return [
        str(network.get("Name") or ""),
        network_kind(network),
        str(network.get("Driver") or ""),
        str(network["Scope"]) if network.get("Scope") else None,
        _boolean(network.get("Internal")),
        str(len(users_of_network(containers, network))),
        str(network.get("Id") or ""),
    ]


def user_row(container: dict[str, Any]) -> Row:
    return [
        name_of(container),
        state_of(container),
        str(container.get("Image") or ""),
        str(container.get("Id") or ""),
    ]


def page(
    request: FetchRequest,
    columns: list[FetchColumn],
    rows: list[Row],
    *,
    notice: str | None = None,
    refresh_seconds: int | None = None,
    narrowed: bool = True,
) -> FetchResult:
    """A page of rows read whole, filtered and sorted here when `narrowed`."""
    if narrowed:
        rows = listed_page(columns, rows, request.filters, request.sort)
    end = request.offset + request.limit
    reason = notice or say("What the Docker server says is read here, not changed")
    return FetchResult(
        columns=columns,
        rows=rows[request.offset : end],
        has_more=len(rows) > end,
        update_reason=reason,
        insert_reason=reason,
        delete_reason=reason,
        record_supported=False,
        record_reason=reason,
        refresh_seconds=refresh_seconds,
        page_commands=list(_PAGE),
    )


@dataclass(frozen=True)
class Lines:
    """A container's log lines, newest first."""

    rows: list[Row]
    reached_depth: bool


def log_rows(body: bytes, *, tty: bool) -> list[Row]:
    """Time, stream and text out of a `timestamps=true` answer, oldest first."""
    chunks: list[tuple[Stream, bytes]]
    found = None if tty else frames(body)
    chunks = [("stdout", body)] if found is None else found
    rows: list[Row] = []
    for stream, chunk in chunks:
        for line in chunk.split(b"\n"):
            line = line.rstrip(b"\r")
            if not line:
                continue
            stamp, space, text = line.partition(b" ")
            moment_text = instant(stamp.decode("ascii", errors="replace")) if space else None
            if moment_text is None:
                # A continuation without a time, or a daemon that wrote none.
                text = line
            if len(text) > LINE_BYTES:
                text = text[:LINE_BYTES] + "…".encode()
            rows.append([moment_text, stream, text.decode("utf-8", errors="replace")])
    return rows


class DockerTables:
    """Rows for every level and view this source opens as a table."""

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def group(self, request: FetchRequest, named: Named) -> FetchResult:
        containers = await read_containers(self._session)
        listed: Listed
        if named.group == "containers":
            chosen = containers.items
            if named.project is not None:
                chosen = [one for one in chosen if project_of(one) == named.project]
            return page(
                request,
                CONTAINER_COLUMNS,
                [container_row(one) for one in chosen],
                notice=cut_notice(containers),
                refresh_seconds=10,
            )
        if named.group == "images":
            listed = await read_images(self._session)
            rows = [image_row(one, containers.items) for one in listed.items]
            return page(request, IMAGE_COLUMNS, rows, notice=cut_notice(listed))
        if named.group == "volumes":
            listed = await read_volumes(self._session)
            rows = [volume_row(one, containers.items) for one in listed.items]
            return page(request, VOLUME_COLUMNS, rows, notice=cut_notice(listed))
        listed = await read_networks(self._session)
        rows = [network_row(one, containers.items) for one in listed.items]
        return page(request, NETWORK_COLUMNS, rows, notice=cut_notice(listed))

    async def view(self, request: FetchRequest, named: Named) -> FetchResult:
        readers: dict[str, Callable[[FetchRequest, Named], Awaitable[FetchResult]]] = {
            "logs": self._logs,
            "processes": self._processes,
            "history": self._history,
            "containers": self._users,
        }
        assert named.view is not None
        return await readers[named.view](request, named)

    async def _inspect(self, named: Named) -> dict[str, Any]:
        node_id = f"{named.leaf}:{named.key}"
        paths = {
            "container": f"/containers/{segment(named.key)}/json",
            "image": f"/images/{segment(named.key)}/json",
            "volume": f"/volumes/{segment(named.key)}",
            "network": f"/networks/{segment(named.key)}",
        }
        assert named.leaf is not None
        _, body = await self._session.get(paths[named.leaf], node_id=node_id)
        if not isinstance(body, dict):
            raise NodeNotFound(node_id)
        return body

    async def _logs(self, request: FetchRequest, named: Named) -> FetchResult:
        if request.filters or request.sort:
            raise ValueError(say("Logs are read newest first and are not filtered here"))
        inspected = await self._inspect(named)
        tty = bool((inspected.get("Config") or {}).get("Tty"))
        depth = min(request.offset + request.limit, LOG_DEPTH)
        _, body = await self._session.raw(
            f"/containers/{segment(named.key)}/logs",
            {
                "stdout": "true",
                "stderr": "true",
                "timestamps": "true",
                "tail": str(depth),
            },
            node_id=f"container:{named.key}",
        )
        rows = list(reversed(log_rows(body, tty=tty)))
        reached = request.offset + request.limit > LOG_DEPTH
        result = page(
            request,
            LOG_COLUMNS,
            rows,
            narrowed=False,
            notice=say("Only the last {count} lines are read", count=LOG_DEPTH)
            if reached
            else None,
            refresh_seconds=5,
        )
        # The daemon was asked for exactly this many; fewer means the start.
        result.has_more = len(rows) >= depth and depth < LOG_DEPTH
        return result

    async def _processes(self, request: FetchRequest, named: Named) -> FetchResult:
        status, body = await self._session.get(
            f"/containers/{segment(named.key)}/top",
            node_id=f"container:{named.key}",
            expected=(200, 409),
        )
        if status == 409 or not isinstance(body, dict):
            # The daemon's 409 here is "is not running".
            return page(
                request,
                [listed_column("process", "string")],
                [],
                notice=say("The container is not running, so nothing runs in it"),
            )
        titles = [str(title) for title in body.get("Titles") or []]
        columns = [listed_column(title, "string") for title in titles]
        rows: list[Row] = [
            [str(cell) for cell in process[: len(titles)]]
            for process in body.get("Processes") or []
            if isinstance(process, list)
        ]
        return page(request, columns, rows, refresh_seconds=5)

    async def _history(self, request: FetchRequest, named: Named) -> FetchResult:
        if request.filters or request.sort:
            raise ValueError(say("An image's layers are shown in their own order"))
        _, body = await self._session.get(
            f"/images/{segment(named.key)}/history", node_id=f"image:{named.key}"
        )
        rows: list[Row] = []
        for layer in body or []:
            if not isinstance(layer, dict):
                continue
            size = layer.get("Size")
            rows.append(
                [
                    moment(layer.get("Created")),
                    str(layer.get("CreatedBy") or ""),
                    str(size) if isinstance(size, int) else None,
                    str(layer["Comment"]) if layer.get("Comment") else None,
                ]
            )
        return page(request, HISTORY_COLUMNS, rows, narrowed=False)

    async def _users(self, request: FetchRequest, named: Named) -> FetchResult:
        inspected = await self._inspect(named)
        containers = (await read_containers(self._session)).items
        if named.leaf == "volume":
            users = users_of_volume(containers, named.key)
        else:
            users = users_of_network(containers, inspected)
        return page(request, USER_COLUMNS, [user_row(one) for one in users])
