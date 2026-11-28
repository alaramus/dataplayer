"""A Kubernetes cluster as a source (D463–D467).

Its namespaces and every kind it serves, found by its own discovery; a kind's
objects as the cluster's own table; an object as an overview, YAML and JSON,
with its events, its pods and a pod's logs as pages; the Cluster section's
reports. One type for every cluster: a managed one is a way in and a card
(D463), not a type.
"""

import json
from typing import Any, ClassVar

import httpx

from app.adapters import jsontext
from app.adapters.actions import Action, ActionRefused, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.changes import ChangeSink, ChangeWatch
from app.adapters.content import (
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    JsonContent,
    TextContent,
    UpdateContentRequest,
    json_tree,
)
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kubernetes.actions import (
    OBJECT_ACTIONS,
    Apply,
    Kube,
    ObjectAction,
    target_of,
)
from app.adapters.kubernetes.card import (
    as_dict,
    as_list,
    as_yaml,
    editable_yaml,
    edited_object,
    object_view,
    redacted,
)
from app.adapters.kubernetes.catalog import (
    EVERY,
    SELECTS_PODS,
    Named,
    cluster_node,
    kind_node,
    namespace_node,
    namespaces_node,
    object_node,
    page_node,
    parse,
    scoped_node,
    section_node,
    view_pages,
)
from app.adapters.kubernetes.connect import OpenAsConnection
from app.adapters.kubernetes.discovery import SECTIONS, Discovery, Resource, Section
from app.adapters.kubernetes.forward import FORWARDS
from app.adapters.kubernetes.jobs import Drain
from app.adapters.kubernetes.options import KubernetesConnection, KubernetesOptions
from app.adapters.kubernetes.reports import (
    REPORTS,
    Context,
    read_report,
    report_for,
    report_node,
)
from app.adapters.kubernetes.reviews import Reviews
from app.adapters.kubernetes.session import Forbidden, KubernetesSession, segment
from app.adapters.kubernetes.tables import (
    EVENT_COLUMNS,
    LOG_BYTES,
    LOG_COLUMNS,
    LOG_DEPTH,
    Listed,
    cut_notice,
    instant,
    log_rows,
    page,
    pod_selector,
    read_events,
    read_table,
)
from app.adapters.kubernetes.terminal import PodTerminal
from app.adapters.kubernetes.watch import KubernetesWatch
from app.adapters.listed import listed_column
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.tunnels import TunnelAccess
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say


class KubernetesAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    # An object is not rows: a kind's table is copied from the grid (D164).
    catalog_clipboard: ClassVar[bool] = False

    def __init__(
        self,
        options: KubernetesConnection,
        tunnels: TunnelAccess | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        connector_id: str | None = None,
    ) -> None:
        self._session = KubernetesSession(options, tunnels, transport)
        self._tunnels = tunnels
        self._discovery = Discovery(self._session)
        self._namespace = options.namespace or None
        self._kube = Kube(self._session, self._discovery, Reviews(self._session))
        self._connect = OpenAsConnection(self._kube, connector_id)
        self._object_actions: list[ObjectAction[Any] | Drain | PodTerminal | OpenAsConnection] = [
            *(kind(self._kube) for kind in OBJECT_ACTIONS),
            Drain(self._kube),
            PodTerminal(self._kube),
            self._connect,
        ]
        self._actions = ActionSet([*self._object_actions, Apply(self._kube)])

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        await self._session.client()
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=f"Kubernetes {self._session.git_version}"[:100],
            features=[],
        )

    def _context(self) -> Context:
        return Context(self._session, self._discovery, self._namespace)

    # --- resolving what a node names -----------------------------------------

    async def _resource(self, named: Named, node_id: str) -> Resource:
        """The kind a node names, as discovery found it, on its own side."""
        assert named.resource is not None and named.group is not None
        found = await self._discovery.find(named.group, named.resource)
        if found is None or found.namespaced != (named.top == "namespace"):
            raise NodeNotFound(node_id)
        return found

    def _namespace_of(self, named: Named) -> str | None:
        """The namespace a list is asked in: None across the cluster."""
        if named.top != "namespace" or named.namespace == EVERY:
            return None
        return named.namespace

    async def _object(
        self, named: Named, node_id: str, *, numbers_as_text: bool = False
    ) -> tuple[Resource, dict[str, Any]]:
        """The object as the cluster holds it. `numbers_as_text` reads it as a
        JSON tree takes it (`jsontext`), each number kept as written."""
        resource = await self._resource(named, node_id)
        assert named.name is not None
        answer = await self._session.request(
            "GET",
            resource.path(named.namespace, named.name),
            asked=resource.asked("get"),
            node_id=node_id,
        )
        try:
            body = jsontext.load(answer.text) if numbers_as_text else json.loads(answer.content)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise AdapterError("unknown", say("The cluster did not answer with JSON"))
        return resource, body

    # --- the catalog (D465) --------------------------------------------------

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [cluster_node(), namespaces_node(), scoped_node()]
        named = parse(node_id)
        if named.top == "cluster":
            if named.report is None:
                return [report_node(report) for report in REPORTS]
            if report_for(node_id) is None:
                raise NodeNotFound(node_id)
            return []
        if named.top == "namespaces":
            return await self._namespaces()
        if named.name is not None:
            if named.view is None:
                await self._object(named, node_id)
            return []
        if named.resource is not None:
            resource = await self._resource(named, node_id)
            listed = await read_table(
                self._session, resource, self._namespace_of(named), node_id=node_id
            )
            namespaces = {namespace if resource.namespaced else None for _, namespace, _ in listed.names}
            offered = {namespace: await self._offered(resource, namespace) for namespace in namespaces}
            return self._object_nodes(resource, listed, offered)
        resources = await self._discovery.resources()
        namespaced = named.top == "namespace"
        if named.section is not None:
            return [
                kind_node(named.namespace, one)
                for one in resources
                if one.namespaced == namespaced and one.section == named.section
            ]
        present = {one.section for one in resources if one.namespaced == namespaced}
        return [section_node(named.namespace, section) for section in SECTIONS if section in present]

    async def _namespaces(self) -> list[CatalogNode]:
        if self._namespace is not None:
            return [namespace_node(self._namespace)]
        found = await self._discovery.find("", "namespaces")
        if found is None:
            return []
        listed = await read_table(self._session, found, None)
        names = sorted(name for name, _, _ in listed.names)
        return [namespace_node(EVERY), *(namespace_node(name) for name in names)]

    async def _offered(self, resource: Resource, namespace: str | None) -> list[str]:
        """What every object of `resource` in `namespace` admits, as `available`
        answers for one of them: RBAC does not tell objects of a kind apart."""
        fitting = [action for action in self._object_actions if action.fits(resource)]
        allowed = await self._kube.reviews.all_allow([action.asked_at(resource, namespace) for action in fitting])
        return [action.name for action, yes in zip(fitting, allowed, strict=True) if yes]

    @staticmethod
    def _object_nodes(
        resource: Resource, listed: Listed, offered: dict[str | None, list[str]]
    ) -> list[CatalogNode]:
        nodes: list[CatalogNode] = [
            object_node(
                namespace if resource.namespaced else None,
                resource,
                name,
                summary=summary,
                created_at=instant(created),
                actions=offered.get(namespace if resource.namespaced else None, []),
            )
            for (name, namespace, created), summary in zip(listed.names, listed.summaries, strict=True)
        ]
        return sorted(nodes, key=lambda node: ((getattr(node, "namespace", None) or ""), node.name))

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        named = parse(node_id)
        if named.top == "cluster":
            if named.report is None:
                return [cluster_node()]
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [cluster_node(), report_node(report)]
        if named.top == "namespaces":
            return [namespaces_node()]
        path: list[CatalogNode] = (
            [namespaces_node(), namespace_node(named.namespace or "")]
            if named.top == "namespace"
            else [scoped_node()]
        )
        if named.section is not None:
            return [*path, section_node(named.namespace, named.section)]
        if named.resource is None:
            return path
        resource = await self._resource(named, node_id)
        section: Section = resource.section
        path += [section_node(named.namespace, section), kind_node(named.namespace, resource)]
        if named.name is None:
            return path
        _, body = await self._object(named, node_id)
        metadata = as_dict(body.get("metadata"))
        path.append(
            object_node(
                named.namespace,
                resource,
                named.name,
                summary=None,
                created_at=instant(metadata.get("creationTimestamp")),
            )
        )
        if named.view is not None:
            path.append(page_node(named))
        return path

    # --- rows (D465, D466) ---------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        named = parse(request.node_id)
        if named.top == "cluster":
            if named.report is None:
                raise ValueError(say("Open one of the Cluster reports"))
            return await read_report(self._context(), request)
        if named.top == "namespaces":
            found = await self._discovery.find("", "namespaces")
            if found is None:
                raise NodeNotFound(request.node_id)
            listed = await read_table(self._session, found, None, node_id=request.node_id)
            return page(request, listed.columns, listed.rows, notice=cut_notice(listed))
        if named.name is not None:
            if named.view is None:
                raise ValueError(say("This opens as what the cluster says about it"))
            return await self._page(request, named)
        if named.resource is None:
            raise ValueError(say("Open one of the kinds inside"))
        resource = await self._resource(named, request.node_id)
        listed = await read_table(
            self._session, resource, self._namespace_of(named), node_id=request.node_id
        )
        return page(request, listed.columns, listed.rows, notice=cut_notice(listed))

    async def _page(self, request: FetchRequest, named: Named) -> FetchResult:
        resource, body = await self._object(named, request.node_id)
        if named.view == "events":
            selector = f"involvedObject.name={named.name},involvedObject.kind={resource.kind}"
            rows = await read_events(self._session, named.namespace, selector)
            return page(request, EVENT_COLUMNS, rows, refresh_seconds=10)
        if named.view == "pods":
            if resource.key not in SELECTS_PODS:
                raise NodeNotFound(request.node_id)
            pods = await self._discovery.find("", "pods")
            picks = pod_selector(body)
            if pods is None or picks is None:
                return page(request, [listed_column("Name", "string")], [], notice=say("It picks no pods"))
            listed = await read_table(self._session, pods, named.namespace, selector=picks)
            return page(request, listed.columns, listed.rows, notice=cut_notice(listed))
        return await self._logs(request, named, resource, body)

    async def _logs(
        self,
        request: FetchRequest,
        named: Named,
        resource: Resource,
        body: dict[str, Any],
    ) -> FetchResult:
        if resource.key != "/pods":
            raise NodeNotFound(request.node_id)
        spec = as_dict(body.get("spec"))
        names = {
            str(as_dict(one).get("name"))
            for one in as_list(spec.get("initContainers")) + as_list(spec.get("containers"))
        }
        if named.container not in names:
            raise NodeNotFound(request.node_id)
        # Newest first: the page's end is how deep the tail must reach.
        depth = min(request.offset + request.limit + 1, LOG_DEPTH)
        assert named.name is not None and named.namespace is not None
        answer = await self._session.request(
            "GET",
            f"/api/v1/namespaces/{segment(named.namespace)}/pods/{segment(named.name)}/log",
            {
                "container": named.container or "",
                "tailLines": depth,
                "timestamps": "true",
                "limitBytes": LOG_BYTES,
            },
            asked=Forbidden("get", "pods/log"),
            # The log is text, yet `text/plain` is refused with 406: only the
            # API's own media types and `*/*` are accepted (checked, 1.33).
            accept="*/*",
            expected=(200, 400),
        )
        if answer.status_code == 400:
            # A container that has not started yet has no log to read.
            return page(request, LOG_COLUMNS, [], narrowed=False, notice=say("The container has not printed anything yet"))
        rows = log_rows(answer.text)
        notice = say("Only the last {count} lines are read", count=LOG_DEPTH) if depth >= LOG_DEPTH else None
        return page(request, LOG_COLUMNS, rows, narrowed=False, notice=notice, refresh_seconds=5)

    # --- what may be changed (D467–D471) ------------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return (*OBJECT_ACTIONS, Drain, PodTerminal, OpenAsConnection, Apply)

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        """What a node admits and the cluster's RBAC allows (D467): an action
        the cluster would refuse is not offered."""
        if node_id is None:
            return []
        try:
            named = parse(node_id)
        except ValueError:
            return []
        if named.top in ("cluster", "namespaces") or named.view is not None:
            return []
        if named.name is None:
            return [self._actions.get(Apply.name)]
        try:
            target = await target_of(self._kube, node_id)
        except (ActionRefused, NodeNotFound):
            return []
        fitting = [action for action in self._object_actions if action.fits(target.resource)]
        allowed = await self._kube.reviews.all_allow([action.asked(target) for action in fitting])
        offered: list[Action[Any]] = [action for action, yes in zip(fitting, allowed, strict=True) if yes]
        # Offered only where a type declares the image (D474): one read of the
        # pod, the menu's own. A listed row cannot tell, so it names it anyway.
        if self._connect in offered and not await self._connect.offered(node_id):
            offered.remove(self._connect)
        return offered

    # --- a port of the cluster carried for another connection (D474) ----------

    async def forward(self, host: str, port: int) -> tuple[str, int]:
        return await FORWARDS.endpoint(self._session.options, self._tunnels, host, port)

    # --- a container's logs told as they grow (D473) ---------------------------

    async def watch_changes(self, sink: ChangeSink) -> ChangeWatch:
        return KubernetesWatch(self._session, sink)

    # --- an object's YAML, edited where it is (D470) --------------------------------

    async def read_editor_content(self, request: EditorContentRequest) -> EditorContent:
        named = parse(request.node_id)
        if named.name is None or named.view is not None:
            raise ValueError(say("This opens as a table"))
        resource, body = await self._object(named, request.node_id)
        metadata = as_dict(body.get("metadata"))
        if resource.key == "/secrets":
            return EditorContent(
                text=as_yaml(resource, body),
                filename=f"{named.name}.yaml",
                language_hint="yaml",
                version=str(metadata.get("resourceVersion") or ""),
                writable=False,
                reason=say("A secret's values are not shown here, so it is not edited here"),
            )
        return EditorContent(
            text=editable_yaml(body),
            filename=f"{named.name}.yaml",
            language_hint="yaml",
            version=str(metadata.get("resourceVersion") or ""),
            writable="update" in resource.verbs,
            reason=None if "update" in resource.verbs else say("The cluster does not change a {kind} in place", kind=resource.kind),
        )

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        """The whole object, if nobody changed it since it was read: the
        version is its `resourceVersion`, and the cluster answers 409 otherwise."""
        named = parse(request.node_id)
        if named.name is None or named.view is not None:
            raise ValueError(say("This opens as a table"))
        resource = await self._resource(named, request.node_id)
        if resource.key == "/secrets":
            raise ValueError(say("A secret's values are not shown here, so it is not edited here"))
        edited = edited_object(request.text, resource, named)
        edited["metadata"]["resourceVersion"] = request.version
        try:
            answer = await self._session.request(
                "PUT",
                resource.path(named.namespace, named.name),
                body=edited,
                asked=resource.asked("update"),
                node_id=request.node_id,
                expected=(200, 201, 409),
            )
        except AdapterError as refusal:
            raise ValueError(refusal.message) from None
        if answer.status_code == 409:
            raise ContentConflict()
        saved = answer.json() or {}
        return ContentUpdated(version=str((saved.get("metadata") or {}).get("resourceVersion") or ""))

    # --- what the cluster says about one object (D466) -------------------------

    async def read_content(self, request: ContentRequest) -> ContentResult:
        named = parse(request.node_id)
        if named.name is None or named.view is not None:
            raise ValueError(say("This opens as a table"))
        resource, body = await self._object(
            named, request.node_id, numbers_as_text=request.representation == "tree"
        )
        if request.representation == "view":
            view = object_view(resource, body)
            containers = [
                str(as_dict(one).get("name"))
                for one in as_list(as_dict(body.get("spec")).get("initContainers"))
                + as_list(as_dict(body.get("spec")).get("containers"))
            ]
            return view.model_copy(update={"pages": view_pages(named, resource, containers)})
        if request.representation == "text":
            return TextContent(text=as_yaml(resource, body))
        if request.representation == "tree":
            return JsonContent(value=json_tree(redacted(resource, body)))
        raise ValueError(say("This opens as what the cluster says about it"))


@register(
    name="kubernetes",
    title=N_("Kubernetes"),
    category="containers",
    description=N_(
        "A Kubernetes cluster reached through its API server, signed in to with a "
        "kubeconfig, a token or a client certificate. See its namespaces and every "
        "kind of object it serves, custom ones included, as the cluster's own tables; "
        "each object's overview, YAML, events and pods, a pod's logs, and the "
        "cluster's nodes, events and API resources."
    ),
    options_schema=KubernetesOptions,
    adapter_class=KubernetesAdapter,
    faces=(CatalogFace(key="kubernetes", title=N_("Kubernetes")),),
)
def _build(options: KubernetesConnection, context: AdapterContext) -> KubernetesAdapter:
    connector_id = None if context.pooling is None else str(context.pooling.connector_id)
    return KubernetesAdapter(options, context.tunnels, connector_id=connector_id)

