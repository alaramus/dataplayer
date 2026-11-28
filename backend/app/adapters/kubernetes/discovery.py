"""The kinds a cluster serves, from its own discovery (D465).

`/api/v1` and each group of `/apis` at its preferred version; every resource
that answers `list` and `get` and is not a subresource. Custom resources are
found the same way as built-in ones. Kept per session for five minutes.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.adapters.kubernetes.session import Forbidden, KubernetesSession, segment
from app.adapters.protocol import AdapterError
from app.core.translation import N_

KEPT_SECONDS = 300.0
# A group is a DNS subdomain; a version and a resource are lowercase words.
_GROUP = re.compile(r"^([a-z0-9]([-a-z0-9]*[a-z0-9])?)(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
_WORD = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")

Section = Literal["workloads", "network", "configuration", "storage", "cluster", "other"]
SECTIONS: tuple[Section, ...] = ("workloads", "network", "configuration", "storage", "cluster", "other")
SECTION_TITLES: dict[Section, str] = {
    "workloads": N_("Workloads"),
    "network": N_("Network"),
    "configuration": N_("Configuration"),
    "storage": N_("Storage"),
    "cluster": N_("Cluster"),
    "other": N_("Other"),
}

# Where a well-known kind is shown, by `group/resource`; the rest is Other.
# Ordered within each section as a person looks for them.
_KNOWN: dict[str, Section] = {
    "/pods": "workloads",
    "apps/deployments": "workloads",
    "apps/statefulsets": "workloads",
    "apps/daemonsets": "workloads",
    "apps/replicasets": "workloads",
    "batch/jobs": "workloads",
    "batch/cronjobs": "workloads",
    "/services": "network",
    "networking.k8s.io/ingresses": "network",
    "discovery.k8s.io/endpointslices": "network",
    "networking.k8s.io/networkpolicies": "network",
    "networking.k8s.io/ingressclasses": "network",
    "/configmaps": "configuration",
    "/secrets": "configuration",
    "/serviceaccounts": "configuration",
    "rbac.authorization.k8s.io/roles": "configuration",
    "rbac.authorization.k8s.io/rolebindings": "configuration",
    "/resourcequotas": "configuration",
    "/limitranges": "configuration",
    "autoscaling/horizontalpodautoscalers": "configuration",
    "policy/poddisruptionbudgets": "configuration",
    "rbac.authorization.k8s.io/clusterroles": "configuration",
    "rbac.authorization.k8s.io/clusterrolebindings": "configuration",
    "/persistentvolumeclaims": "storage",
    "/persistentvolumes": "storage",
    "storage.k8s.io/storageclasses": "storage",
    "/nodes": "cluster",
    "/namespaces": "cluster",
    "apiextensions.k8s.io/customresourcedefinitions": "cluster",
    "scheduling.k8s.io/priorityclasses": "cluster",
}
_ORDER = {key: index for index, key in enumerate(_KNOWN)}
# Kinds the core group still serves that nobody lists any more, or that
# duplicate a newer one: `endpoints` (EndpointSlices), `events` (Cluster ›
# Events, and events.k8s.io), `componentstatuses` (deprecated since 1.19).
_HIDDEN = {"/endpoints", "/events", "/componentstatuses", "/podtemplates", "/replicationcontrollers", "events.k8s.io/events"}


@dataclass(frozen=True)
class Resource:
    group: str
    version: str
    resource: str
    kind: str
    namespaced: bool
    verbs: frozenset[str]

    @property
    def key(self) -> str:
        return f"{self.group}/{self.resource}"

    @property
    def section(self) -> Section:
        return _KNOWN.get(self.key, "other")

    @property
    def order(self) -> tuple[int, str, str]:
        return (_ORDER.get(self.key, len(_ORDER)), self.group, self.resource)

    def base(self, namespace: str | None) -> str:
        """The path of its list, in a namespace or across the cluster."""
        root = "/api/v1" if self.group == "" else f"/apis/{segment(self.group)}/{segment(self.version)}"
        if namespace and self.namespaced:
            return f"{root}/namespaces/{segment(namespace)}/{segment(self.resource)}"
        return f"{root}/{segment(self.resource)}"

    def path(self, namespace: str | None, name: str) -> str:
        return f"{self.base(namespace)}/{segment(name)}"

    def asked(self, verb: str) -> Forbidden:
        return Forbidden(verb=verb, resource=self.resource if not self.group else f"{self.resource}.{self.group}")


def resources_in(group: str, version: str, body: Any) -> list[Resource]:
    found: list[Resource] = []
    entries = body.get("resources") if isinstance(body, dict) else None
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        verbs = frozenset(str(verb) for verb in entry.get("verbs") or [])
        if "/" in name or not _WORD.match(name) or not {"list", "get"} <= verbs:
            continue
        if f"{group}/{name}" in _HIDDEN:
            continue
        found.append(
            Resource(
                group=group,
                version=version,
                resource=name,
                kind=str(entry.get("kind") or name),
                namespaced=bool(entry.get("namespaced")),
                verbs=verbs,
            )
        )
    return found


class Discovery:
    """What the cluster serves, asked again after `KEPT_SECONDS`."""

    def __init__(self, session: KubernetesSession) -> None:
        self._session = session
        self._kept: list[Resource] | None = None
        self._at = 0.0
        self._lock = asyncio.Lock()

    async def resources(self) -> list[Resource]:
        async with self._lock:
            if self._kept is None or time.monotonic() - self._at > KEPT_SECONDS:
                self._kept = await self._read()
                self._at = time.monotonic()
            return self._kept

    async def _read(self) -> list[Resource]:
        core = await self._session.get("/api/v1")
        found = resources_in("", "v1", core)
        groups = await self._session.get("/apis")
        wanted: list[tuple[str, str]] = []
        for entry in (groups.get("groups") if isinstance(groups, dict) else None) or []:
            name = str(entry.get("name") or "")
            version = str((entry.get("preferredVersion") or {}).get("version") or "")
            if _GROUP.match(name) and _WORD.match(version):
                wanted.append((name, version))

        async def one(group: str, version: str) -> list[Resource]:
            try:
                body = await self._session.get(f"/apis/{segment(group)}/{segment(version)}")
            except AdapterError:
                # An aggregated API whose server is down (metrics before its
                # pod is up answers 503) hides its kinds, not the cluster.
                return []
            return resources_in(group, version, body)

        for listed in await asyncio.gather(*(one(group, version) for group, version in wanted)):
            found.extend(listed)
        return sorted(found, key=lambda resource: resource.order)

    async def find(self, group: str, resource: str) -> Resource | None:
        for one in await self.resources():
            if one.group == group and one.resource == resource:
                return one
        return None
