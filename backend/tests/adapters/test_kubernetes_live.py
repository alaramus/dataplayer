"""The source against the k3s stand (D463–D467); skipped without it."""

import pytest

from app.adapters.catalog import KubeObjectNode
from app.adapters.content import ContentRequest, JsonContent, TextContent
from app.adapters.fetch import FetchRequest
from app.adapters.kubernetes.adapter import KubernetesAdapter
from app.adapters.protocol import NodeNotFound
from app.adapters.views import DocumentView
from tests.adapters import kubernetes_stand as stand


@pytest.fixture(scope="module")
async def adapter() -> KubernetesAdapter:
    await stand.prepare()
    return KubernetesAdapter(stand.admin_options())


async def test_the_catalog_is_built_from_discovery(adapter: KubernetesAdapter) -> None:
    assert (await adapter.check_connection()).ok
    namespaces = [node.name for node in await adapter.list_children("namespaces")]
    assert namespaces[0] == "All namespaces" and stand.NAMESPACE in namespaces
    sections = [node.id for node in await adapter.list_children(f"ns/{stand.NAMESPACE}")]
    assert sections[0] == f"ns/{stand.NAMESPACE}/s/workloads"
    # k3s's own custom resources are found the way built-in kinds are.
    other = [node.name for node in await adapter.list_children(f"ns/{stand.NAMESPACE}/s/other")]
    assert "helmcharts (helm.cattle.io)" in other
    pods = await adapter.list_children(f"ns/{stand.NAMESPACE}/k/core/pods")
    assert len(pods) == 2
    assert all(isinstance(pod, KubeObjectNode) and pod.summary == "1/1 · Running" for pod in pods)


async def test_a_kinds_table_is_the_clusters_own(adapter: KubernetesAdapter) -> None:
    result = await adapter.fetch(FetchRequest(node_id="ns/*/k/apps/deployments"))
    names = [column.name for column in result.columns]
    assert names[:3] == ["Namespace", "Name", "Ready"] and names[-1] == "Created"
    assert [stand.NAMESPACE, "web", "2/2"] in [row[:3] for row in result.rows]


async def test_an_object_opens_as_overview_yaml_and_json(adapter: KubernetesAdapter) -> None:
    node = f"ns/{stand.NAMESPACE}/o/apps/deployments/web"
    view = await adapter.read_content(ContentRequest(node_id=node, representation="view"))
    assert isinstance(view, DocumentView)
    assert view.header.state is not None and view.header.state.word == "2/2"
    assert [page.node_id for page in view.pages] == [f"{node}/pods", f"{node}/events"]
    pods = await adapter.fetch(FetchRequest(node_id=f"{node}/pods"))
    assert len(pods.rows) == 2
    text = await adapter.read_content(ContentRequest(node_id=node, representation="text"))
    assert isinstance(text, TextContent) and "kind: Deployment" in text.text
    # A deployment has numbers in it (replicas, ports), which a JSON tree takes
    # only as `jsontext` reads them.
    tree = await adapter.read_content(ContentRequest(node_id=node, representation="tree"))
    assert isinstance(tree, JsonContent) and '"replicas"' in tree.model_dump_json()


async def test_a_secret_is_never_shown(adapter: KubernetesAdapter) -> None:
    node = f"ns/{stand.NAMESPACE}/o/core/secrets/password"
    for representation in ("view", "text", "tree"):
        found = await adapter.read_content(ContentRequest(node_id=node, representation=representation))
        assert "c2VjcmV0LXZhbHVl" not in found.model_dump_json()
    tree = await adapter.read_content(ContentRequest(node_id=node, representation="tree"))
    assert isinstance(tree, JsonContent)


async def test_a_pods_logs_and_the_cluster_reports(adapter: KubernetesAdapter) -> None:
    pod = (await adapter.list_children(f"ns/{stand.NAMESPACE}/k/core/pods"))[0].id
    logs = await adapter.fetch(FetchRequest(node_id=f"{pod}/logs/echo", limit=2))
    assert len(logs.rows) == 2 and str(logs.rows[0][1]).startswith("line ")
    path = [node.name for node in await adapter.path_to(f"{pod}/logs/echo")]
    assert path[:3] == ["Namespaces", stand.NAMESPACE, "Workloads"] and path[-1] == "Logs: echo"
    overview = {
        row[0]: row[1] for row in (await adapter.fetch(FetchRequest(node_id="cluster/overview"))).rows
    }
    assert overview["Nodes ready"] == "1 / 1"
    assert int(str(overview["Pods Running"])) >= 2
    nodes = await adapter.fetch(FetchRequest(node_id="cluster/nodes"))
    assert nodes.rows[0][1] == "Ready"
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id=f"ns/{stand.NAMESPACE}/o/core/pods/nobody/events"))


async def test_rbac_is_said_by_the_verb_asked(adapter: KubernetesAdapter) -> None:
    del adapter
    reader = KubernetesAdapter(await stand.reader_options())
    namespaces = [node.name for node in await reader.list_children("namespaces")]
    assert namespaces == [stand.NAMESPACE]
    assert len(await reader.list_children(f"ns/{stand.NAMESPACE}/k/core/pods")) == 2
    from app.adapters.protocol import AdapterError

    with pytest.raises(AdapterError) as refused:
        await reader.fetch(FetchRequest(node_id=f"ns/{stand.NAMESPACE}/k/core/secrets"))
    assert refused.value.error_kind == "auth"
    assert "list secrets" in refused.value.message
    assert "dp-reader" not in refused.value.message
