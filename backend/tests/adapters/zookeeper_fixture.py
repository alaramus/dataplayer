"""A subtree of known shape on the ZooKeeper server the suite talks to.

Built with kazoo directly rather than through the adapter, under a root of
its own per run, and removed whole afterwards.
"""

import json
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from kazoo.client import KazooClient
from kazoo.security import make_digest_acl
from starlette.concurrency import run_in_threadpool

from app.adapters.zookeeper.adapter import ZookeeperAdapter
from app.adapters.zookeeper.options import ZookeeperAnonymous, ZookeeperDigest
from tests.utils.services import ZOOKEEPER

CONFIG = {"name": "billing", "replicas": 3, "tags": ["a", "b"]}
BINARY = bytes(range(250, 256)) + b"\x00\x01binary"
SECRET_USER = "keeper"
SECRET_PASSWORD = "s3cret"
CHILDREN = 25


def address() -> tuple[str, int]:
    parts = urlsplit(ZOOKEEPER.require())
    return parts.hostname or "127.0.0.1", parts.port or 2181


def raw_client() -> KazooClient:
    host, port = address()
    client = KazooClient(hosts=f"{host}:{port}", timeout=5)
    client.start(timeout=5)
    return client


def with_client[T](work: Callable[[KazooClient], T]) -> T:
    client = raw_client()
    try:
        return work(client)
    finally:
        client.stop()
        client.close()


async def on_server[T](work: Callable[[KazooClient], T]) -> T:
    return await run_in_threadpool(with_client, work)


def new_root() -> str:
    return f"/dp_test_{uuid.uuid4().hex[:12]}"


def build_tree(client: KazooClient, root: str) -> None:
    """The shapes the catalog tells apart, one of each.

    - `config`: JSON data and no children;
    - `text`: plain text;
    - `binary`: bytes that are not UTF-8;
    - `services`: no data and many children, `item-00` … `item-24`;
    - `big`: text larger than the catalog reads to tell JSON from text;
    - `secret`: readable only by a digest user.
    """
    client.create(root, b"root data")
    client.create(f"{root}/config", json.dumps(CONFIG).encode())
    client.create(f"{root}/text", "plain words, ünïcode".encode())
    client.create(f"{root}/binary", BINARY)
    client.create(f"{root}/services")
    for index in range(CHILDREN):
        client.create(f"{root}/services/item-{index:02d}", f"value {index}".encode())
    client.create(f"{root}/services/item-00/deeper", b"{}")
    client.create(f"{root}/big", json.dumps({"x": "y" * 8000}).encode())
    acl = make_digest_acl(SECRET_USER, SECRET_PASSWORD, all=True)
    client.create(f"{root}/secret", b"hidden", acl=[acl])


def remove_tree(client: KazooClient, root: str) -> None:
    client.add_auth("digest", f"{SECRET_USER}:{SECRET_PASSWORD}")
    client.delete(root, recursive=True)


def options(**changes: Any) -> ZookeeperAnonymous:
    host, port = address()
    return ZookeeperAnonymous(host=host, port=port, **changes)


def digest_options(**changes: Any) -> ZookeeperDigest:
    host, port = address()
    return ZookeeperDigest(
        host=host, port=port, user=SECRET_USER, password=SECRET_PASSWORD, **changes
    )


def adapter(**changes: Any) -> ZookeeperAdapter:
    return ZookeeperAdapter(options(**changes))
