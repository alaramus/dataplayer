"""A cluster measured from metrics.k8s.io, searched by name and a kind's
table exported (D475, D476)."""

import pytest

from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.kubernetes.adapter import KubernetesAdapter
from app.adapters.kubernetes.catalog import object_id
from app.adapters.kubernetes.metrics import (
    POLLED,
    Measured,
    Usage,
    quantity,
    samples_of,
    top_rows,
    usages,
)
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters import kubernetes_stand as stand


def test_a_quantity_is_cores_or_bytes() -> None:
    assert quantity("894980n") == pytest.approx(0.00089498)
    assert quantity("82m") == pytest.approx(0.082)
    assert quantity("2") == 2.0
    assert quantity("600Ki") == 600 * 1024
    assert quantity("1.5Gi") == 1.5 * 2**30
    assert quantity("1e3") == 1000.0
    assert quantity("lots") is None
    assert quantity(None) is None


def test_nodes_say_their_share_and_pods_come_busiest_first() -> None:
    found = usages(
        [{"metadata": {"name": "n1"}, "usage": {"cpu": "500m", "memory": "1Gi"}}],
        [
            {"metadata": {"name": "quiet", "namespace": "a"}, "containers": [{"usage": {"cpu": "1m", "memory": "1Mi"}}]},
            {
                "metadata": {"name": "busy", "namespace": "a"},
                "containers": [{"usage": {"cpu": "200m", "memory": "10Mi"}}, {"usage": {"cpu": "100m", "memory": "6Mi"}}],
            },
        ],
        [{"metadata": {"name": "n1"}, "status": {"allocatable": {"cpu": "2", "memory": "4Gi"}}}],
    )
    assert found.nodes[0].cpu_share == pytest.approx(25.0)
    assert found.nodes[0].memory_share == pytest.approx(25.0)
    assert [pod.label for pod in found.pods] == ["a/busy", "a/quiet"]
    assert top_rows(found)[1] == ["Pod", "a", "busy", "300", "16.0", None, None]


def test_a_poll_measures_the_busiest_pods_and_counts_the_rest() -> None:
    pods = [Usage("Pod", "a", f"p{index}", 0.001, 1.0) for index in range(POLLED + 5)]
    samples = samples_of(Measured([], pods))
    assert len([one for one in samples if one.metric == "pod" and one.field == "cpu"]) == POLLED
    counted = {one.field: one.value for one in samples if one.metric == "cluster"}
    assert counted == {"pods_measured": POLLED, "pods_skipped": 5}


@pytest.fixture(scope="module")
async def adapter() -> KubernetesAdapter:
    await stand.prepare()
    return KubernetesAdapter(stand.admin_options())


async def test_the_stand_is_measured(adapter: KubernetesAdapter) -> None:
    samples = await adapter.metric_samples()
    if not samples:
        pytest.skip("metrics-server on the k3s stand has nothing to serve yet")
    assert {one.label for one in samples if one.metric == "node"} == {"k3s"}
    assert any(one.metric == "pod" and one.label.startswith(f"{stand.NAMESPACE}/web-") for one in samples)
    top = await adapter.fetch(FetchRequest(node_id="cluster/top", limit=100))
    assert top.rows[0][:3] == ["Node", None, "k3s"]


async def test_a_namespace_held_connection_measures_only_its_pods() -> None:
    held = KubernetesAdapter(stand.admin_options().model_copy(update={"namespace": stand.NAMESPACE}))
    samples = await held.metric_samples()
    assert not any(one.metric == "node" for one in samples)
    assert all(one.label.startswith(f"{stand.NAMESPACE}/") for one in samples if one.metric == "pod")


def _searched(query: str, node_id: str | None = None) -> NodeSearchRequest:
    return NodeSearchRequest(query=query, node_id=node_id, limit=50)


async def test_a_search_finds_objects_where_the_catalog_lists_them(adapter: KubernetesAdapter) -> None:
    found = await adapter.search_nodes(_searched("web"))
    by_id = {one.node.id: one for one in found.matches}
    deployment = object_id(stand.NAMESPACE, "apps", "deployments", "web")
    assert deployment in by_id
    assert by_id[deployment].parent_id == f"ns/{stand.NAMESPACE}/k/apps/deployments"
    assert [one.node_id for one in by_id[deployment].ancestors][:2] == ["namespaces", f"ns/{stand.NAMESPACE}"]
    assert object_id(stand.NAMESPACE, "", "services", "web") in by_id
    namespaces = await adapter.search_nodes(_searched(stand.NAMESPACE, "namespaces"))
    assert [one.node.id for one in namespaces.matches] == [f"ns/{stand.NAMESPACE}"]


async def test_a_search_keeps_to_its_namespace_section_or_kind(adapter: KubernetesAdapter) -> None:
    in_kind = await adapter.search_nodes(_searched("web", f"ns/{stand.NAMESPACE}/k/apps/deployments"))
    assert {one.node.id for one in in_kind.matches} == {object_id(stand.NAMESPACE, "apps", "deployments", "web")}
    in_section = await adapter.search_nodes(_searched("web", f"ns/{stand.NAMESPACE}/s/network"))
    assert {one.node.id for one in in_section.matches} == {object_id(stand.NAMESPACE, "", "services", "web")}
    elsewhere = await adapter.search_nodes(_searched("coredns", f"ns/{stand.NAMESPACE}"))
    assert elsewhere.matches == []
    with pytest.raises(ValueError, match="starts at the top"):
        await adapter.search_nodes(_searched("web", object_id(stand.NAMESPACE, "apps", "deployments", "web")))


async def test_every_searched_name_is_kept_under_its_kind(adapter: KubernetesAdapter) -> None:
    batches = [batch async for batch in adapter.enumerate_names(10_000, SearchBounds.within(30))]
    names = {one.node.id: one.scope for batch in batches for one in batch.names}
    assert names[object_id(stand.NAMESPACE, "apps", "deployments", "web")] == f"ns/{stand.NAMESPACE}/k/apps/deployments"
    assert names[f"ns/{stand.NAMESPACE}"] == "namespaces"
    assert any(node.startswith("scoped/o/core/nodes/") for node in names)


async def test_a_kinds_table_is_exported_as_it_is_read(adapter: KubernetesAdapter) -> None:
    node = f"ns/{stand.NAMESPACE}/k/core/configmaps"
    request = ExportRequest(
        node_id=node,
        columns=["Name"],
        filters=[ScalarFilter(column="Name", op="contains", value="settings")],
        sort=[Sort(column="Name")],
    )
    rows = [row async for batch in adapter.export_rows(request) for row in batch.rows]
    assert rows == [["settings"]]
    with pytest.raises(ValueError, match="Unknown column"):
        [batch async for batch in adapter.export_rows(request.model_copy(update={"columns": ["Nope"]}))]
    with pytest.raises(ValueError, match="a page at a time"):
        [batch async for batch in adapter.export_rows(request.model_copy(update={"node_id": "cluster/top"}))]
