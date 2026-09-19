"""An SSH source against a real server: `docker compose up -d sshd` (D144, D145, D147).

Every test works in a folder of its own below the user's home, and takes it
away afterwards, so the tests can run in any order against a server that is
left running between runs.
"""

import io
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.content import ContentRequest
from app.adapters.credentials import SigningKey
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.registry import AdapterContext
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.ssh import keys
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshKeyAuth, SshPassword
from app.adapters.ssh.session import connect
from tests.utils import services


class _Payload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._data.read(size)


class _Keys:
    """The owner's keys, as a test hands them over."""

    def __init__(self, signing: SigningKey) -> None:
        self.signing = signing
        self.locked = False

    async def signing_key(self, key_id: uuid.UUID) -> SigningKey:
        if self.locked:
            raise AdapterError("locked", "The SSH key is locked")
        return self.signing


@pytest.fixture
def server() -> dict[str, object]:
    parts = urlsplit(services.SSH.require())
    return {
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }


@pytest.fixture
async def pinned(server: dict[str, object]) -> str:
    return (await SshAdapter.presented_server_key(server)).public_key


def _options(server: dict[str, object], pinned: str, **changes: object) -> SshPassword:
    return SshPassword.model_validate(
        {"auth_method": "password", **server, "host_key": pinned} | changes
    )


def _context(keys_at_hand: _Keys | None = None, pooling: Pooling | None = None) -> AdapterContext:
    return AdapterContext(home_dir=Path("."), keys=keys_at_hand, pooling=pooling)


@pytest.fixture
async def folder(server: dict[str, object], pinned: str) -> AsyncGenerator[str]:
    """A folder of this test's own, below the home folder."""
    name = f"test-{uuid.uuid4().hex[:12]}"
    home = SshAdapter(_options(server, pinned), _context())
    await home.action("create_folder").perform(None, {"name": name})
    try:
        yield name
    finally:
        await home.action("delete").perform(name, {})


@pytest.fixture
def adapter(server: dict[str, object], pinned: str, folder: str) -> SshAdapter:
    return SshAdapter(_options(server, pinned, path=folder), _context())


async def test_the_key_the_server_presents_is_the_key_it_is_checked_against(
    server: dict[str, object], pinned: str
) -> None:
    result = await SshAdapter(_options(server, pinned), _context()).check_connection()

    assert result.ok is True


async def test_a_server_presenting_another_key_is_refused_before_signing_in(
    server: dict[str, object],
) -> None:
    somebody_else = keys.generate("ed25519", None).facts.public_key

    result = await SshAdapter(_options(server, somebody_else), _context()).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"
    assert "different key" in result.message


async def test_a_wrong_password_is_an_authentication_answer(
    server: dict[str, object], pinned: str
) -> None:
    result = await SshAdapter(
        _options(server, pinned, password="certainly-not-it"), _context()
    ).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"
    assert "certainly-not-it" not in result.message


async def test_a_folder_is_walked_one_level_at_a_time(adapter: SshAdapter) -> None:
    await adapter.action("create_folder").perform(None, {"name": "logs"})
    await adapter.action("upload").perform_with_file(
        "logs", {"conflict": "refuse"}, _Payload("today.log", b"started\n")
    )

    top = await adapter.list_children(None)
    inside = await adapter.list_children("logs")
    path = await adapter.path_to("logs/today.log")

    assert [(node.kind, node.name) for node in top] == [("directory", "logs")]
    assert [(node.kind, node.id) for node in inside] == [("file", "logs/today.log")]
    assert [node.name for node in path] == ["logs", "today.log"]
    with pytest.raises(NodeNotFound):
        await adapter.path_to("logs/yesterday.log")


async def test_a_text_file_is_read_as_text_and_a_document_as_one(adapter: SshAdapter) -> None:
    await adapter.action("upload").perform_with_file(
        None, {"conflict": "refuse"}, _Payload("notes.md", b"# Notes\nfirst\n")
    )

    document = await adapter.read_content(
        ContentRequest(node_id="notes.md", representation="markdown")
    )
    text = await adapter.read_content(ContentRequest(node_id="notes.md", representation="text"))

    assert document.kind == "markdown"
    assert text.kind == "text"
    assert "first" in text.text  # type: ignore[union-attr]  # narrowed by the kind above


async def test_a_file_comes_down_exactly_as_the_server_holds_it(adapter: SshAdapter) -> None:
    body = bytes(range(256)) * 300
    await adapter.action("upload").perform_with_file(
        None, {"conflict": "refuse"}, _Payload("blob.bin", body)
    )

    prepared = await adapter.action("download").download(["blob.bin"], {})  # type: ignore[attr-defined]  # Download produces one
    received = b"".join([chunk async for chunk in prepared.body])

    assert prepared.metadata.size_bytes == len(body)
    assert received == body


async def test_an_upload_to_a_name_that_is_taken_is_refused_or_numbered(
    adapter: SshAdapter,
) -> None:
    upload = adapter.action("upload")
    await upload.perform_with_file(None, {"conflict": "refuse"}, _Payload("a.txt", b"1"))

    with pytest.raises(ActionRefused):
        await upload.perform_with_file(None, {"conflict": "refuse"}, _Payload("a.txt", b"2"))
    await upload.perform_with_file(None, {"conflict": "rename"}, _Payload("a.txt", b"3"))
    await upload.perform_with_file(None, {"conflict": "replace"}, _Payload("a.txt", b"4"))

    names = sorted(node.name for node in await adapter.list_children(None))
    assert names == ["a (1).txt", "a.txt"]
    replaced = await adapter.read_content(ContentRequest(node_id="a.txt", representation="text"))
    assert replaced.text == "4"  # type: ignore[union-attr]  # a text file answers text


async def test_a_node_is_renamed_and_deleted_but_the_folder_it_stands_in_is_not(
    adapter: SshAdapter,
) -> None:
    await adapter.action("create_folder").perform(None, {"name": "old"})

    await adapter.action("rename").perform("old", {"new_name": "new"})
    assert [node.name for node in await adapter.list_children(None)] == ["new"]
    await adapter.action("delete").perform("new", {})
    assert await adapter.list_children(None) == []

    with pytest.raises(ActionRefused):
        await adapter.action("delete").perform(None, {})
    offered = {action.name for action in await adapter.available(None)}
    assert "delete" not in offered and "create_folder" in offered


async def _authorized(server: dict[str, object], pinned: str) -> SigningKey:
    """A key of this test's own, added to the server's authorized_keys over SFTP."""
    made = keys.generate("ed25519", "test passphrase")
    connection = await connect(_options(server, pinned), None)
    try:
        sftp = await connection.start_sftp_client()
        if not await sftp.exists(".ssh"):
            await sftp.mkdir(".ssh")
        existing = b""
        if await sftp.exists(".ssh/authorized_keys"):
            async with sftp.open(".ssh/authorized_keys", "rb", encoding=None) as handle:
                existing = await handle.read()
        async with sftp.open(".ssh/authorized_keys", "wb", encoding=None) as handle:
            await handle.write(existing + (made.facts.public_key + "\n").encode())
    finally:
        connection.close()
    return SigningKey(private_key=made.private_key, passphrase="test passphrase")


async def test_a_key_signs_in_and_a_locked_one_stops_a_kept_connection(
    server: dict[str, object], pinned: str
) -> None:
    """Locking a key stops the source now, not when its connection closes (D147)."""
    held = _Keys(await _authorized(server, pinned))
    options = SshKeyAuth.model_validate(
        {
            "auth_method": "key",
            **{name: server[name] for name in ("host", "port", "username")},
            "key_id": str(uuid.uuid4()),
            "host_key": pinned,
        }
    )
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    adapter = SshAdapter(
        options, _context(held, Pooling(store=store, connector_id=uuid.uuid4()))
    )
    try:
        assert (await adapter.check_connection()).ok is True
        await adapter.list_children(None)
        assert await store.size() == 1

        held.locked = True
        with pytest.raises(AdapterError) as locked:
            await adapter.list_children(None)
        assert locked.value.error_kind == "locked"
    finally:
        await store.aclose()
