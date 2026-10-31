"""A znode's children read as rows, a page at a time (D298).

In ZooKeeper's order of names and no other: it keeps no index over data or
stats, so the columns can be neither sorted nor filtered, and a grid that
offered either would be offering to read every child here.
"""

from datetime import datetime
from typing import Any

from kazoo.client import KazooClient
from kazoo.exceptions import NoAuthError, NoNodeError

from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import (
    SNIFF_BYTES,
    Stat,
    checked_path,
    child_path,
    stat_of,
    text_of,
)

# Characters of data shown in a cell; the znode opens for the rest.
PREVIEW_CHARACTERS = 200

_SHAPE: tuple[tuple[str, str, TypeCategory], ...] = (
    ("name", "name", "string"),
    ("data", "data", "string"),
    ("bytes", "count", "number"),
    ("version", "version", "number"),
    ("children", "count", "number"),
    ("modified", "timestamp", "datetime"),
    ("created", "timestamp", "datetime"),
    ("ephemeral_owner", "session", "string"),
)

COLUMNS = [
    FetchColumn(name=name, type=ColumnType(sql=sql, category=category))
    for name, sql, category in _SHAPE
]


def preview(data: bytes | None, length: int) -> str | None:
    """The start of the data as text, or nothing when it was not read."""
    if data is None:
        return None if length > 0 else ""
    text = text_of(data)
    if text is None:
        return "0x" + data[:32].hex() + ("…" if len(data) > 32 else "")
    if len(text) > PREVIEW_CHARACTERS:
        return text[:PREVIEW_CHARACTERS] + "…"
    return text


def moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def session_id(owner: int) -> str | None:
    """The session an ephemeral znode belongs to, as ZooKeeper prints it."""
    return None if owner == 0 else f"0x{owner:x}"


def row(name: str, stat: Stat, data: bytes | None) -> list[str | None]:
    return [
        name,
        preview(data, stat.data_length),
        str(stat.data_length),
        str(stat.version),
        str(stat.children),
        moment(stat.modified_at),
        moment(stat.created_at),
        session_id(stat.ephemeral_owner),
    ]


def read_page(
    client: KazooClient, parent: str, offset: int, limit: int
) -> tuple[list[list[str | None]], bool]:
    """One page of children, stats and small data asked for together."""
    names = sorted(client.get_children(parent))
    page = names[offset : offset + limit]
    stats = [(name, client.exists_async(child_path(parent, name))) for name in page]
    found: list[tuple[str, Stat | None, Any]] = []
    for name, pending in stats:
        try:
            raw = pending.get()
        except NoAuthError:
            found.append((name, None, None))
            continue
        if raw is None:
            continue
        stat = stat_of(raw)
        small = 0 < stat.data_length <= SNIFF_BYTES
        found.append(
            (name, stat, client.get_async(child_path(parent, name)) if small else None)
        )
    rows: list[list[str | None]] = []
    for name, known, read in found:
        if known is None:
            # Even a stat needs READ, so all there is to show is the name.
            rows.append([name, *[None] * (len(COLUMNS) - 1)])
            continue
        data: bytes | None = None
        if read is not None:
            try:
                data = read.get()[0]
            except NoAuthError, NoNodeError:
                data = None
        rows.append(row(name, known, data))
    return rows, len(names) > offset + limit


class ZookeeperChildren:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        path = checked_path(request.node_id)
        rows, has_more = await self._session.run(
            lambda client: read_page(client, path, request.offset, request.limit), path
        )
        return FetchResult(
            columns=COLUMNS,
            rows=rows,
            has_more=has_more,
            page_commands=["download", "share"],
        )
