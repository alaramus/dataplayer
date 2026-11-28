"""The Cluster section: Overview, Nodes, Top (D475), Events and API resources (D465).

Read like tables (D55). Pods are counted by phase from lists of their
metadata alone, the namespaces by one item and `remainingItemCount`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kubernetes.catalog import CLUSTER
from app.adapters.kubernetes.discovery import Discovery
from app.adapters.kubernetes.metrics import read_top
from app.adapters.kubernetes.session import (
    METADATA,
    Forbidden,
    KubernetesSession,
    segment,
)
from app.adapters.kubernetes.tables import (
    EVENT_COLUMNS,
    MOST,
    PAGE,
    Row,
    page,
    read_events,
    text_of,
)
from app.adapters.listed import listed_column
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.report_rows import page as report_page
from app.adapters.words import worded_titles
from app.core.translation import N_, say

SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")
_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))
PHASES = ("Running", "Pending", "Succeeded", "Failed", "Unknown")

NODE_COLUMNS = [
    listed_column("Name", "string"),
    listed_column("Status", "string"),
    listed_column("Roles", "string", nullable=True),
    listed_column("Version", "string", nullable=True),
    listed_column("Internal IP", "string", nullable=True),
    listed_column("OS image", "string", nullable=True),
    listed_column("Kernel", "string", nullable=True),
    listed_column("Container runtime", "string", nullable=True),
    listed_column("CPU", "string", nullable=True),
    listed_column("Memory", "string", nullable=True),
    listed_column("Allocatable CPU", "string", nullable=True),
    listed_column("Allocatable memory", "string", nullable=True),
    listed_column("Taints", "string", nullable=True),
    listed_column("Created", "datetime", nullable=True),
]
RESOURCE_COLUMNS = [
    listed_column("Resource", "string"),
    listed_column("Kind", "string"),
    listed_column("Group", "string", nullable=True),
    listed_column("Version", "string"),
    listed_column("Namespaced", "boolean"),
    listed_column("Verbs", "string"),
]


@dataclass(frozen=True)
class Context:
    session: KubernetesSession
    discovery: Discovery
    # The one namespace the connection is held to, or None for every one.
    namespace: str | None


def node_status(node: dict[str, Any]) -> str:
    conditions = (node.get("status") or {}).get("conditions") or []
    ready = next((one for one in conditions if isinstance(one, dict) and one.get("type") == "Ready"), None)
    word = "Ready" if ready and ready.get("status") == "True" else "NotReady"
    if (node.get("spec") or {}).get("unschedulable"):
        word += ",SchedulingDisabled"
    return word


def node_roles(node: dict[str, Any]) -> str | None:
    labels = (node.get("metadata") or {}).get("labels") or {}
    roles = sorted(
        key.removeprefix("node-role.kubernetes.io/")
        for key in labels
        if key.startswith("node-role.kubernetes.io/")
    )
    return ",".join(roles) or None


def node_row(node: dict[str, Any]) -> Row:
    metadata = node.get("metadata") or {}
    status = node.get("status") or {}
    info = status.get("nodeInfo") or {}
    internal = next(
        (
            one.get("address")
            for one in status.get("addresses") or []
            if isinstance(one, dict) and one.get("type") == "InternalIP"
        ),
        None,
    )
    taints = [
        f"{one.get('key')}{'=' + one['value'] if one.get('value') else ''}:{one.get('effect')}"
        for one in (node.get("spec") or {}).get("taints") or []
        if isinstance(one, dict)
    ]
    capacity = status.get("capacity") or {}
    allocatable = status.get("allocatable") or {}
    return [
        str(metadata.get("name") or ""),
        node_status(node),
        node_roles(node),
        text_of(info.get("kubeletVersion")),
        text_of(internal),
        text_of(info.get("osImage")),
        text_of(info.get("kernelVersion")),
        text_of(info.get("containerRuntimeVersion")),
        text_of(capacity.get("cpu")),
        text_of(capacity.get("memory")),
        text_of(allocatable.get("cpu")),
        text_of(allocatable.get("memory")),
        ", ".join(taints) or None,
        text_of(metadata.get("creationTimestamp")),
    ]


async def _total(session: KubernetesSession, path: str) -> int | None:
    """How many a list holds, from one item and `remainingItemCount`."""
    try:
        answer = await session.get(path, {"limit": 1})
    except AdapterError:
        return None
    if not isinstance(answer, dict):
        return None
    remaining = (answer.get("metadata") or {}).get("remainingItemCount")
    return len(answer.get("items") or []) + (int(remaining) if isinstance(remaining, int) else 0)


async def _counted(session: KubernetesSession, path: str, field_selector: str) -> int | None:
    """How many match a field selector, counted from metadata-only pages.

    The server leaves `remainingItemCount` out when a selector is given
    (checked, 1.33), so the matches are read, as metadata only, to `MOST`.
    """
    count = 0
    token = ""
    try:
        while True:
            params: dict[str, str | int] = {"limit": PAGE, "fieldSelector": field_selector}
            if token:
                params["continue"] = token
            answer = await session.get(path, params, accept=METADATA)
            if not isinstance(answer, dict):
                return None
            count += len(answer.get("items") or [])
            token = str((answer.get("metadata") or {}).get("continue") or "")
            if not token or count >= MOST:
                return count
    except AdapterError:
        return None


async def identity(session: KubernetesSession) -> str | None:
    """Who the cluster takes this connection for (`SelfSubjectReview`, GA in 1.28)."""
    for version in ("v1", "v1beta1"):
        try:
            answer = await session.request(
                "POST",
                f"/apis/authentication.k8s.io/{version}/selfsubjectreviews",
                body={"apiVersion": f"authentication.k8s.io/{version}", "kind": "SelfSubjectReview"},
                expected=(200, 201),
            )
        except AdapterError:
            continue
        info = ((answer.json() or {}).get("status") or {}).get("userInfo") or {}
        name = info.get("username")
        return str(name) if name else None
    return None


async def overview_rows(context: Context) -> list[tuple[str, str]]:
    session = context.session
    await session.client()
    pods_path = (
        "/api/v1/pods" if context.namespace is None else f"/api/v1/namespaces/{segment(context.namespace)}/pods"
    )
    nodes_task = session.get("/api/v1/nodes", asked=Forbidden("list", "nodes"))
    counts = [_counted(session, pods_path, f"status.phase={phase}") for phase in PHASES]
    results = await asyncio.gather(
        nodes_task, _total(session, "/api/v1/namespaces"), identity(session), *counts,
        return_exceptions=True,
    )
    nodes, namespaces, who, *phases = results
    rows: list[tuple[str, str]] = [("Version", session.git_version)]
    endpoint = session.endpoint()
    rows.append(("Server", endpoint.server))
    if endpoint.context:
        rows.append(("Context", endpoint.context))
    rows.append(("Identity", who if isinstance(who, str) else "—"))
    if isinstance(nodes, dict):
        items = [one for one in nodes.get("items") or [] if isinstance(one, dict)]
        ready = sum(1 for one in items if node_status(one).startswith("Ready"))
        rows.append(("Nodes ready", f"{ready} / {len(items)}"))
        platforms = sorted(
            {
                f"{(one.get('status') or {}).get('nodeInfo', {}).get('operatingSystem', '')}/"
                f"{(one.get('status') or {}).get('nodeInfo', {}).get('architecture', '')}"
                for one in items
            }
        )
        rows.append(("Platforms", ", ".join(platforms) or "—"))
    else:
        rows.append(("Nodes ready", "—"))
    rows.append(("Namespaces", str(namespaces) if isinstance(namespaces, int) else "—"))
    for phase, counted in zip(PHASES, phases, strict=True):
        rows.append((f"Pods {phase}", str(counted) if isinstance(counted, int) else "—"))
    return rows


async def _overview(context: Context, request: FetchRequest) -> FetchResult:
    return report_page(
        request,
        await overview_rows(context),
        name_column=say(SETTING_COLUMN),
        value_column=say(VALUE_COLUMN),
        read_only_reason=say('"{title}" is a report and holds no rows of its own', title=say("Overview")),
        refresh_seconds=30,
        page_commands=["download", "share"],
    )


async def _nodes(context: Context, request: FetchRequest) -> FetchResult:
    answer = await context.session.get("/api/v1/nodes", asked=Forbidden("list", "nodes"))
    items = (answer.get("items") if isinstance(answer, dict) else None) or []
    rows = [node_row(one) for one in items if isinstance(one, dict)]
    return page(request, NODE_COLUMNS, rows, refresh_seconds=30)


async def _top(context: Context, request: FetchRequest) -> FetchResult:
    return await read_top(context.session, context.namespace, request)


async def _events(context: Context, request: FetchRequest) -> FetchResult:
    rows = await read_events(context.session, context.namespace)
    return page(request, EVENT_COLUMNS, rows, refresh_seconds=10)


async def _resources(context: Context, request: FetchRequest) -> FetchResult:
    rows: list[Row] = [
        [
            one.resource,
            one.kind,
            one.group or None,
            one.version,
            "true" if one.namespaced else "false",
            ", ".join(sorted(one.verbs)),
        ]
        for one in await context.discovery.resources()
    ]
    return page(request, RESOURCE_COLUMNS, rows)


@dataclass(frozen=True)
class ClusterReport:
    key: str
    title: str
    description: str
    read: Callable[[Context, FetchRequest], Awaitable[FetchResult]]

    @property
    def node_id(self) -> str:
        return f"{CLUSTER}/{self.key}"


REPORTS: tuple[ClusterReport, ...] = (
    ClusterReport(
        "overview",
        N_("Overview"),
        N_("Version, nodes ready, namespaces, pods by phase, and who you are to it"),
        _overview,
    ),
    ClusterReport(
        "nodes",
        N_("Nodes"),
        N_("Each machine's status, roles, versions, capacity and taints"),
        _nodes,
    ),
    ClusterReport(
        "top",
        N_("Top"),
        N_("CPU and memory of each node and pod now, busiest first, from metrics.k8s.io"),
        _top,
    ),
    ClusterReport(
        "events",
        N_("Events"),
        N_("What the cluster recorded lately, newest first"),
        _events,
    ),
    ClusterReport(
        "api-resources",
        N_("API resources"),
        N_("Every kind the cluster serves, its group, version and verbs"),
        _resources,
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def report_for(node_id: str | None) -> ClusterReport | None:
    return _BY_ID.get(node_id or "")


def report_node(report: ClusterReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=worded_titles([_TABLE]),
    )


async def read_report(context: Context, request: FetchRequest) -> FetchResult:
    report = report_for(request.node_id)
    if report is None:
        raise NodeNotFound(request.node_id)
    return await report.read(context, request)
