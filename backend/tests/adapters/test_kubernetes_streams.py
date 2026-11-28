"""A terminal in a pod, its logs told as they grow, and a port of the cluster
carried for another connection (D472–D474)."""

import asyncio
from typing import Any

import pytest

from app.adapters.changes import Changed
from app.adapters.kubernetes.adapter import KubernetesAdapter
from app.adapters.kubernetes.catalog import object_id, page_id
from app.adapters.kubernetes.connect import declared_in, environment, service_port
from app.adapters.kubernetes.forward import pod_port, reach_of, service_target
from app.adapters.kubernetes.terminal import exit_code
from app.adapters.kubernetes.watch import logs_followed
from app.adapters.protocol import AdapterError
from app.adapters.terminal import TerminalSize
from tests.adapters import kubernetes_stand as stand

SIZE = TerminalSize(cols=80, rows=24)


def test_a_tunnelled_host_names_a_pod_or_a_service() -> None:
    assert reach_of("postgres-0.db.pod").name == "postgres-0"
    service = reach_of("kube-dns.kube-system.svc.cluster.local")
    assert (service.kind, service.namespace, service.name) == ("svc", "kube-system", "kube-dns")
    for host in ("db.example.com", "a.pod", "UPPER_case.ns.svc", "x.ns.node"):
        with pytest.raises(AdapterError, match="pod or"):
            reach_of(host)


def test_a_service_port_is_followed_to_the_pod() -> None:
    service = {"spec": {"ports": [{"port": 5432, "targetPort": "pg"}, {"port": 53, "protocol": "UDP"}]}}
    pod = {"spec": {"containers": [{"ports": [{"name": "pg", "containerPort": 5433}]}]}}
    assert pod_port(pod, service_target(service, 5432)) == 5433
    with pytest.raises(AdapterError, match="TCP port 53"):
        service_target(service, 53)
    assert service_port(service, pod, 5433) == 5432
    assert service_port(service, pod, 9999) is None


def test_a_draft_reads_literal_values_only() -> None:
    container = {
        "image": "docker.io/library/postgres:18",
        "env": [
            {"name": "POSTGRES_PASSWORD", "value": "secret"},
            {"name": "POSTGRES_USER", "valueFrom": {"secretKeyRef": {"name": "db", "key": "user"}}},
            {"name": "POSTGRES_PASSWORD", "value": "second"},
        ],
    }
    assert environment(container) == {"POSTGRES_PASSWORD": "secret"}
    declared = declared_in({"spec": {"containers": [{"image": "busybox"}, container]}})
    assert declared is not None and declared[0].name == "postgres"
    assert declared_in({"spec": {"containers": [{"image": "busybox:1.37"}]}}) is None


def test_an_exec_ends_with_the_code_its_status_carries() -> None:
    assert exit_code({"status": "Success"}) == 0
    failed = {"status": "Failure", "reason": "NonZeroExitCode", "details": {"causes": [{"reason": "ExitCode", "message": "3"}]}}
    assert exit_code(failed) == 3
    assert exit_code({"status": "Failure", "message": "OCI runtime exec failed"}) is None


def test_only_a_pods_logs_page_is_followed() -> None:
    pod = object_id(stand.NAMESPACE, "", "pods", "web-1")
    logs = page_id(pod, "logs", "echo")
    assert logs_followed([None, pod, page_id(pod, "events"), logs, "nonsense"]) == {
        logs: (stand.NAMESPACE, "web-1", "echo")
    }


@pytest.fixture(scope="module")
async def adapter() -> KubernetesAdapter:
    await stand.prepare()
    return KubernetesAdapter(stand.admin_options(), connector_id="00000000-0000-4000-8000-000000000001")


async def _pod(adapter: KubernetesAdapter, namespace: str = stand.NAMESPACE, labels: str = "app=web") -> str:
    found = await adapter._session.get(f"/api/v1/namespaces/{namespace}/pods", {"labelSelector": labels})
    running = [one for one in found["items"] if (one.get("status") or {}).get("phase") == "Running"]
    return str(running[0]["metadata"]["name"])


async def _read_all(terminal: Any) -> bytes:
    seen = b""
    async with asyncio.timeout(20):
        while chunk := await terminal.read():
            seen += chunk
    return seen


async def test_a_terminal_runs_a_shell_in_the_pods_container(adapter: KubernetesAdapter) -> None:
    node = object_id(stand.NAMESPACE, "", "pods", await _pod(adapter))
    names = [one.name for one in await adapter.available(node)]
    assert "kubernetes_terminal" in names
    terminal_action: Any = adapter.action("kubernetes_terminal")
    assert (await terminal_action.field_hints(node)).values == {"container": "echo"}

    terminal = await terminal_action.open_terminal(node, {"shell": "/bin/sh"}, SIZE)
    try:
        await terminal.write(b"echo hello-$((40+2)); exit 3\n")
        assert b"hello-42" in await _read_all(terminal)
        assert await terminal.exit_status() == 3
    finally:
        await terminal.close()

    missing = await terminal_action.open_terminal(node, {"shell": "/bin/bash"}, SIZE)
    try:
        assert b"There is no /bin/bash" in await _read_all(missing)
    finally:
        await missing.close()


async def test_a_logs_page_is_told_when_the_container_prints(adapter: KubernetesAdapter) -> None:
    logs = page_id(object_id(stand.NAMESPACE, "", "pods", await _pod(adapter)), "logs", "echo")
    told: asyncio.Queue[Changed] = asyncio.Queue()
    watch = await adapter.watch_changes(told.put_nowait)
    try:
        await watch.follow([None, logs])
        async with asyncio.timeout(15):
            changed = await told.get()
        assert changed.nodes == frozenset({logs})
    finally:
        await watch.close()


async def _http_get(address: tuple[str, int], path: str) -> bytes:
    reader, writer = await asyncio.open_connection(*address)
    try:
        writer.write(f"GET {path} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
        await writer.drain()
        async with asyncio.timeout(15):
            return await reader.read(200)
    finally:
        writer.close()


async def test_a_port_of_a_pod_and_of_a_service_is_carried(adapter: KubernetesAdapter) -> None:
    dns = await _pod(adapter, "kube-system", "k8s-app=kube-dns")
    through_pod = await adapter.forward(f"{dns}.kube-system.pod", 8080)
    assert (await _http_get(through_pod, "/health")).startswith(b"HTTP/1.0 200")
    # The same target is the same listener.
    assert await adapter.forward(f"{dns}.kube-system.pod", 8080) == through_pod
    through_service = await adapter.forward("kube-dns.kube-system.svc", 9153)
    assert (await _http_get(through_service, "/metrics")).startswith(b"HTTP/1.")
    with pytest.raises(AdapterError, match="not running|no such"):
        await adapter.forward(f"nothing.{stand.NAMESPACE}.pod", 80)


async def test_a_pod_without_a_database_is_not_offered_as_a_connection(adapter: KubernetesAdapter) -> None:
    node = object_id(stand.NAMESPACE, "", "pods", await _pod(adapter))
    assert "kubernetes_open_as_connection" not in [one.name for one in await adapter.available(node)]
    listed = await adapter.list_children(f"ns/{stand.NAMESPACE}/k/core/pods")
    # A row cannot read the image, so it names the action; the node itself does not.
    assert "kubernetes_open_as_connection" in (getattr(listed[0], "actions", None) or [])
