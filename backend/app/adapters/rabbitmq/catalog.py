"""Virtual hosts, queues, streams and exchanges as a catalog (D326).

Node ids carry the virtual host and the name percent-encoded, joined by `/`,
since a name in RabbitMQ is any text up to 255 bytes, `/` included:
`vhost:<v>`, `queues:<v>`, `streams:<v>`, `exchanges:<v>`, `queue:<v>/<n>`,
`stream:<v>/<n>` and `exchange:<v>/<n>`. A name in an id is only ever looked
up in the broker's own listing, never trusted as it is.
"""

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, unquote

from app.adapters.catalog import (
    AmqpQueueNode,
    AmqpStreamNode,
    CatalogNode,
    DirectoryNode,
    ExchangeNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.protocol import NodeNotFound
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# Past this many, a level lists the first ones by name: the largest page the
# management API serves.
LIST_CEILING = 500

MESSAGES = NodeRepresentation(kind="table", title=N_("View the messages"))
BINDINGS = NodeRepresentation(kind="table", title=N_("View the bindings"))

# The default exchange has an empty name; the API calls it this.
DEFAULT_EXCHANGE_PATH = "amq.default"

Folder = Literal["queues", "streams", "exchanges"]
Leaf = Literal["queue", "stream", "exchange"]

FOLDERS: tuple[Folder, ...] = ("queues", "streams", "exchanges")
_FOLDER_TITLES: dict[Folder, str] = {
    "queues": N_("Queues"),
    "streams": N_("Streams"),
    "exchanges": N_("Exchanges"),
}
_LEAF_OF: dict[Folder, Leaf] = {
    "queues": "queue",
    "streams": "stream",
    "exchanges": "exchange",
}

_QUEUE_COLUMNS = (
    "name,type,state,messages,messages_ready,messages_unacknowledged,consumers"
)
_EXCHANGE_COLUMNS = "name,type,durable,internal"


@dataclass(frozen=True)
class Named:
    """What a node id names: a level of a virtual host, or a thing in one."""

    prefix: str
    vhost: str
    name: str | None = None
    # A snapshot of a queue's messages, by its number (D330).
    snapshot: int | None = None


def _encode(text: str) -> str:
    return quote(text, safe="")


def parse(node_id: str) -> Named:
    """The parts of a node id of this source, or a refusal."""
    prefix, colon, rest = node_id.partition(":")
    if colon == "" or prefix not in {
        "vhost",
        "peek",
        *FOLDERS,
        *_LEAF_OF.values(),
    }:
        raise ValueError(say("Not a node of this connection"))
    if prefix == "peek":
        vhost, _, tail = rest.partition("/")
        name, slash, number = tail.rpartition("/")
        if vhost == "" or slash == "" or not number.isdigit():
            raise ValueError(say("Not a node of this connection"))
        return Named(prefix, unquote(vhost), unquote(name), int(number))
    if prefix in {"queue", "stream", "exchange"}:
        vhost, slash, name = rest.partition("/")
        if slash == "" or vhost == "":
            raise ValueError(say("Not a node of this connection"))
        return Named(prefix, unquote(vhost), unquote(name))
    if rest == "" or "/" in rest:
        raise ValueError(say("Not a node of this connection"))
    return Named(prefix, unquote(rest))


def peek_id(vhost: str, queue: str, number: int) -> str:
    return f"peek:{_encode(vhost)}/{_encode(queue)}/{number}"


def vhost_id(vhost: str) -> str:
    return f"vhost:{_encode(vhost)}"


def folder_id(folder: Folder, vhost: str) -> str:
    return f"{folder}:{_encode(vhost)}"


def leaf_id(leaf: Leaf, vhost: str, name: str) -> str:
    return f"{leaf}:{_encode(vhost)}/{_encode(name)}"


def vhost_node(vhost: str) -> DirectoryNode:
    return DirectoryNode(
        id=vhost_id(vhost), name=vhost, has_children=True, representations=[]
    )


def folder_node(folder: Folder, vhost: str) -> DirectoryNode:
    return DirectoryNode(
        id=folder_id(folder, vhost),
        name=say(_FOLDER_TITLES[folder]),
        has_children=True,
        representations=[],
    )


def folders_of(vhost: str) -> list[CatalogNode]:
    return [folder_node(folder, vhost) for folder in FOLDERS]


def exchange_title(name: str) -> str:
    return name if name else say("(default)")


def exchange_path(name: str) -> str:
    """An exchange as a segment of the API's path."""
    return segment(name or DEFAULT_EXCHANGE_PATH)


def is_system_exchange(name: str) -> bool:
    return name == "" or name.startswith("amq.")


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def queue_node(vhost: str, row: dict[str, Any]) -> CatalogNode:
    name = str(row.get("name", ""))
    queue_type = str(row.get("type") or "classic")
    if queue_type == "stream":
        return AmqpStreamNode(
            id=leaf_id("stream", vhost, name),
            name=name,
            representations=worded_titles([MESSAGES]),
            summarizable=True,
            messages=_count(row.get("messages")),
            consumers=_count(row.get("consumers")),
        )
    return AmqpQueueNode(
        id=leaf_id("queue", vhost, name),
        name=name,
        representations=worded_titles([BINDINGS]),
        summarizable=True,
        queue_type=queue_type,
        state=str(row["state"]) if row.get("state") else None,
        ready=_count(row.get("messages_ready")),
        unacknowledged=_count(row.get("messages_unacknowledged")),
        consumers=_count(row.get("consumers")),
    )


def exchange_node(vhost: str, row: dict[str, Any]) -> ExchangeNode:
    name = str(row.get("name", ""))
    return ExchangeNode(
        id=leaf_id("exchange", vhost, name),
        name=exchange_title(name),
        representations=worded_titles([BINDINGS]),
        summarizable=True,
        exchange_type=str(row.get("type") or "direct"),
        durable=bool(row.get("durable", True)),
        internal=bool(row.get("internal", False)),
        is_system=is_system_exchange(name),
    )


async def _listed(
    session: RabbitmqSession, path: str, columns: str, node_id: str
) -> list[dict[str, Any]]:
    """The first page of a listing, sorted by name, as the API pages it."""
    answer = await session.api(
        path,
        {
            "page": "1",
            "page_size": str(LIST_CEILING),
            "sort": "name",
            "columns": columns,
        },
        node_id=node_id,
    )
    items = answer.get("items") if isinstance(answer, dict) else answer
    return [item for item in items or [] if isinstance(item, dict)]


async def read_vhosts(session: RabbitmqSession) -> list[str]:
    answer = await session.api("/vhosts", {"columns": "name"})
    names = [str(row["name"]) for row in answer if isinstance(row, dict)]
    return sorted(names)


async def read_queues(
    session: RabbitmqSession, vhost: str, streams: bool
) -> list[CatalogNode]:
    rows = await _listed(
        session, f"/queues/{segment(vhost)}", _QUEUE_COLUMNS, vhost_id(vhost)
    )
    return [
        queue_node(vhost, row)
        for row in rows
        if (row.get("type") == "stream") == streams
    ]


async def read_exchanges(session: RabbitmqSession, vhost: str) -> list[CatalogNode]:
    rows = await _listed(
        session, f"/exchanges/{segment(vhost)}", _EXCHANGE_COLUMNS, vhost_id(vhost)
    )
    nodes = [exchange_node(vhost, row) for row in rows]
    # The user's own first, then the ones every virtual host is made with.
    nodes.sort(key=lambda node: (node.is_system, node.name))
    return list(nodes)


async def read_queue(
    session: RabbitmqSession, vhost: str, name: str, *, stream: bool
) -> dict[str, Any]:
    """One queue or one stream as the API describes it, or a 404 — a stream
    asked for as a queue, or the other way round, included."""
    node_id = leaf_id("stream" if stream else "queue", vhost, name)
    answer = await session.api(
        f"/queues/{segment(vhost)}/{segment(name)}", node_id=node_id
    )
    if not isinstance(answer, dict) or (answer.get("type") == "stream") != stream:
        raise NodeNotFound(node_id)
    return answer


async def read_exchange(
    session: RabbitmqSession, vhost: str, name: str
) -> dict[str, Any]:
    node_id = leaf_id("exchange", vhost, name)
    answer = await session.api(
        f"/exchanges/{segment(vhost)}/{exchange_path(name)}", node_id=node_id
    )
    if not isinstance(answer, dict):
        raise NodeNotFound(node_id)
    return answer
