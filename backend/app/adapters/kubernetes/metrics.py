"""What a cluster is measured by, from `metrics.k8s.io` (D475, on D128).

The Metrics API is served by metrics-server, not by the API server itself:
`/apis/metrics.k8s.io/v1beta1/nodes` and `…/pods`, each item a usage of CPU
and memory as quantities (`894980n`, `82m`, `600Ki`, `535Mi`). A cluster that
does not serve it — the group absent from discovery, or a 404 or 503 while
metrics-server starts (*checked*, k3s) — polls nothing and its Top report
says so.

A poll measures every node and at most `POLLED` pods, the busiest by CPU;
the rest are counted, not named, as Docker counts its containers (D415).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kubernetes.session import Forbidden, KubernetesSession, segment
from app.adapters.kubernetes.tables import Row, page
from app.adapters.listed import listed_column
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.translation import N_, say

GROUP = "/apis/metrics.k8s.io/v1beta1"
POLLED = 200
_SUFFIXES = {
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
    "E": 1e18,
    "Ki": 2.0**10,
    "Mi": 2.0**20,
    "Gi": 2.0**30,
    "Ti": 2.0**40,
    "Pi": 2.0**50,
    "Ei": 2.0**60,
}
_QUANTITY = re.compile(r"^([+-]?[0-9.]+(?:[eE][+-]?[0-9]+)?)(Ki|Mi|Gi|Ti|Pi|Ei|n|u|m|k|M|G|T|P|E)?$")


def quantity(text: Any) -> float | None:
    """A Kubernetes quantity as a number: cores for CPU, bytes for memory."""
    found = _QUANTITY.match(str(text or "").strip())
    if found is None:
        return None
    try:
        number = float(found[1])
    except ValueError:
        return None
    return number * _SUFFIXES[found[2] or ""]


@dataclass(frozen=True)
class Usage:
    kind: str
    namespace: str | None
    name: str
    # Cores and bytes.
    cpu: float
    memory: float
    # Of what the node offers its pods; None for a pod.
    cpu_share: float | None = None
    memory_share: float | None = None

    @property
    def label(self) -> str:
        return self.name if self.namespace is None else f"{self.namespace}/{self.name}"


@dataclass(frozen=True)
class Measured:
    nodes: list[Usage]
    # Every pod measured, busiest first; nothing is cut here.
    pods: list[Usage]


class NotServed(Exception):
    """The cluster serves no Metrics API now."""


def _usage_of(item: dict[str, Any], containers: bool) -> tuple[float, float]:
    if containers:
        parts = [one.get("usage") or {} for one in item.get("containers") or [] if isinstance(one, dict)]
    else:
        parts = [item.get("usage") or {}]
    cpu = sum(quantity(part.get("cpu")) or 0.0 for part in parts)
    memory = sum(quantity(part.get("memory")) or 0.0 for part in parts)
    return cpu, memory


def usages(
    node_metrics: Iterable[dict[str, Any]],
    pod_metrics: Iterable[dict[str, Any]],
    nodes: Iterable[dict[str, Any]],
) -> Measured:
    """Nodes by name with their share of what they offer, pods busiest first."""
    offered: dict[str, tuple[float | None, float | None]] = {}
    for node in nodes:
        allocatable = (node.get("status") or {}).get("allocatable") or {}
        offered[str((node.get("metadata") or {}).get("name") or "")] = (
            quantity(allocatable.get("cpu")),
            quantity(allocatable.get("memory")),
        )
    measured_nodes: list[Usage] = []
    for item in node_metrics:
        name = str((item.get("metadata") or {}).get("name") or "")
        cpu, memory = _usage_of(item, containers=False)
        cpu_offered, memory_offered = offered.get(name, (None, None))
        measured_nodes.append(
            Usage(
                "Node",
                None,
                name,
                cpu,
                memory,
                cpu / cpu_offered * 100.0 if cpu_offered else None,
                memory / memory_offered * 100.0 if memory_offered else None,
            )
        )
    measured_pods: list[Usage] = []
    for item in pod_metrics:
        metadata = item.get("metadata") or {}
        cpu, memory = _usage_of(item, containers=True)
        measured_pods.append(
            Usage("Pod", str(metadata.get("namespace") or ""), str(metadata.get("name") or ""), cpu, memory)
        )
    measured_nodes.sort(key=lambda one: one.name)
    measured_pods.sort(key=lambda one: (-one.cpu, -one.memory, one.label))
    return Measured(measured_nodes, measured_pods)


async def measured(session: KubernetesSession, namespace: str | None) -> Measured:
    """What metrics-server says now; NotServed when nothing serves it."""
    pods_path = f"{GROUP}/pods" if namespace is None else f"{GROUP}/namespaces/{segment(namespace)}/pods"
    try:
        node_metrics = (
            await session.get(f"{GROUP}/nodes", asked=Forbidden("list", "nodes.metrics.k8s.io"))
            if namespace is None
            else {"items": []}
        )
        pod_metrics = await session.get(pods_path, asked=Forbidden("list", "pods.metrics.k8s.io"))
    except NodeNotFound:
        raise NotServed from None
    except AdapterError as failure:
        # A 404 is "no such thing" and a 503 a metrics-server still starting:
        # either way there is nothing to read; a refusal is said as one.
        if failure.error_kind == "auth":
            raise
        raise NotServed from None
    nodes: list[dict[str, Any]] = []
    if namespace is None:
        try:
            listed = await session.get("/api/v1/nodes", asked=Forbidden("list", "nodes"))
            nodes = [one for one in (listed.get("items") or []) if isinstance(one, dict)]
        except AdapterError:
            nodes = []
    return usages(
        [one for one in (node_metrics.get("items") or []) if isinstance(one, dict)],
        [one for one in (pod_metrics.get("items") or []) if isinstance(one, dict)],
        nodes,
    )


def samples_of(found: Measured) -> list[MetricSample]:
    samples: list[MetricSample] = []
    for node in found.nodes:
        samples.append(MetricSample("node", "cpu", node.cpu * 100.0, label=node.label, unit="%"))
        samples.append(MetricSample("node", "memory", node.memory, label=node.label, unit="B"))
        if node.cpu_share is not None:
            samples.append(MetricSample("node", "cpu_allocatable", node.cpu_share, label=node.label, unit="%"))
        if node.memory_share is not None:
            samples.append(MetricSample("node", "memory_allocatable", node.memory_share, label=node.label, unit="%"))
    for pod in found.pods[:POLLED]:
        samples.append(MetricSample("pod", "cpu", pod.cpu * 100.0, label=pod.label, unit="%"))
        samples.append(MetricSample("pod", "memory", pod.memory, label=pod.label, unit="B"))
    samples.append(MetricSample("cluster", "pods_measured", float(min(len(found.pods), POLLED))))
    samples.append(MetricSample("cluster", "pods_skipped", float(max(len(found.pods) - POLLED, 0))))
    return samples


async def samples(session: KubernetesSession, namespace: str | None) -> list[MetricSample]:
    try:
        return samples_of(await measured(session, namespace))
    except NotServed:
        return []


TOP_COLUMNS = [
    listed_column("Kind", "string"),
    listed_column("Namespace", "string", nullable=True),
    listed_column("Name", "string"),
    listed_column("CPU, millicores", "number"),
    listed_column("Memory, MiB", "number"),
    listed_column("CPU, % of allocatable", "number", nullable=True),
    listed_column("Memory, % of allocatable", "number", nullable=True),
]


def _number(value: float | None, digits: int) -> str | None:
    return None if value is None else f"{value:.{digits}f}"


def top_rows(found: Measured) -> list[Row]:
    """Nodes, then pods busiest first, as `kubectl top` says them."""
    return [
        [
            one.kind,
            one.namespace,
            one.name,
            _number(one.cpu * 1000.0, 0),
            _number(one.memory / 2.0**20, 1),
            _number(one.cpu_share, 1),
            _number(one.memory_share, 1),
        ]
        for one in [*found.nodes, *found.pods]
    ]


async def read_top(session: KubernetesSession, namespace: str | None, request: FetchRequest) -> FetchResult:
    try:
        found = await measured(session, namespace)
    except NotServed:
        return page(
            request,
            TOP_COLUMNS,
            [],
            notice=say("The cluster serves no metrics.k8s.io; metrics-server is not running or still starting"),
        )
    return page(request, TOP_COLUMNS, top_rows(found), refresh_seconds=30)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="kubernetes-cluster",
        name=N_("Kubernetes nodes and pods"),
        description=N_(
            "CPU and memory of each node and of the two hundred busiest pods, from metrics.k8s.io, "
            "and how many pods were left unmeasured."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("CPU by node"), (0, 0, 6, 5), "node", ("cpu",)),
            MetricRecipe("timeseries", N_("Memory by node"), (6, 0, 6, 5), "node", ("memory",)),
            MetricRecipe("timeseries", N_("CPU by pod"), (0, 5, 6, 5), "pod", ("cpu",)),
            MetricRecipe("timeseries", N_("Memory by pod"), (6, 5, 6, 5), "pod", ("memory",)),
            MetricRecipe("stat", N_("Pods measured"), (0, 10, 3, 4), "cluster", ("pods_measured",)),
            MetricRecipe("stat", N_("Pods not measured"), (3, 10, 3, 4), "cluster", ("pods_skipped",)),
        ),
    ),
)
