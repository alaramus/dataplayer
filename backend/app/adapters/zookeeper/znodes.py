"""The znode tree as a catalog: what a znode is called, what it says, where it lies (D298).

A znode's id is its path under the connection's root path, `/` first, which is
ZooKeeper's own name for it. Report ids never start with `/`, so the two
cannot be confused.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kazoo.client import KazooClient
from kazoo.exceptions import NoAuthError, NoNodeError

from app.adapters import jsontext
from app.adapters.catalog import ZnodeNode
from app.adapters.content import NodeRepresentation
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# Past this many children, a level of the catalog lists the first ones by name
# and the children table pages through the rest (D298).
LIST_CEILING = 1000

# Data up to this size is read while listing, to tell JSON from text; larger
# data is opened as text and read only when it is opened.
SNIFF_BYTES = 4096

# ZooKeeper's own subtree: quotas and the ensemble's configuration.
SYSTEM_ROOT = "/zookeeper"

DATA_TREE = NodeRepresentation(kind="tree", title=N_("View the data as JSON"))
DATA_TEXT = NodeRepresentation(kind="text", title=N_("Edit the data"))
CHILDREN = NodeRepresentation(kind="table", title=N_("View the children"))


def is_path(node_id: str | None) -> bool:
    return node_id is not None and node_id.startswith("/")


def checked_path(node_id: str) -> str:
    """A node id as a znode path, or ValueError for one this source did not issue."""
    if node_id == "/":
        return node_id
    if not node_id.startswith("/") or node_id.endswith("/"):
        raise ValueError(
            say('"{node_id}" is not a znode of this source', node_id=node_id)
        )
    if any(part in {"", ".", ".."} for part in node_id[1:].split("/")):
        raise ValueError(
            say('"{node_id}" is not a znode of this source', node_id=node_id)
        )
    if "\x00" in node_id:
        raise ValueError(
            say('"{node_id}" is not a znode of this source', node_id=node_id)
        )
    return node_id


def child_path(parent: str, name: str) -> str:
    return f"/{name}" if parent == "/" else f"{parent}/{name}"


def name_of(path: str) -> str:
    return path.rsplit("/", 1)[1] or "/"


def ancestors_of(path: str) -> list[str]:
    """Every path from the top down to `path`, itself included, `/` not."""
    parts = path[1:].split("/")
    return ["/" + "/".join(parts[: depth + 1]) for depth in range(len(parts))]


@dataclass(frozen=True)
class Stat:
    """What ZooKeeper says about a znode with every read, in this repository's types."""

    version: int
    child_version: int
    acl_version: int
    created_zxid: int
    modified_zxid: int
    children_zxid: int
    created_at: datetime | None
    modified_at: datetime | None
    ephemeral_owner: int
    data_length: int
    children: int


def stat_of(raw: Any) -> Stat:
    """kazoo's ZnodeStat, read once into names that say what they are."""
    return Stat(
        version=int(raw.version),
        child_version=int(raw.cversion),
        acl_version=int(raw.aversion),
        created_zxid=int(raw.czxid),
        modified_zxid=int(raw.mzxid),
        children_zxid=int(raw.pzxid),
        created_at=_moment(int(raw.ctime)),
        modified_at=_moment(int(raw.mtime)),
        ephemeral_owner=int(raw.ephemeralOwner),
        data_length=int(raw.dataLength),
        children=int(raw.numChildren),
    )


def _moment(milliseconds: int) -> datetime | None:
    """A time ZooKeeper states in milliseconds; zero is a znode it made itself."""
    if milliseconds <= 0:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


# The control characters text may hold; any other one makes the data bytes.
_TEXT_CONTROLS = frozenset("\t\n\r")


def text_of(data: bytes) -> str | None:
    """The data as text, or nothing when it is bytes.

    UTF-8 is not enough: bytes 0 to 31 decode, and a counter or a serialized
    id stored by a program is no less binary for it.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(char < " " and char not in _TEXT_CONTROLS for char in text):
        return None
    return text


def looks_like_json(data: bytes) -> bool:
    """An object or an array: a number or a string is better read as text."""
    if data.lstrip()[:1] not in (b"{", b"["):
        return False
    text = text_of(data)
    if text is None:
        return False
    try:
        jsontext.load(text)
    except ValueError:
        return False
    return True


def representations(stat: Stat, json: bool) -> list[NodeRepresentation]:
    """The data first, unless there is none and there are children (D298)."""
    data = [DATA_TREE, DATA_TEXT] if json else [DATA_TEXT]
    if stat.children == 0:
        return worded_titles(data)
    if stat.data_length == 0:
        return worded_titles([CHILDREN, *data])
    return worded_titles([*data, CHILDREN])


def znode_node(path: str, stat: Stat, json: bool) -> ZnodeNode:
    return ZnodeNode(
        id=path,
        name=name_of(path),
        has_children=stat.children > 0,
        representations=representations(stat, json),
        summarizable=True,
        data_length=stat.data_length,
        children=stat.children,
        ephemeral=stat.ephemeral_owner != 0,
        version=stat.version,
        modified_at=stat.modified_at,
        is_system=path == SYSTEM_ROOT or path.startswith(SYSTEM_ROOT + "/"),
    )


def read_level(client: KazooClient, parent: str) -> list[ZnodeNode]:
    """The first children of one znode by name, each with its stat.

    Asked all at once through kazoo's asynchronous calls: one round trip's
    wait for a level rather than one per child. A child gone between the
    listing and its stat is left out, which is what the tree now holds; one
    this session may not read is listed by name, since even its stat needs
    READ (D298).
    """
    names = sorted(client.get_children(parent))[:LIST_CEILING]
    paths = [child_path(parent, name) for name in names]
    stats = [client.exists_async(path) for path in paths]
    found: list[tuple[str, Stat | None]] = []
    for path, pending in zip(paths, stats, strict=True):
        try:
            raw = pending.get()
        except NoAuthError:
            found.append((path, None))
            continue
        if raw is not None:
            found.append((path, stat_of(raw)))
    sniffed = sniff(client, [(path, stat) for path, stat in found if stat is not None])
    return [
        unreadable_node(path)
        if stat is None
        else znode_node(path, stat, path in sniffed)
        for path, stat in found
    ]


def unreadable_node(path: str) -> ZnodeNode:
    return ZnodeNode(
        id=path,
        name=name_of(path),
        has_children=False,
        representations=[],
        readable=False,
        is_system=path == SYSTEM_ROOT or path.startswith(SYSTEM_ROOT + "/"),
    )


def sniff(client: KazooClient, znodes: list[tuple[str, Stat]]) -> set[str]:
    """Which of these hold JSON, among the ones small enough to read here."""
    small = [path for path, stat in znodes if 0 < stat.data_length <= SNIFF_BYTES]
    reads = [(path, client.get_async(path)) for path in small]
    json: set[str] = set()
    for path, pending in reads:
        try:
            data, _ = pending.get()
        except NoAuthError, NoNodeError:
            continue
        if isinstance(data, bytes) and looks_like_json(data):
            json.add(path)
    return json


def read_node(client: KazooClient, path: str) -> ZnodeNode:
    """One znode as the catalog lists it."""
    data, raw = client.get(path)
    stat = stat_of(raw)
    small = isinstance(data, bytes) and 0 < len(data) <= SNIFF_BYTES
    return znode_node(path, stat, small and looks_like_json(data))
