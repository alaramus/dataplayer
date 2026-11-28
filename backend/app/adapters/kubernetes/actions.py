"""What a Kubernetes connection can be asked to change (D468–D470).

Every change answers what it would do first (D46), and where the cluster can
rehearse it the answer is the cluster's own dry run (`dryRun=All`), which runs
admission and changes nothing. Each action declares the verb and resource it
needs, so a menu offers only what the cluster's RBAC allows (`reviews.py`).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    FieldHints,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.kubernetes.catalog import EVERY, Named, kind_id, object_id, parse
from app.adapters.kubernetes.discovery import Discovery, Resource
from app.adapters.kubernetes.reviews import Asked, Reviews
from app.adapters.kubernetes.session import Forbidden, KubernetesSession, segment
from app.adapters.layout import layout
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access
from app.core.translation import N_, say

MAX_REPLICAS = 1000
MAX_GRACE = 3600
# What New from YAML takes at once.
MAX_DOCUMENTS = 100
MAX_YAML = 1024 * 1024
FIELD_MANAGER = "dataplayer"
SCALABLE = {"apps/deployments", "apps/statefulsets", "apps/replicasets"}
RESTARTABLE = {"apps/deployments", "apps/statefulsets", "apps/daemonsets"}
RESTARTED_AT = "kubectl.kubernetes.io/restartedAt"
MERGE = "application/merge-patch+json"
STRATEGIC = "application/strategic-merge-patch+json"
APPLY = "application/apply-patch+yaml"


@dataclass(frozen=True)
class Kube:
    """What every action reads through: one session, its discovery and reviews."""

    session: KubernetesSession
    discovery: Discovery
    reviews: Reviews


@dataclass(frozen=True)
class Target:
    named: Named
    resource: Resource

    @property
    def name(self) -> str:
        assert self.named.name is not None
        return self.named.name

    @property
    def namespace(self) -> str | None:
        return self.named.namespace

    @property
    def path(self) -> str:
        return self.resource.path(self.namespace, self.name)

    @property
    def node_id(self) -> str:
        return object_id(self.namespace, self.resource.group, self.resource.resource, self.name)

    @property
    def level_id(self) -> str:
        return kind_id(self.namespace, self.resource)

    @property
    def shown(self) -> str:
        return f"{self.resource.kind}/{self.name}"


async def target_of(kube: Kube, node_id: str | None, keys: set[str] | None = None) -> Target:
    """The object a node id names, of one of `keys` when they are given."""
    try:
        named = parse(node_id or "")
    except ValueError:
        raise ActionRefused("not_applicable", say("Choose an object of the cluster")) from None
    if named.name is None or named.view is not None or named.resource is None or named.group is None:
        raise ActionRefused("not_applicable", say("Choose an object of the cluster"))
    resource = await kube.discovery.find(named.group, named.resource)
    if resource is None or resource.namespaced != (named.top == "namespace"):
        raise NodeNotFound(node_id or "")
    if keys is not None and resource.key not in keys:
        raise ActionRefused("not_applicable", say("This does not apply to a {kind}", kind=resource.kind))
    return Target(named=named, resource=resource)


async def read(kube: Kube, target: Target) -> dict[str, Any]:
    body = await kube.session.get(target.path, asked=target.resource.asked("get"), node_id=target.node_id)
    if not isinstance(body, dict):
        raise AdapterError("unknown", say("The cluster did not answer with JSON"))
    return body


async def patch(
    kube: Kube, target: Target, body: Any, content_type: str, *, subresource: str = "", dry: bool = False
) -> None:
    await kube.session.request(
        "PATCH",
        target.path + (f"/{subresource}" if subresource else ""),
        {"dryRun": "All"} if dry else None,
        body=body,
        content_type=content_type,
        asked=target.resource.asked("patch"),
        node_id=target.node_id,
        expected=(200, 201),
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class NoParams(BaseModel):
    """The selection says everything."""


class ObjectAction[P: BaseModel](JsonAction[P]):
    """An action on one object of some kinds, asking one verb of the cluster."""

    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"k8s_object"})
    acts_on: ClassVar[ActsOn] = "node"
    in_view: ClassVar[bool] = True
    # The kinds it applies to by `group/resource`, and what it asks of RBAC.
    keys: ClassVar[frozenset[str]]
    verb: ClassVar[str] = "patch"
    subresource: ClassVar[str] = ""

    def __init__(self, kube: Kube) -> None:
        self._kube = kube

    def fits(self, resource: Resource) -> bool:
        return resource.key in self.keys

    def asked(self, target: Target) -> Asked:
        return Asked(
            verb=self.verb,
            group=target.resource.group,
            resource=target.resource.resource,
            namespace=target.namespace,
            subresource=self.subresource,
        )


# --- scale, restart, cordon, suspend (D468) -------------------------------------


class ScaleParams(BaseModel):
    replicas: int = Field(
        ge=0,
        le=MAX_REPLICAS,
        title=N_("Replicas"),
        description=N_("How many pods it should run; 0 stops them all"),
        json_schema_extra=layout(),
    )


class Scale(ObjectAction[ScaleParams]):
    name: ClassVar[str] = "kubernetes_scale"
    title: ClassVar[str] = N_("Scale")
    icon: ClassVar[str | None] = "tune"
    requires: ClassVar[Access] = "write"
    params_model = ScaleParams
    keys = frozenset(SCALABLE)
    subresource = "scale"

    async def field_hints(self, node_id: str | None) -> FieldHints:
        target = await target_of(self._kube, node_id, set(self.keys))
        body = await read(self._kube, target)
        replicas = (body.get("spec") or {}).get("replicas", 1)
        return FieldHints(values={"replicas": str(replicas)})

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        body = await read(self._kube, target)
        now = (body.get("spec") or {}).get("replicas", 1)
        await patch(self._kube, target, {"spec": {"replicas": params.replicas}}, MERGE, subresource="scale", dry=True)
        if now == params.replicas:
            return ActionPreview(
                summary=say("{name} already runs {count} replicas", name=target.shown, count=now), blocked=True
            )
        return ActionPreview(
            summary=say("{name}: {before} → {after} replicas", name=target.shown, before=now, after=params.replicas),
            items=[say("Every pod stops; it keeps its configuration")] if params.replicas == 0 else [],
        )

    async def run(self, node_id: str | None, params: ScaleParams) -> ActionResult:
        target = await target_of(self._kube, node_id, set(self.keys))
        await patch(self._kube, target, {"spec": {"replicas": params.replicas}}, MERGE, subresource="scale")
        return ActionResult(
            message=say("{name} scaled to {count} replicas", name=target.shown, count=params.replicas),
            reload_node_ids=[target.level_id],
        )


class Restart(ObjectAction[NoParams]):
    """What `kubectl rollout restart` does: a new pod template annotation."""

    name: ClassVar[str] = "kubernetes_restart"
    title: ClassVar[str] = N_("Restart")
    icon: ClassVar[str | None] = "restart_alt"
    requires: ClassVar[Access] = "write"
    params_model = NoParams
    keys = frozenset(RESTARTABLE)

    def _body(self) -> dict[str, Any]:
        return {"spec": {"template": {"metadata": {"annotations": {RESTARTED_AT: _now()}}}}}

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        await patch(self._kube, target, self._body(), STRATEGIC, dry=True)
        return ActionPreview(
            summary=say("{name} will replace its pods one by one", name=target.shown),
            items=[say("As kubectl rollout restart does: by its update strategy")],
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        target = await target_of(self._kube, node_id, set(self.keys))
        await patch(self._kube, target, self._body(), STRATEGIC)
        return ActionResult(message=say("{name} is restarting", name=target.shown), reload_node_ids=[target.level_id])


class _Toggle(ObjectAction[NoParams]):
    """A switch in the spec: a node's `unschedulable`, a CronJob's `suspend`."""

    requires: ClassVar[Access] = "write"
    params_model = NoParams
    field: ClassVar[str]
    value: ClassVar[bool]
    will: ClassVar[str]
    already: ClassVar[str]
    done: ClassVar[str]

    async def _state(self, node_id: str | None) -> tuple[Target, bool]:
        target = await target_of(self._kube, node_id, set(self.keys))
        body = await read(self._kube, target)
        return target, bool((body.get("spec") or {}).get(self.field)) == self.value

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        target, already = await self._state(node_id)
        if already:
            return ActionPreview(summary=say(self.already, name=target.shown), blocked=True)
        await patch(self._kube, target, {"spec": {self.field: self.value}}, MERGE, dry=True)
        return ActionPreview(summary=say(self.will, name=target.shown))

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        target, already = await self._state(node_id)
        if already:
            raise ActionRefused("not_applicable", say(self.already, name=target.shown))
        await patch(self._kube, target, {"spec": {self.field: self.value}}, MERGE)
        return ActionResult(message=say(self.done, name=target.shown), reload_node_ids=[target.level_id])


class Cordon(_Toggle):
    name: ClassVar[str] = "kubernetes_cordon"
    title: ClassVar[str] = N_("Cordon")
    icon: ClassVar[str | None] = "block"
    keys = frozenset({"/nodes"})
    field = "unschedulable"
    value = True
    will = N_("{name} will take no new pods; those on it stay")
    already = N_("{name} is cordoned already")
    done = N_("{name} cordoned")


class Uncordon(_Toggle):
    name: ClassVar[str] = "kubernetes_uncordon"
    title: ClassVar[str] = N_("Uncordon")
    icon: ClassVar[str | None] = "check_circle"
    keys = frozenset({"/nodes"})
    field = "unschedulable"
    value = False
    will = N_("{name} will take new pods again")
    already = N_("{name} takes pods already")
    done = N_("{name} uncordoned")


class Suspend(_Toggle):
    name: ClassVar[str] = "kubernetes_suspend"
    title: ClassVar[str] = N_("Suspend")
    icon: ClassVar[str | None] = "pause"
    keys = frozenset({"batch/cronjobs"})
    field = "suspend"
    value = True
    will = N_("{name} will start no new jobs; running ones go on")
    already = N_("{name} is suspended already")
    done = N_("{name} suspended")


class Resume(_Toggle):
    name: ClassVar[str] = "kubernetes_resume"
    title: ClassVar[str] = N_("Resume")
    icon: ClassVar[str | None] = "play_arrow"
    keys = frozenset({"batch/cronjobs"})
    field = "suspend"
    value = False
    will = N_("{name} will start jobs on its schedule again")
    already = N_("{name} is not suspended")
    done = N_("{name} resumed")


class RunNow(ObjectAction[NoParams]):
    """A Job made from a CronJob's template now, named and owned as kubectl
    makes one with `create job --from=cronjob/…`."""

    name: ClassVar[str] = "kubernetes_run_now"
    title: ClassVar[str] = N_("Run now")
    icon: ClassVar[str | None] = "play_circle"
    requires: ClassVar[Access] = "write"
    params_model = NoParams
    keys = frozenset({"batch/cronjobs"})
    verb = "create"

    def asked(self, target: Target) -> Asked:
        return Asked(verb="create", group="batch", resource="jobs", namespace=target.namespace)

    def _job(self, body: dict[str, Any], target: Target) -> dict[str, Any]:
        template = (body.get("spec") or {}).get("jobTemplate") or {}
        metadata = body.get("metadata") or {}
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": f"{target.name[:37]}-manual-{stamp}",
                "namespace": target.namespace,
                "annotations": {"cronjob.kubernetes.io/instantiate": "manual"},
                "labels": dict((template.get("metadata") or {}).get("labels") or {}),
                "ownerReferences": [
                    {
                        "apiVersion": "batch/v1",
                        "kind": "CronJob",
                        "name": target.name,
                        "uid": metadata.get("uid"),
                        "controller": True,
                    }
                ],
            },
            "spec": template.get("spec") or {},
        }

    async def _post(self, target: Target, job: dict[str, Any], *, dry: bool) -> None:
        await self._kube.session.request(
            "POST",
            f"/apis/batch/v1/namespaces/{segment(target.namespace or '')}/jobs",
            {"dryRun": "All"} if dry else None,
            body=job,
            asked=Forbidden("create", "jobs.batch"),
            expected=(201,),
        )

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        job = self._job(await read(self._kube, target), target)
        await self._post(target, job, dry=True)
        return ActionPreview(
            summary=say("A job {job} will start now from {name}", job=job["metadata"]["name"], name=target.shown)
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        target = await target_of(self._kube, node_id, set(self.keys))
        job = self._job(await read(self._kube, target), target)
        await self._post(target, job, dry=False)
        jobs = await self._kube.discovery.find("batch", "jobs")
        return ActionResult(
            message=say("Job {job} started", job=job["metadata"]["name"]),
            reload_node_ids=[kind_id(target.namespace, jobs)] if jobs is not None else [],
            created_node_id=object_id(target.namespace, "batch", "jobs", job["metadata"]["name"]),
        )


# --- deleting (D469) ----------------------------------------------------------------


Propagation = Literal["Background", "Foreground", "Orphan"]


class DeleteParams(BaseModel):
    propagation: Propagation = Field(
        default="Background",
        title=N_("What it owns"),
        description=N_(
            "Background: deleted after it; Foreground: before it; Orphan: left without an owner"
        ),
        json_schema_extra=layout(),
    )
    grace_seconds: int | None = Field(
        default=None,
        ge=0,
        le=MAX_GRACE,
        title=N_("Seconds a pod has to stop"),
        description=N_("Empty for the pod's own; 0 stops it at once"),
        json_schema_extra=layout(),
    )


class Delete(ObjectAction[DeleteParams]):
    name: ClassVar[str] = "kubernetes_delete"
    title: ClassVar[str] = N_("Delete")
    icon: ClassVar[str | None] = "delete"
    requires: ClassVar[Access] = "structure"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    params_model = DeleteParams
    verb = "delete"

    def fits(self, resource: Resource) -> bool:
        return "delete" in resource.verbs

    async def _delete(self, target: Target, params: DeleteParams, *, dry: bool) -> None:
        query: dict[str, str | int] = {"propagationPolicy": params.propagation}
        if dry:
            query["dryRun"] = "All"
        if params.grace_seconds is not None:
            query["gracePeriodSeconds"] = params.grace_seconds
        await self._kube.session.request(
            "DELETE",
            target.path,
            query,
            asked=target.resource.asked("delete"),
            node_id=target.node_id,
            expected=(200, 202),
        )

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        target = await target_of(self._kube, node_id)
        if not self.fits(target.resource):
            raise ActionRefused("not_applicable", say("The cluster does not delete a {kind}", kind=target.resource.kind))
        body = await read(self._kube, target)
        await self._delete(target, params, dry=True)
        items: list[str] = []
        for owner in (body.get("metadata") or {}).get("ownerReferences") or []:
            if isinstance(owner, dict) and owner.get("controller"):
                items.append(
                    say(
                        "{owner} owns it and will make it again",
                        owner=f"{owner.get('kind')}/{owner.get('name')}",
                    )
                )
        if target.resource.key == "/namespaces":
            items.append(say("Everything in the namespace is deleted with it"))
        return ActionPreview(summary=say("{name} will be deleted", name=target.shown), items=items)

    async def run(self, node_id: str | None, params: DeleteParams) -> ActionResult:
        target = await target_of(self._kube, node_id)
        if not self.fits(target.resource):
            raise ActionRefused("not_applicable", say("The cluster does not delete a {kind}", kind=target.resource.kind))
        await self._delete(target, params, dry=False)
        return ActionResult(message=say("{name} deleted", name=target.shown), reload_node_ids=[target.level_id])


# --- new from YAML (D470) ----------------------------------------------------------


class ApplyParams(BaseModel):
    manifest: str = Field(
        min_length=1,
        max_length=MAX_YAML,
        title=N_("YAML"),
        description=N_("One or more objects, separated by ---; applied in order"),
        json_schema_extra=layout(multiline=True, file=".yaml,.yml,.json"),
    )

    @field_validator("manifest")
    @classmethod
    def _documents(cls, text: str) -> str:
        documents(text)
        return text


def documents(text: str) -> list[dict[str, Any]]:
    try:
        found = [one for one in yaml.safe_load_all(text) if one is not None]
    except yaml.YAMLError:
        raise ValueError(say("This is not YAML the cluster could read")) from None
    if not found:
        raise ValueError(say("There is no object in it"))
    if len(found) > MAX_DOCUMENTS:
        raise ValueError(say("At most {count} objects at once", count=MAX_DOCUMENTS))
    for one in found:
        if not isinstance(one, dict) or not isinstance(one.get("metadata"), dict):
            raise ValueError(say("Every object has apiVersion, kind and metadata"))
        if not one.get("apiVersion") or not one.get("kind") or not one["metadata"].get("name"):
            raise ValueError(say("Every object has apiVersion, kind and metadata.name"))
    return found


@dataclass(frozen=True)
class Placed:
    document: dict[str, Any]
    resource: Resource
    namespace: str | None

    @property
    def shown(self) -> str:
        return f"{self.resource.kind}/{self.document['metadata']['name']}"

    @property
    def path(self) -> str:
        return self.resource.path(self.namespace, str(self.document["metadata"]["name"]))


class Apply(JsonAction[ApplyParams]):
    """Server-side apply of what was pasted, every object rehearsed first."""

    name: ClassVar[str] = "kubernetes_apply"
    title: ClassVar[str] = N_("New from YAML")
    icon: ClassVar[str | None] = "note_add"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = ApplyParams

    def __init__(self, kube: Kube) -> None:
        self._kube = kube

    @staticmethod
    def level_namespace(node_id: str | None) -> str | None:
        """The namespace an object without one lands in: the level's."""
        try:
            named = parse(node_id or "")
        except ValueError:
            raise ActionRefused("not_applicable", say("Choose a namespace or a kind")) from None
        if named.top not in ("namespace", "scoped") or named.name is not None:
            raise ActionRefused("not_applicable", say("Choose a namespace or a kind"))
        return None if named.namespace in (None, EVERY) else named.namespace

    async def _placed(self, node_id: str | None, manifest: str) -> list[Placed]:
        default = self.level_namespace(node_id)
        placed: list[Placed] = []
        resources = await self._kube.discovery.resources()
        for document in documents(manifest):
            group, _, version = str(document["apiVersion"]).rpartition("/")
            kind = str(document["kind"])
            resource = next(
                (one for one in resources if one.group == group and one.kind == kind),
                None,
            )
            if resource is None:
                raise ActionRefused(
                    "not_applicable",
                    say("The cluster serves no {kind} in {group}", kind=kind, group=group or "core"),
                )
            resource = Resource(group, version, resource.resource, kind, resource.namespaced, resource.verbs)
            namespace = None
            if resource.namespaced:
                namespace = str(document["metadata"].get("namespace") or default or "")
                if not namespace:
                    raise ActionRefused(
                        "not_applicable",
                        say("{kind}/{name} needs a namespace", kind=kind, name=document["metadata"]["name"]),
                    )
                document = {**document, "metadata": {**document["metadata"], "namespace": namespace}}
            placed.append(Placed(document, resource, namespace))
        return placed

    async def _apply(self, one: Placed, *, dry: bool) -> int:
        query: dict[str, str | int] = {"fieldManager": FIELD_MANAGER, "force": "true"}
        if dry:
            query["dryRun"] = "All"
        answer = await self._kube.session.request(
            "PATCH",
            one.path,
            query,
            body=one.document,
            content_type=APPLY,
            asked=one.resource.asked("patch"),
            expected=(200, 201),
        )
        return answer.status_code

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        placed = await self._placed(node_id, params.manifest)
        items: list[str] = []
        blocked = False
        for one in placed:
            try:
                status = await self._apply(one, dry=True)
            except AdapterError as refusal:
                blocked = True
                items.append(say("{name}: {reason}", name=one.shown, reason=refusal.message))
                continue
            items.append(
                say("{name} will be created", name=one.shown)
                if status == 201
                else say("{name} will be changed", name=one.shown)
            )
        return ActionPreview(
            summary=say("{count} objects; the cluster rehearsed each", count=len(placed)),
            items=items,
            blocked=blocked,
        )

    async def run(self, node_id: str | None, params: ApplyParams) -> ActionResult:
        placed = await self._placed(node_id, params.manifest)
        done: list[Placed] = []
        for one in placed:
            try:
                await self._apply(one, dry=False)
            except AdapterError as refusal:
                if not done:
                    raise
                raise ActionRefused(
                    "conflict",
                    say(
                        "{done} of {count} applied; {name} was refused: {reason}",
                        done=len(done),
                        count=len(placed),
                        name=one.shown,
                        reason=refusal.message,
                    ),
                ) from None
            done.append(one)
        return ActionResult(
            message=say("{name} applied", name=done[0].shown)
            if len(done) == 1
            else say("{count} objects applied", count=len(done)),
            reload_node_ids=list[str | None](sorted({kind_id(one.namespace, one.resource) for one in done})),
            created_node_id=object_id(
                done[0].namespace, done[0].resource.group, done[0].resource.resource, str(done[0].document["metadata"]["name"])
            )
            if len(done) == 1
            else None,
        )


OBJECT_ACTIONS: tuple[type[ObjectAction[Any]], ...] = (
    Scale,
    Restart,
    Cordon,
    Uncordon,
    Suspend,
    Resume,
    RunNow,
    Delete,
)
