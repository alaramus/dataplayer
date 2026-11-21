"""The daemon's System section: Engine, Disk usage and Events (D407).

Read like tables (D55). Registry mirrors and proxies are left out of Engine:
they can carry credentials in their URLs.
"""

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.docker.inventory import moment
from app.adapters.docker.session import SLOW_SECONDS, DockerSession
from app.adapters.docker.tables import Row, page
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.listed import listed_column
from app.adapters.protocol import NodeNotFound
from app.adapters.report_rows import page as report_page
from app.adapters.words import worded_titles
from app.core.translation import N_, say

SECTION_ID = "system"
REPORT_PREFIX = "system/"
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")
_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

# How many of the last hour's events are shown: a health check alone writes
# one every few seconds.
EVENTS_SHOWN = 2_000

DISK_COLUMNS = [
    listed_column("kind", "string"),
    listed_column("name", "string"),
    listed_column("size_bytes", "number", nullable=True),
    listed_column("reclaimable", "boolean"),
    listed_column("used_by", "number", nullable=True),
]
EVENT_COLUMNS = [
    listed_column("time", "datetime"),
    listed_column("type", "string"),
    listed_column("action", "string"),
    listed_column("name", "string", nullable=True),
    listed_column("id", "string"),
]


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def engine_rows(version: dict[str, Any], info: dict[str, Any]) -> list[tuple[str, str]]:
    """What the engine says about itself, without anything that names a secret.

    Named by the API's own fields, as a ZooKeeper report keeps `zk_*`: they
    are the daemon's words, not this application's.
    """
    pairs: list[tuple[str, Any]] = [
        ("Version", version.get("Version")),
        ("ApiVersion", version.get("ApiVersion")),
        ("MinAPIVersion", version.get("MinAPIVersion")),
        ("Platform", (version.get("Platform") or {}).get("Name")),
        ("OperatingSystem", info.get("OperatingSystem")),
        ("OSType", info.get("OSType")),
        ("KernelVersion", info.get("KernelVersion")),
        ("Architecture", info.get("Architecture")),
        ("Driver", info.get("Driver")),
        ("LoggingDriver", info.get("LoggingDriver")),
        ("CgroupDriver", info.get("CgroupDriver")),
        ("CgroupVersion", info.get("CgroupVersion")),
        ("Rootless", "name=rootless" in (info.get("SecurityOptions") or [])),
        ("SecurityOptions", info.get("SecurityOptions")),
        ("NCPU", info.get("NCPU")),
        ("MemTotal", info.get("MemTotal")),
        ("Containers", info.get("Containers")),
        ("ContainersRunning", info.get("ContainersRunning")),
        ("ContainersPaused", info.get("ContainersPaused")),
        ("ContainersStopped", info.get("ContainersStopped")),
        ("Images", info.get("Images")),
        ("DockerRootDir", info.get("DockerRootDir")),
        ("LiveRestoreEnabled", info.get("LiveRestoreEnabled")),
        ("DefaultRuntime", info.get("DefaultRuntime")),
        ("Swarm", (info.get("Swarm") or {}).get("LocalNodeState")),
        ("Name", info.get("Name")),
        ("SystemTime", info.get("SystemTime")),
    ]
    return [(name, _text(value)) for name, value in pairs if value is not None]


def disk_rows(df: dict[str, Any]) -> list[Row]:
    """Every image, container, volume and build cache entry with its size."""
    rows: list[Row] = []
    for image in df.get("Images") or []:
        users = image.get("Containers")
        tags = [tag for tag in image.get("RepoTags") or [] if tag != "<none>:<none>"]
        rows.append(
            [
                "image",
                ", ".join(tags) or str(image.get("Id", ""))[:19],
                _size(image.get("Size")),
                "true" if users == 0 else "false",
                str(users) if isinstance(users, int) and users >= 0 else None,
            ]
        )
    for container in df.get("Containers") or []:
        names = container.get("Names") or [""]
        rows.append(
            [
                "container",
                str(names[0]).lstrip("/"),
                _size(container.get("SizeRw")),
                "true" if container.get("State") != "running" else "false",
                None,
            ]
        )
    for volume in df.get("Volumes") or []:
        usage = volume.get("UsageData") or {}
        refs = usage.get("RefCount")
        rows.append(
            [
                "volume",
                str(volume.get("Name") or ""),
                _size(usage.get("Size")),
                "true" if refs == 0 else "false",
                str(refs) if isinstance(refs, int) and refs >= 0 else None,
            ]
        )
    for cache in df.get("BuildCache") or []:
        rows.append(
            [
                "build cache",
                str(cache.get("Description") or cache.get("ID") or ""),
                _size(cache.get("Size")),
                "false" if cache.get("InUse") else "true",
                None,
            ]
        )
    return rows


def _size(value: Any) -> str | None:
    # -1 is the daemon's "not computed".
    return str(value) if isinstance(value, int) and value >= 0 else None


def event_rows(body: bytes) -> list[Row]:
    """The JSON-lines answer to `/events`, newest first."""
    rows: list[Row] = []
    for line in body.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        actor = event.get("Actor") or {}
        attributes = actor.get("Attributes") or {}
        nanos = event.get("timeNano")
        at = (
            instant_from_nanos(nanos)
            if isinstance(nanos, int)
            else moment(event.get("time"))
        )
        rows.append(
            [
                at,
                str(event.get("Type") or ""),
                str(event.get("Action") or ""),
                str(attributes["name"]) if attributes.get("name") else None,
                str(actor.get("ID") or ""),
            ]
        )
    rows.reverse()
    return rows[:EVENTS_SHOWN]


def instant_from_nanos(nanos: int) -> str | None:
    return moment(nanos / 1_000_000_000)


async def _engine(session: DockerSession, request: FetchRequest) -> FetchResult:
    _, version = await session.get("/version")
    _, info = await session.get("/info")
    return report_page(
        request,
        engine_rows(version if isinstance(version, dict) else {}, info if isinstance(info, dict) else {}),
        name_column=say(SETTING_COLUMN),
        value_column=say(VALUE_COLUMN),
        read_only_reason=say('"{title}" is a report and holds no rows of its own', title=say("Engine")),
        refresh_seconds=30,
        page_commands=["download", "share"],
    )


async def _disk(session: DockerSession, request: FetchRequest) -> FetchResult:
    # The one slow call: the daemon sizes every volume.
    _, df = await session.get("/system/df", seconds=SLOW_SECONDS)
    return page(request, DISK_COLUMNS, disk_rows(df if isinstance(df, dict) else {}))


async def _events(session: DockerSession, request: FetchRequest) -> FetchResult:
    now = int(time.time())
    # `until` closes the stream: without it the daemon keeps it open for ever.
    _, body = await session.raw(
        "/events", {"since": str(now - 3600), "until": str(now)}
    )
    return page(request, EVENT_COLUMNS, event_rows(body), refresh_seconds=10)


@dataclass(frozen=True)
class SystemReport:
    key: str
    title: str
    description: str
    read: Callable[[DockerSession, FetchRequest], Awaitable[FetchResult]]

    @property
    def node_id(self) -> str:
        return REPORT_PREFIX + self.key


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        "engine",
        N_("Engine"),
        N_("Versions, the operating system, drivers, CPUs, memory and counts"),
        _engine,
    ),
    SystemReport(
        "disk",
        N_("Disk usage"),
        N_("What images, containers, volumes and the build cache take, and what could go"),
        _disk,
    ),
    SystemReport(
        "events",
        N_("Events"),
        N_("What happened in the last hour, newest first"),
        _events,
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(REPORT_PREFIX)


def report_for(node_id: str | None) -> SystemReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say("System"),
        description=say("What this Docker server says about itself"),
        has_children=True,
        representations=[],
    )


def report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=worded_titles([_TABLE]),
    )


async def read_report(session: DockerSession, request: FetchRequest) -> FetchResult:
    report = report_for(request.node_id)
    if report is None:
        raise NodeNotFound(request.node_id)
    return await report.read(session, request)

