"""A znode's data: read as text or as a JSON tree, and written back whole (D298).

ZooKeeper holds bytes and says nothing about what they mean. UTF-8 is shown
as text and edited as text; anything else is shown as a hex dump and is not
offered for editing, since saving the text of a dump would write the dump.
"""

from kazoo.client import KazooClient

from app.adapters import jsontext
from app.adapters.content import (
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    JsonContent,
    TextContent,
    UpdateContentRequest,
    json_tree,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import (
    Stat,
    checked_path,
    looks_like_json,
    name_of,
    stat_of,
    text_of,
)
from app.core.translation import say

# The most of a binary value drawn as hex: sixteen bytes a line, so 4096 lines.
HEX_BYTES = 64 * 1024


def hex_dump(data: bytes) -> str:
    """Offset, sixteen bytes in hex, and the printable ones as they are."""
    lines: list[str] = []
    for offset in range(0, min(len(data), HEX_BYTES), 16):
        chunk = data[offset : offset + 16]
        hexes = " ".join(f"{byte:02x}" for byte in chunk)
        shown = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08x}  {hexes:<47}  |{shown}|")
    return "\n".join(lines)


def version_of(stat: Stat) -> str:
    """The version an editor sends back: which znode, and which write of it.

    The creation zxid as well as the data version, because a znode deleted and
    made again starts counting from zero, and an editor holding version 0 of
    the old one must not overwrite the new one.
    """
    return f"{stat.created_zxid}:{stat.version}"


def _read(client: KazooClient, path: str) -> tuple[bytes, Stat]:
    data, raw = client.get(path)
    return (data if isinstance(data, bytes) else b""), stat_of(raw)


class ZookeeperData:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def read_content(self, request: ContentRequest) -> ContentResult:
        path = checked_path(request.node_id)
        if request.representation not in {"text", "tree"}:
            raise ValueError(say("A znode is opened as text or as a JSON tree"))
        data, _ = await self._session.run(lambda client: _read(client, path), path)
        if request.representation == "tree":
            return _as_tree(data)
        return _as_text(data)

    async def read_editor_content(self, request: EditorContentRequest) -> EditorContent:
        path = checked_path(request.node_id)
        data, stat = await self._session.run(lambda client: _read(client, path), path)
        json = looks_like_json(data)
        text = text_of(data)
        if text is None:
            return EditorContent(
                text=hex_dump(data),
                filename=name_of(path),
                version=version_of(stat),
                writable=False,
                truncated=len(data) > HEX_BYTES,
                reason=say(
                    "The data is not UTF-8 text, so it is shown as hex and not edited here"
                ),
            )
        return EditorContent(
            text=text,
            filename=name_of(path),
            language_hint="json" if json else None,
            # Kept JSON once it is JSON: a configuration read by a program
            # breaks that program when it stops parsing.
            validation="json" if json else None,
            version=version_of(stat),
            writable=True,
        )

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        """The whole data, if the znode is still the one at the version read."""
        path = checked_path(request.node_id)
        created, _, written = request.version.partition(":")
        if not created.lstrip("-").isdigit() or not written.lstrip("-").isdigit():
            raise ContentConflict()
        data = request.text.encode("utf-8")

        def write(client: KazooClient) -> str:
            raw = client.exists(path)
            if raw is None:
                raise NodeNotFound(path)
            if stat_of(raw).created_zxid != int(created):
                raise ContentConflict()
            return version_of(stat_of(client.set(path, data, version=int(written))))

        return ContentUpdated(version=await self._session.run(write, path))


def _as_text(data: bytes) -> TextContent:
    text = text_of(data)
    if text is not None:
        return TextContent(text=text)
    return TextContent(
        text=hex_dump(data),
        truncated=len(data) > HEX_BYTES,
        notice=say("The data is not UTF-8 text, so it is shown as hex"),
    )


def _as_tree(data: bytes) -> JsonContent:
    text = text_of(data)
    if text is None:
        return JsonContent(
            source_text=hex_dump(data),
            truncated=len(data) > HEX_BYTES,
            notice=say("The data is not UTF-8 text, so it is shown as hex"),
        )
    try:
        return JsonContent(value=json_tree(jsontext.load(text)))
    except ValueError:
        return JsonContent(source_text=text, notice=say("The data is not JSON"))
