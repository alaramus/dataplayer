"""A GKE cluster, read through the Container API at every session (D477, D478).

What `gke-gcloud-auth-plugin` does for kubectl, without running it: the
connection's Google Cloud account issues an OAuth 2 access token of scope
`cloud-platform` (`GoogleAccessToken`, D449); the same token reads the
cluster — its address, CA and versions — from
`container.googleapis.com/v1/{cluster}` and signs every request to its API
server, which takes it as GKE's own identity. A token lives an hour; the
session asks again before it runs out, so an upgraded or re-addressed
cluster needs no edit either.

The Container API is REST and JSON, read with httpx: google-auth stays in
`app.adapters.cloud.gcp`.
"""

import base64
import binascii
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.cloud import CloudAccess, issue
from app.adapters.cloud.requests import GoogleAccessToken
from app.adapters.kubernetes.endpoint import Endpoint
from app.adapters.kubernetes.options import GkeOptions
from app.adapters.protocol import AdapterError
from app.core.translation import say

CONTAINER = "https://container.googleapis.com/v1"
_SECONDS = 20.0
# A token this close to its end is asked for again before a request.
RENEW_SECONDS = 300.0


@dataclass(frozen=True)
class GkeCluster:
    endpoint: Endpoint
    # The Container API's answer, for the GKE report (D478).
    cluster: dict[str, Any]
    # Seconds since the epoch; None when the account's token does not say.
    expires_at: float | None

    def stale(self) -> bool:
        return self.expires_at is not None and self.expires_at - time.time() < RENEW_SECONDS


def _pem(data: Any) -> str | None:
    """`masterAuth.clusterCaCertificate`, base64 of a PEM, as PEM."""
    try:
        text = base64.b64decode(str(data or ""), validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return text if "BEGIN CERTIFICATE" in text else None


def address_of(cluster: dict[str, Any], chosen: str) -> tuple[str, str | None]:
    """The control plane's host and the CA to trust for the address chosen.

    The DNS name carries a certificate public roots trust; the two IP
    addresses carry the cluster's own CA.
    """
    config = cluster.get("controlPlaneEndpointsConfig") or {}
    ip = config.get("ipEndpointsConfig") or {}
    private = cluster.get("privateClusterConfig") or {}
    ca = _pem((cluster.get("masterAuth") or {}).get("clusterCaCertificate"))
    if chosen == "dns":
        dns = config.get("dnsEndpointConfig") or {}
        host = str(dns.get("endpoint") or "")
        if not host:
            raise AdapterError("config", say("The cluster has no DNS name for its control plane"))
        if not dns.get("allowExternalTraffic"):
            raise AdapterError(
                "config", say("The cluster's DNS name takes no traffic from outside Google Cloud; choose its public address")
            )
        return host, None
    if chosen == "private":
        host = str(ip.get("privateEndpoint") or private.get("privateEndpoint") or "")
        if not host:
            raise AdapterError("config", say("The cluster has no private address for its control plane"))
    else:
        host = str(ip.get("publicEndpoint") or private.get("publicEndpoint") or cluster.get("endpoint") or "")
        if not host or ip.get("enablePublicEndpoint") is False:
            raise AdapterError(
                "config", say("The cluster has no public address; choose its private one through an SSH tunnel")
            )
    if ca is None:
        raise AdapterError("config", say("Google gave no CA certificate for the cluster"))
    return host, ca


async def read_cluster(
    cloud: CloudAccess | None, options: GkeOptions, transport: httpx.AsyncBaseTransport | None = None
) -> GkeCluster:
    """The cluster as Google describes it now, and how to reach and sign in to it."""
    token = await issue(cloud, options.account, ("gcp",), GoogleAccessToken())
    try:
        async with httpx.AsyncClient(timeout=_SECONDS, transport=transport) as client:
            answer = await client.get(
                f"{CONTAINER}/{options.cluster}", headers={"Authorization": f"Bearer {token.value}"}
            )
    except httpx.HTTPError:
        raise AdapterError("network", say("Google could not be reached; check the network")) from None
    if answer.status_code in (401, 403):
        raise AdapterError(
            "auth", say("Google denied reading the cluster; the account needs a Kubernetes Engine role")
        )
    if answer.status_code == 404:
        raise AdapterError("config", say("Google has no such cluster; choose it again"))
    if answer.status_code != 200:
        raise AdapterError("unknown", say("Google refused the request; test the account in Preferences"))
    try:
        cluster = answer.json()
    except ValueError:
        cluster = None
    if not isinstance(cluster, dict):
        raise AdapterError("unknown", say("Google did not answer with JSON"))
    host, ca = address_of(cluster, options.endpoint)
    shown = f"[{host}]" if ":" in host else host
    return GkeCluster(
        endpoint=Endpoint(
            server=f"https://{shown}",
            ca=ca,
            server_name=None,
            token=token.value,
            client_certificate=None,
            client_key=None,
            context=str(cluster.get("name") or "") or None,
        ),
        cluster=cluster,
        expires_at=token.expires_at,
    )


def _pool_line(pool: dict[str, Any]) -> str:
    config = pool.get("config") or {}
    scaling = pool.get("autoscaling") or {}
    if scaling.get("enabled"):
        low = scaling.get("totalMinNodeCount", scaling.get("minNodeCount", 0))
        high = scaling.get("totalMaxNodeCount", scaling.get("maxNodeCount", 0))
        size = f"{low}–{high} nodes, autoscaled"
    else:
        size = f"{pool.get('initialNodeCount', 0)} per zone"
    parts = [
        str(config.get("machineType") or "—"),
        size,
        "Spot" if config.get("spot") else ("preemptible" if config.get("preemptible") else ""),
        str(pool.get("version") or ""),
        str(pool.get("status") or ""),
    ]
    return " · ".join(part for part in parts if part)


def report_rows(cluster: dict[str, Any]) -> list[tuple[str, str]]:
    """What only GKE says of a cluster, from the Container API's answer (D478)."""
    config = cluster.get("controlPlaneEndpointsConfig") or {}
    ip = config.get("ipEndpointsConfig") or {}
    private = cluster.get("privateClusterConfig") or {}
    dns = config.get("dnsEndpointConfig") or {}
    identity = (cluster.get("workloadIdentityConfig") or {}).get("workloadPool")
    autopilot = (cluster.get("autopilot") or {}).get("enabled")
    rows: list[tuple[str, str]] = [
        ("Name", str(cluster.get("name") or "—")),
        ("Location", str(cluster.get("location") or "—")),
        ("Status", str(cluster.get("status") or "—")),
        ("Mode", "Autopilot" if autopilot else "Standard"),
        ("Release channel", str((cluster.get("releaseChannel") or {}).get("channel") or "none")),
        ("Control plane version", str(cluster.get("currentMasterVersion") or "—")),
        ("Node version", str(cluster.get("currentNodeVersion") or "—")),
        ("Public endpoint", str(ip.get("publicEndpoint") or private.get("publicEndpoint") or cluster.get("endpoint") or "—")),
        ("Private endpoint", str(ip.get("privateEndpoint") or private.get("privateEndpoint") or "—")),
        (
            "DNS endpoint",
            f"{dns['endpoint']} ({'reachable from outside' if dns.get('allowExternalTraffic') else 'inside Google Cloud only'})"
            if dns.get("endpoint")
            else "—",
        ),
        ("Workload Identity", str(identity) if identity else "off"),
        ("Network", " / ".join(str(part) for part in (cluster.get("network"), cluster.get("subnetwork")) if part) or "—"),
    ]
    for pool in cluster.get("nodePools") or []:
        if isinstance(pool, dict) and pool.get("name"):
            rows.append((f"Node pool {pool['name']}", _pool_line(pool)))
    return rows
