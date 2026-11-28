"""A GKE cluster read through the Container API and signed in to with the
token its Google Cloud account issues (D477, D478)."""

import base64
import copy
import json
import time
import uuid
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.cloud import AccountKind, IssuedSecret, SecretRequest
from app.adapters.cloud.requests import GoogleAccessToken
from app.adapters.kubernetes.endpoint import from_kubeconfig, gke_cluster_of
from app.adapters.kubernetes.gke import (
    GkeCluster,
    address_of,
    read_cluster,
    report_rows,
)
from app.adapters.kubernetes.options import GkeOptions, KubeconfigOptions, is_google_key
from app.adapters.kubernetes.session import KubernetesSession
from app.adapters.protocol import AdapterError

ACCOUNT = str(uuid.uuid4())
CLUSTER_NAME = "projects/demo-project-1/locations/europe-west1-b/clusters/dataplayer-test"
CA = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
CLUSTER: dict[str, Any] = {
    "name": "dataplayer-test",
    "location": "europe-west1-b",
    "status": "RUNNING",
    "endpoint": "34.38.200.79",
    "currentMasterVersion": "1.36.4-gke.2377000",
    "currentNodeVersion": "1.36.4-gke.2377000",
    "autopilot": {},
    "releaseChannel": {"channel": "REGULAR"},
    "masterAuth": {"clusterCaCertificate": base64.b64encode(CA.encode()).decode()},
    "controlPlaneEndpointsConfig": {
        "dnsEndpointConfig": {"endpoint": "gke-1.europe-west1-b.gke.goog", "allowExternalTraffic": False},
        "ipEndpointsConfig": {
            "enablePublicEndpoint": True,
            "publicEndpoint": "34.38.200.79",
            "privateEndpoint": "10.132.0.2",
        },
    },
    "nodePools": [
        {
            "name": "default-pool",
            "config": {"machineType": "e2-medium", "spot": True},
            "initialNodeCount": 1,
            "version": "1.36.4",
            "status": "RUNNING",
        },
        {
            "name": "big",
            "config": {"machineType": "n2-standard-4"},
            "autoscaling": {"enabled": True, "totalMinNodeCount": 1, "totalMaxNodeCount": 3},
        },
    ],
}


class FakeCloud:
    """Issues `token-<n>`, each living `seconds`, and records what was asked."""

    def __init__(self, seconds: float = 3600.0) -> None:
        self.asked: list[SecretRequest] = []
        self.seconds = seconds

    async def issue(
        self, account_id: uuid.UUID, kinds: tuple[AccountKind, ...], request: SecretRequest
    ) -> IssuedSecret:
        assert str(account_id) == ACCOUNT and kinds == ("gcp",)
        self.asked.append(request)
        return IssuedSecret(value=f"token-{len(self.asked)}", expires_at=time.time() + self.seconds)


def options(**changed: Any) -> GkeOptions:
    return GkeOptions.model_validate({"auth": "gke", "account": ACCOUNT, "cluster": CLUSTER_NAME, **changed})


def google(seen: list[httpx.Request], status: int = 200, body: Any = CLUSTER) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(answer)


def test_a_cluster_is_named_as_the_container_api_names_it() -> None:
    assert options().endpoint == "public"
    for wrong in ("dataplayer-test", "projects/p/clusters/x", f"{CLUSTER_NAME}/extra"):
        with pytest.raises(ValidationError):
            options(cluster=wrong)


def test_the_address_chosen_brings_its_own_trust() -> None:
    assert address_of(CLUSTER, "public") == ("34.38.200.79", CA)
    assert address_of(CLUSTER, "private") == ("10.132.0.2", CA)
    with pytest.raises(AdapterError, match="outside Google Cloud"):
        address_of(CLUSTER, "dns")
    open_dns = copy.deepcopy(CLUSTER)
    open_dns["controlPlaneEndpointsConfig"]["dnsEndpointConfig"]["allowExternalTraffic"] = True
    assert address_of(open_dns, "dns") == ("gke-1.europe-west1-b.gke.goog", None)
    closed = copy.deepcopy(CLUSTER)
    closed["controlPlaneEndpointsConfig"]["ipEndpointsConfig"]["enablePublicEndpoint"] = False
    with pytest.raises(AdapterError, match="no public address"):
        address_of(closed, "public")


def test_the_gke_report_says_what_only_gke_has() -> None:
    rows = dict(report_rows(CLUSTER))
    assert rows["Mode"] == "Standard"
    assert rows["Release channel"] == "REGULAR"
    assert rows["Node pool default-pool"] == "e2-medium · 1 per zone · Spot · 1.36.4 · RUNNING"
    assert rows["Node pool big"].startswith("n2-standard-4 · 1–3 nodes, autoscaled")
    assert "inside Google Cloud only" in rows["DNS endpoint"]


def test_a_gcloud_kubeconfig_is_told_which_cluster_to_choose() -> None:
    context = "gke_demo-project-1_europe-west1-b_dataplayer-test"
    assert gke_cluster_of(context) == CLUSTER_NAME
    assert gke_cluster_of("k3s") is None
    kubeconfig = {
        "apiVersion": "v1",
        "current-context": context,
        "contexts": [{"name": context, "context": {"cluster": "c", "user": "u"}}],
        "clusters": [{"name": "c", "cluster": {"server": "https://34.38.200.79", "certificate-authority-data": "eA=="}}],
        "users": [{"name": "u", "user": {"exec": {"command": "gke-gcloud-auth-plugin"}}}],
    }
    with pytest.raises(AdapterError, match=CLUSTER_NAME):
        from_kubeconfig(json.dumps(kubeconfig), "")


async def test_the_cluster_is_read_with_the_accounts_token() -> None:
    cloud = FakeCloud()
    seen: list[httpx.Request] = []
    found = await read_cluster(cloud, options(), google(seen))
    assert cloud.asked == [GoogleAccessToken()]
    assert str(seen[0].url) == f"https://container.googleapis.com/v1/{CLUSTER_NAME}"
    assert seen[0].headers["Authorization"] == "Bearer token-1"
    endpoint = found.endpoint
    assert (endpoint.server, endpoint.ca, endpoint.token) == ("https://34.38.200.79", CA, "token-1")


async def test_a_refusal_from_google_is_said_by_what_it_means() -> None:
    refusals = ((403, "Kubernetes Engine role"), (404, "no such cluster"), (500, "refused the request"))
    for status, words in refusals:
        with pytest.raises(AdapterError, match=words) as refused:
            await read_cluster(FakeCloud(), options(), google([], status, {"error": {"message": "secret text"}}))
        assert "secret text" not in refused.value.message
    with pytest.raises(AdapterError, match="signs in with a cloud account"):
        await read_cluster(None, options(), google([]))


async def test_a_session_renews_a_token_about_to_run_out(monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = FakeCloud(seconds=60)
    transport = google([])

    async def read(cloud_: Any, options_: GkeOptions) -> GkeCluster:
        return await read_cluster(cloud_, options_, transport)

    monkeypatch.setattr("app.adapters.kubernetes.session.read_cluster", read)
    session = KubernetesSession(options(), None, cloud=cloud)
    assert await session._read_gke() is True
    assert session.endpoint().token == "token-1"
    # A minute left is inside the five minutes the session renews within.
    assert await session._read_gke() is True
    assert session.endpoint().token == "token-2"
    assert session.gke_cluster is not None and session.gke_cluster["name"] == "dataplayer-test"
    cloud.seconds = 3600
    assert await session._read_gke() is True
    assert await session._read_gke() is False


def test_a_google_key_in_the_kubeconfig_field_is_sent_to_the_gke_way_in() -> None:
    """The key file is what people reach for with a GKE cluster (D477)."""
    key = {
        "type": "service_account",
        "project_id": "demo-project-1",
        "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-key\n-----END PRIVATE KEY-----\n",
        "client_email": "dataplayer@demo-project-1.iam.gserviceaccount.com",
    }
    with pytest.raises(ValidationError, match="service account's key, not a kubeconfig") as refused:
        KubeconfigOptions.model_validate({"auth": "kubeconfig", "kubeconfig": json.dumps(key)})
    assert "not-a-key" not in str(refused.value)
    assert is_google_key(json.dumps(key)) and not is_google_key("apiVersion: v1") and not is_google_key("{}")

