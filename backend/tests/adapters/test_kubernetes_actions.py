"""Changing a cluster (D467–D471): what is offered, what is rehearsed, what
is refused, and an object's YAML edited where it is."""

from typing import Any

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.content import (
    ContentConflict,
    EditorContentRequest,
    UpdateContentRequest,
)
from app.adapters.kubernetes.actions import documents
from app.adapters.kubernetes.adapter import KubernetesAdapter
from app.adapters.kubernetes.card import editable_yaml, edited_object
from app.adapters.kubernetes.catalog import parse
from app.adapters.kubernetes.discovery import Resource
from app.adapters.kubernetes.jobs import _pods_on
from app.adapters.operations import OperationTarget
from tests.adapters import kubernetes_stand as stand

DEPLOYMENT = f"ns/{stand.NAMESPACE}/o/apps/deployments/web"
SETTINGS = f"ns/{stand.NAMESPACE}/o/core/configmaps/settings"
NODE = "scoped/o/core/nodes/k3s"
CONFIGMAPS = Resource("", "v1", "configmaps", "ConfigMap", True, frozenset({"get", "update"}))


def test_pasted_yaml_is_read_as_objects_or_refused() -> None:
    two = "kind: A\napiVersion: v1\nmetadata: {name: a}\n---\n---\nkind: B\napiVersion: v1\nmetadata: {name: b}"
    assert len(documents(two)) == 2
    for text, words in [
        ("a: [unclosed", "not YAML"),
        ("---\n", "no object"),
        ("- just\n- a list", "apiVersion, kind and metadata"),
        ("apiVersion: v1\nkind: ConfigMap\nmetadata: {}", "metadata.name"),
    ]:
        with pytest.raises(ValueError, match=words):
            documents(text)


def test_an_edit_keeps_which_object_it_is() -> None:
    named = parse(SETTINGS)
    body = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "settings", "namespace": stand.NAMESPACE, "managedFields": [{}]},
        "data": {"mode": "test"},
        "status": {"x": 1},
    }
    text = editable_yaml(body)
    assert "managedFields" not in text and "status" not in text
    edited = edited_object(text.replace("mode: test", "mode: edited"), CONFIGMAPS, named)
    assert edited["data"] == {"mode": "edited"}
    for changed in (text.replace("name: settings", "name: other"), text.replace("kind: ConfigMap", "kind: Secret")):
        with pytest.raises(ValueError, match="stay as they were"):
            edited_object(changed, CONFIGMAPS, named)


def test_a_drain_leaves_what_kubectl_leaves() -> None:
    pods = {
        "items": [
            {"metadata": {"name": "a", "namespace": "n"}, "status": {"phase": "Running"}},
            {"metadata": {"name": "b", "namespace": "n", "ownerReferences": [{"kind": "DaemonSet"}]}},
            {"metadata": {"name": "c", "namespace": "n", "annotations": {"kubernetes.io/config.mirror": "x"}}},
            {"metadata": {"name": "d", "namespace": "n"}, "status": {"phase": "Succeeded"}},
        ]
    }
    evicted, left = _pods_on(pods)
    assert [pod["metadata"]["name"] for pod in evicted] == ["a"]
    assert len(left) == 2


@pytest.fixture(scope="module")
async def adapter() -> KubernetesAdapter:
    await stand.prepare()
    return KubernetesAdapter(stand.admin_options())


def _action(adapter: KubernetesAdapter, name: str) -> Any:
    """An action by name, as the route reaches it; typed loosely, since each
    capability (previews, hints, a job) is a protocol of its own."""
    return adapter.action(name)


async def test_a_menu_offers_what_fits_the_kind(adapter: KubernetesAdapter) -> None:
    assert [one.name for one in await adapter.available(DEPLOYMENT)] == [
        "kubernetes_scale",
        "kubernetes_restart",
        "kubernetes_delete",
    ]
    assert "kubernetes_drain" in [one.name for one in await adapter.available(NODE)]
    assert [one.name for one in await adapter.available(f"ns/{stand.NAMESPACE}")] == ["kubernetes_apply"]
    assert await adapter.available("cluster/overview") == []


async def test_a_menu_leaves_out_what_rbac_would_refuse(adapter: KubernetesAdapter) -> None:
    del adapter
    reader = KubernetesAdapter(await stand.reader_options())
    assert await reader.available(DEPLOYMENT) == []


async def test_scaling_is_rehearsed_then_done(adapter: KubernetesAdapter) -> None:
    scale = _action(adapter, "kubernetes_scale")
    assert (await scale.field_hints(DEPLOYMENT)).values == {"replicas": "2"}
    preview = await scale.preview(DEPLOYMENT, {"replicas": 3})
    assert preview.summary == "Deployment/web: 2 → 3 replicas" and not preview.blocked
    assert (await scale.preview(DEPLOYMENT, {"replicas": 2})).blocked
    try:
        await scale.perform(DEPLOYMENT, {"replicas": 3})
        body = await adapter._session.get(f"/apis/apps/v1/namespaces/{stand.NAMESPACE}/deployments/web")
        assert body["spec"]["replicas"] == 3
    finally:
        await scale.perform(DEPLOYMENT, {"replicas": 2})


async def test_yaml_is_applied_rehearsed_first_and_deleted(adapter: KubernetesAdapter) -> None:
    apply = _action(adapter, "kubernetes_apply")
    level = f"ns/{stand.NAMESPACE}"
    bad = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: Bad_Name\n"
    preview = await apply.preview(level, {"manifest": bad})
    assert preview.blocked and "metadata.name" in preview.items[0]
    good = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: from-yaml\ndata:\n  a: b\n"
    assert (await apply.preview(level, {"manifest": good})).items == ["ConfigMap/from-yaml will be created"]
    result = await apply.perform(level, {"manifest": good})
    made = f"ns/{stand.NAMESPACE}/o/core/configmaps/from-yaml"
    assert result.created_node_id == made and result.message == "ConfigMap/from-yaml applied"
    delete = _action(adapter, "kubernetes_delete")
    assert (await delete.preview(made, {})).summary == "ConfigMap/from-yaml will be deleted"
    await delete.perform(made, {})
    unknown = "apiVersion: example.com/v1\nkind: Nope\nmetadata: {name: x}"
    with pytest.raises(ActionRefused):
        await apply.preview(level, {"manifest": unknown})


async def test_yaml_is_edited_only_at_the_version_read(adapter: KubernetesAdapter) -> None:
    read = await adapter.read_editor_content(EditorContentRequest(node_id=SETTINGS))
    assert read.writable and read.language_hint == "yaml"
    changed = read.text.replace("mode: test", "mode: edited")
    saved = await adapter.update_content(
        UpdateContentRequest(node_id=SETTINGS, text=changed, version=read.version or "")
    )
    try:
        with pytest.raises(ContentConflict):
            await adapter.update_content(
                UpdateContentRequest(node_id=SETTINGS, text=changed, version=read.version or "")
            )
    finally:
        await adapter.update_content(
            UpdateContentRequest(node_id=SETTINGS, text=read.text, version=saved.version)
        )
    secret = await adapter.read_editor_content(
        EditorContentRequest(node_id=f"ns/{stand.NAMESPACE}/o/core/secrets/password")
    )
    assert not secret.writable and "c2VjcmV0" not in secret.text


async def test_a_drain_cordons_and_evicts_one_pod_a_unit(adapter: KubernetesAdapter) -> None:
    drain = _action(adapter, "kubernetes_drain")
    params = {"local_data": True}
    preview = await drain.preview(NODE, params)
    assert preview.runs_as_job and preview.fingerprint
    pod = (await adapter.list_children(f"ns/{stand.NAMESPACE}/k/core/pods"))[0].name
    target = OperationTarget(schema_name=stand.NAMESPACE, name=pod)
    try:
        plan = await drain.plan_job(NODE, params, preview.fingerprint)
        assert target in plan.targets
        assert await drain.run_unit(NODE, params, plan.unit_fingerprint, target) == "completed"
        assert await drain.observe(NODE, params, [target]) in (["as_requested"], ["unchanged"])
    finally:
        await _action(adapter, "kubernetes_uncordon").perform(NODE, {})
    await stand.prepare()
