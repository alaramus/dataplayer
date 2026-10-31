"""Something worth looking at, put into a ZooKeeper this server started (D302).

An empty ZooKeeper shows `/zookeeper` and nothing else. The lab is a tree the
way applications leave one: configuration as JSON, a registry of service
instances, leader election and a queue of sequential znodes, a counter that is
bytes, a lock left behind, and a branch only a digest user may read. It is
written out rather than generated, so two demonstrations look the same.
"""

import json

from kazoo.client import KazooClient
from kazoo.security import make_digest_acl

from app.adapters.zookeeper.session import ZookeeperSession
from app.core.translation import say

LAB = "/lab"

# The user the private branch is for; its password is in the guide, since the
# lab is a demonstration and the point is to try signing in.
LAB_USER = "lab"
LAB_PASSWORD = "lab"

SERVICES = (
    ("billing", 3, 8080),
    ("orders", 2, 8081),
    ("search", 4, 9200),
)

CONFIG = {
    "billing": {"currency": "EUR", "retries": 3, "features": {"invoices": True, "refunds": False}},
    "orders": {"batch_size": 500, "timeout_ms": 2000, "regions": ["north", "south"]},
    "search": {"shards": 4, "replicas": 1, "refresh": "1s"},
}

JOBS = ("resize-images", "send-invoices", "rebuild-index", "export-orders", "purge-cache")


def plan() -> list[tuple[str, bytes]]:
    """Every znode of the lab, parents first, with its data."""
    znodes: list[tuple[str, bytes]] = [
        (LAB, b"DataPlayer's ZooKeeper lab"),
        (f"{LAB}/config", b""),
    ]
    for name, settings in CONFIG.items():
        znodes.append((f"{LAB}/config/{name}", json.dumps(settings, indent=2).encode()))
    znodes.append((f"{LAB}/services", b""))
    for name, instances, port in SERVICES:
        znodes.append((f"{LAB}/services/{name}", f"{instances} instances".encode()))
        for index in range(instances):
            member = {"host": f"10.0.{len(name)}.{index + 10}", "port": port, "zone": f"z{index % 2}"}
            znodes.append((f"{LAB}/services/{name}/instance-{index}", json.dumps(member).encode()))
    znodes += [
        (f"{LAB}/election", b""),
        (f"{LAB}/locks", b""),
        (f"{LAB}/locks/orders-export", b"held by worker-2 since 2026-09-01T08:00:00Z"),
        (f"{LAB}/queue", b""),
        # A counter a program keeps as eight bytes: shown as hex, not edited.
        (f"{LAB}/counters", b""),
        (f"{LAB}/counters/requests", (1_284_220).to_bytes(8, "big")),
        (f"{LAB}/counters/errors", (37).to_bytes(8, "big")),
    ]
    return znodes


def install(client: KazooClient) -> int:
    """The lab, made again from nothing, and how many znodes it has."""
    if client.exists(LAB) is not None:
        client.add_auth("digest", f"{LAB_USER}:{LAB_PASSWORD}")
        client.delete(LAB, recursive=True)
    znodes = plan()
    for path, data in znodes:
        client.create(path, data)
    # Sequential znodes, so their names show the numbers ZooKeeper chose.
    for index in range(3):
        client.create(f"{LAB}/election/candidate-", f"worker-{index}".encode(), sequence=True)
    for job in JOBS:
        client.create(f"{LAB}/queue/job-", json.dumps({"job": job}).encode(), sequence=True)
    client.create(
        f"{LAB}/private",
        b'{"api_key": "lab-only"}',
        acl=[make_digest_acl(LAB_USER, LAB_PASSWORD, all=True)],
    )
    return len(znodes) + 3 + len(JOBS) + 1


class ZookeeperSamples:
    """Filling a ZooKeeper this server just started, never one somebody else runs (D80)."""

    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        count = await self._session.run(install)
        return say("{count} znodes under {path}", count=count, path=LAB)
