"""Draining a node, which takes minutes, as an owned job (D471, D123).

Cordon, then evict each pod but a DaemonSet's and a mirror pod through the
`eviction` subresource, one pod a unit. A disruption budget answers 429; the
unit waits and asks again until the form's timeout. A pod with `emptyDir`
loses that data, so the form must say so before the job will take it, as
`kubectl drain --delete-emptydir-data` must be told.
"""

import asyncio
import hashlib
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.adapters.actions import Action, ActionPreview, ActionRefused, ActsOn
from app.adapters.catalog import NodeKind
from app.adapters.kubernetes.actions import MERGE, Kube, Target, patch, read, target_of
from app.adapters.kubernetes.reviews import Asked
from app.adapters.kubernetes.session import Forbidden, segment
from app.adapters.layout import layout
from app.adapters.operations import (
    MAX_OPERATION_TARGETS,
    ObservedState,
    OperationPlan,
    OperationTarget,
    UnitOutcome,
)
from app.adapters.protocol import NodeNotFound
from app.core.access import Access
from app.core.translation import N_, say

# How long a unit asks again while a disruption budget says no.
RETRY_SECONDS = 5.0
MIRROR = "kubernetes.io/config.mirror"


class DrainParams(BaseModel):
    timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        title=N_("Seconds to wait for each pod"),
        description=N_("How long a pod's disruption budget may hold it before the job gives up on it"),
        json_schema_extra=layout(),
    )
    local_data: bool = Field(
        default=False,
        title=N_("Evict pods with emptyDir volumes; that data is lost"),
    )


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def _pods_on(answer: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The pods to evict, and the ones left as kubectl drain leaves them."""
    evicted: list[dict[str, Any]] = []
    left: list[str] = []
    for pod in (answer.get("items") if isinstance(answer, dict) else None) or []:
        metadata = pod.get("metadata") or {}
        shown = f"{metadata.get('namespace')}/{metadata.get('name')}"
        owners = metadata.get("ownerReferences") or []
        if MIRROR in (metadata.get("annotations") or {}):
            left.append(say("{pod} is a static pod and stays", pod=shown))
        elif any(owner.get("kind") == "DaemonSet" for owner in owners if isinstance(owner, dict)):
            left.append(say("{pod} belongs to a DaemonSet and stays", pod=shown))
        elif (pod.get("status") or {}).get("phase") in ("Succeeded", "Failed"):
            continue
        else:
            evicted.append(pod)
    return evicted, left


def _local_data(pod: dict[str, Any]) -> bool:
    return any("emptyDir" in volume for volume in (pod.get("spec") or {}).get("volumes") or [])


def _shown(pod: dict[str, Any]) -> str:
    metadata = pod.get("metadata") or {}
    return f"{metadata.get('namespace')}/{metadata.get('name')}"


class Drain(Action[DrainParams]):
    name: ClassVar[str] = "kubernetes_drain"
    title: ClassVar[str] = N_("Drain")
    icon: ClassVar[str | None] = "move_down"
    in_view: ClassVar[bool] = True
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"k8s_object"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "Its pods are evicted and started elsewhere, if there is anywhere else. Drain it?"
    )
    params_model = DrainParams
    keys: ClassVar[frozenset[str]] = frozenset({"/nodes"})

    def __init__(self, kube: Kube) -> None:
        self._kube = kube

    def fits(self, resource: Any) -> bool:
        return bool(resource.key in self.keys)

    def asked(self, target: Target) -> Asked:
        return self.asked_at(target.resource, target.namespace)

    def asked_at(self, resource: Any, namespace: str | None) -> Asked:
        return Asked(verb="create", group="", resource="pods", subresource="eviction")

    async def _pods(self, target: Target) -> tuple[list[dict[str, Any]], list[str]]:
        answer = await self._kube.session.get(
            "/api/v1/pods",
            {"fieldSelector": f"spec.nodeName={target.name}", "limit": MAX_OPERATION_TARGETS + 1},
            asked=Forbidden("list", "pods"),
        )
        return _pods_on(answer)

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        pods, left = await self._pods(target)
        local = [_shown(pod) for pod in pods if _local_data(pod)]
        items = [say("{pod} will be evicted", pod=_shown(pod)) for pod in pods[:50]]
        if len(pods) > 50:
            items.append(say("and {count} more", count=len(pods) - 50))
        items += left
        blocked = False
        if local and not params.local_data:
            blocked = True
            items.insert(0, say("{count} pods keep data in emptyDir; tick the box to evict them", count=len(local)))
        if len(pods) > MAX_OPERATION_TARGETS:
            blocked = True
            items.insert(0, say("More than {count} pods are on it", count=MAX_OPERATION_TARGETS))
        too_long = [_shown(pod) for pod in pods if len(str((pod.get("metadata") or {}).get("name"))) > 63]
        if too_long:
            blocked = True
            items.insert(0, say("A pod's name is too long to be one step of a job: {pod}", pod=too_long[0]))
        return ActionPreview(
            summary=say("{name} will be cordoned and {count} pods evicted, as a job", name=target.shown, count=len(pods)),
            items=items,
            blocked=blocked,
            fingerprint=_fingerprint("drain", target.name),
            runs_as_job=True,
        )

    async def plan_job(self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str) -> OperationPlan:
        params = self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        unit = _fingerprint("drain", target.name)
        if unit != reviewed_fingerprint:
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        pods, _ = await self._pods(target)
        if any(_local_data(pod) for pod in pods) and not params.local_data:
            raise ActionRefused("conflict", say("Some pods keep data in emptyDir; tick the box to evict them"))
        await patch(self._kube, target, {"spec": {"unschedulable": True}}, MERGE)
        targets = tuple(
            OperationTarget(
                schema_name=str((pod.get("metadata") or {}).get("namespace")),
                name=str((pod.get("metadata") or {}).get("name")),
            )
            for pod in pods
        )
        if not targets:
            # Nothing to evict: the node is cordoned, and that is the job.
            targets = (OperationTarget(schema_name="node", name=target.name[:63]),)
        return OperationPlan(
            summary=say("Drain {name}", name=target.name)[:300],
            unit_fingerprint=unit,
            targets=targets,
        )

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str, target: OperationTarget
    ) -> UnitOutcome:
        params = self._validated(raw)
        node = await target_of(self._kube, node_id, set(self.keys))
        if unit_fingerprint != _fingerprint("drain", node.name):
            raise ActionRefused("conflict", say("The form changed after it was reviewed"))
        if target.schema_name == "node":
            return "already"
        path = f"/api/v1/namespaces/{segment(target.schema_name)}/pods/{segment(target.name)}/eviction"
        body = {
            "apiVersion": "policy/v1",
            "kind": "Eviction",
            "metadata": {"name": target.name, "namespace": target.schema_name},
        }
        deadline = time.monotonic() + params.timeout_seconds
        while True:
            answer = await self._kube.session.request(
                "POST", path, body=body, asked=Forbidden("create", "pods/eviction"), expected=(200, 201, 404, 429)
            )
            if answer.status_code == 404:
                return "already"
            if answer.status_code != 429:
                return "completed"
            if time.monotonic() >= deadline:
                raise ActionRefused(
                    "conflict",
                    say(
                        "{pod} was held by its disruption budget for {seconds} seconds",
                        pod=f"{target.schema_name}/{target.name}",
                        seconds=params.timeout_seconds,
                    ),
                )
            await asyncio.sleep(RETRY_SECONDS)

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget]
    ) -> list[ObservedState]:
        del raw
        node = await target_of(self._kube, node_id, set(self.keys))
        states: list[ObservedState] = []
        for one in targets:
            if one.schema_name == "node":
                body = await read(self._kube, node)
                cordoned = bool((body.get("spec") or {}).get("unschedulable"))
                states.append("as_requested" if cordoned else "unchanged")
                continue
            # An evicted pod is gone; its controller makes one under a new name.
            try:
                await self._kube.session.request(
                    "GET", f"/api/v1/namespaces/{segment(one.schema_name)}/pods/{segment(one.name)}", node_id="pod"
                )
            except NodeNotFound:
                states.append("as_requested")
                continue
            states.append("unchanged")
        return states
