"""The k3s cluster the Kubernetes source tests run against (D463).

Needs `docker compose up -d k3s`. What the tests read is applied here through
the API, as `kubectl apply --server-side` would apply kubernetes_stand.yaml,
so the stand needs nothing prepared by hand; a service account that may only
view `dp-test` gives a token for refusals.
"""

import asyncio
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr

from app.adapters.kubernetes.endpoint import from_kubeconfig
from app.adapters.kubernetes.options import KubeconfigOptions, TokenOptions
from app.adapters.kubernetes.session import KubernetesSession
from tests.utils import services

NAMESPACE = "dp-test"
READER = "dp-reader"
_MANIFEST = Path(__file__).with_name("kubernetes_stand.yaml")
# Where each kind of the manifest is applied, by kind.
_PATHS = {
    "Namespace": "/api/v1/namespaces/{name}",
    "Deployment": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
    "Service": "/api/v1/namespaces/{namespace}/services/{name}",
    "ConfigMap": "/api/v1/namespaces/{namespace}/configmaps/{name}",
    "Secret": "/api/v1/namespaces/{namespace}/secrets/{name}",
    "ServiceAccount": "/api/v1/namespaces/{namespace}/serviceaccounts/{name}",
    "RoleBinding": "/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/rolebindings/{name}",
}
_READER = [
    {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": READER, "namespace": NAMESPACE}},
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": READER, "namespace": NAMESPACE},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"},
        "subjects": [{"kind": "ServiceAccount", "name": READER, "namespace": NAMESPACE}],
    },
]


def kubeconfig() -> str:
    services.K3S.require()
    return services.k3s_kubeconfig().read_text()


def admin_options() -> KubeconfigOptions:
    return KubeconfigOptions(kubeconfig=SecretStr(kubeconfig()))


async def _apply(session: KubernetesSession, document: dict[str, Any]) -> None:
    metadata = document["metadata"]
    path = _PATHS[document["kind"]].format(name=metadata["name"], namespace=metadata.get("namespace", ""))
    client = await session.client()
    answer = await client.patch(
        path,
        params={"fieldManager": "dataplayer-tests", "force": "true"},
        json=document,
        headers={"Content-Type": "application/apply-patch+yaml"},
    )
    assert answer.status_code in (200, 201), (path, answer.status_code)


async def prepare() -> None:
    """The manifest and the reader applied, and the deployment ready."""
    session = KubernetesSession(admin_options(), None)
    try:
        documents = [one for one in yaml.safe_load_all(_MANIFEST.read_text()) if one]
        for document in [*documents, *_READER]:
            await _apply(session, document)
        client = await session.client()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            status = (await client.get(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/web")).json()["status"]
            if status.get("readyReplicas") == 2:
                return
            await asyncio.sleep(2)
        raise AssertionError("The stand's deployment did not become ready")
    finally:
        await session.close()


async def reader_options() -> TokenOptions:
    """A token of a service account that may only view `dp-test`."""
    endpoint = from_kubeconfig(kubeconfig(), "")
    session = KubernetesSession(admin_options(), None)
    try:
        client = await session.client()
        answer = await client.post(
            f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts/{READER}/token",
            json={"apiVersion": "authentication.k8s.io/v1", "kind": "TokenRequest", "spec": {"expirationSeconds": 3600}},
        )
        token = answer.json()["status"]["token"]
    finally:
        await session.close()
    return TokenOptions(
        server=endpoint.server,
        ca_certificate=endpoint.ca or "",
        token=SecretStr(token),
        namespace=NAMESPACE,
    )
