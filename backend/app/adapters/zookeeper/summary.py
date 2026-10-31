"""What a znode is: its stat and its ACL, beside its data (D298)."""

from typing import Any

from kazoo.client import KazooClient

from app.adapters.summary import (
    NodeSummary,
    ZnodeAccess,
    ZnodeContents,
    ZnodePermission,
)
from app.adapters.zookeeper.children import session_id
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import (
    SNIFF_BYTES,
    Stat,
    checked_path,
    looks_like_json,
    name_of,
    representations,
    stat_of,
)

# ZooKeeper's permission bits, in the order its tools print them.
PERMISSIONS: tuple[tuple[int, ZnodePermission], ...] = (
    (1, "read"),
    (2, "write"),
    (4, "create"),
    (8, "delete"),
    (16, "admin"),
)


def access_of(entry: Any) -> ZnodeAccess:
    perms = int(entry.perms)
    return ZnodeAccess(
        scheme=str(entry.id.scheme),
        id=str(entry.id.id),
        permissions=[name for bit, name in PERMISSIONS if perms & bit],
    )


def _read(client: KazooClient, path: str) -> tuple[bytes, Stat, list[ZnodeAccess]]:
    data, raw = client.get(path)
    acl, _ = client.get_acls(path)
    return (
        (data if isinstance(data, bytes) else b""),
        stat_of(raw),
        [access_of(e) for e in acl],
    )


class ZookeeperSummaries:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def node_summary(self, node_id: str) -> NodeSummary:
        path = checked_path(node_id)
        data, stat, acl = await self._session.run(
            lambda client: _read(client, path), path
        )
        json = len(data) <= SNIFF_BYTES and looks_like_json(data)
        return NodeSummary(
            node_id=path,
            name=name_of(path),
            kind="znode",
            representations=representations(stat, json),
            size_bytes=stat.data_length,
            modified_at=stat.modified_at,
            created_at=stat.created_at,
            contents=ZnodeContents(
                version=stat.version,
                child_version=stat.child_version,
                acl_version=stat.acl_version,
                created_zxid=f"0x{stat.created_zxid:x}",
                modified_zxid=f"0x{stat.modified_zxid:x}",
                children_zxid=f"0x{stat.children_zxid:x}",
                children=stat.children,
                ephemeral_owner=session_id(stat.ephemeral_owner),
                acl=acl,
            ),
        )
