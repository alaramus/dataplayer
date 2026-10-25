"""An SSH server through the file explorer: `docker compose up -d sshd` (D150, D152).

Everything here is something the file source always could do — tables, SQL,
a search inside files, copies, archives —
now asked of a server. Every test works in a folder of its own below the
user's home and takes it away afterwards.
"""

import io
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from anyio import to_thread

from app.adapters.content import ContentRequest, TextContent, VideoContent
from app.adapters.explorer.copies import copies
from app.adapters.fetch import FetchRequest
from app.adapters.query import QueryLimits, QueryRequest, StatementFinished
from app.adapters.registry import AdapterContext
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.search import NodeSearchRequest
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from app.adapters.update import UpdateCellRequest
from tests.utils import services
from tests.utils.media import mp4_bytes
from tests.utils.ssh import pinned_key

LIMITS = QueryLimits(
    statement_timeout_seconds=10,
    script_timeout_seconds=30,
    max_statements=100,
    max_statement_bytes=262_144,
    max_result_rows=1_000,
    max_result_bytes=33_554_432,
    max_cell_bytes=4_194_304,
    max_run_results=20,
    max_run_bytes=67_108_864,
    max_messages=1_000,
)


class _Payload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._data.read(size)


@pytest.fixture
async def options() -> SshPassword:
    parts = urlsplit(services.SSH.require())
    server: dict[str, object] = {
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }
    pinned = await pinned_key(str(server["host"]), int(str(server["port"])))
    return SshPassword.model_validate({"auth_method": "password", **server, "host_key": pinned})


@pytest.fixture
async def store() -> AsyncGenerator[ResourceStore]:
    kept = ResourceStore(max_entries=4, max_idle_seconds=60)
    try:
        yield kept
    finally:
        await kept.aclose()


@pytest.fixture
async def adapter(options: SshPassword, store: ResourceStore) -> AsyncGenerator[SshAdapter]:
    """The explorer over a folder of this test's own, through a kept connection."""
    name = f"test-{uuid.uuid4().hex[:12]}"
    pooling = Pooling(store=store, connector_id=uuid.uuid4())
    home = SshAdapter(options, AdapterContext(home_dir=Path("."), pooling=pooling))
    await home.action("create_folder").perform(None, {"name": name})
    try:
        yield SshAdapter(
            options.model_copy(update={"path": name}),
            AdapterContext(home_dir=Path("."), pooling=pooling),
        )
    finally:
        await home.action("delete").perform(name, {})


async def _upload(adapter: SshAdapter, name: str, data: bytes, into: str | None = None) -> None:
    await adapter.action("upload").perform_with_file(
        into, {"conflict": "refuse"}, _Payload(name, data)
    )


async def test_a_csv_on_the_server_is_rows_and_a_cell_is_written_back(adapter: SshAdapter) -> None:
    await _upload(adapter, "sales.csv", b"id,region\n1,north\n2,south\n")

    page = await adapter.fetch(FetchRequest(node_id="sales.csv"))
    handle = page.row_handles[1]
    assert handle is not None
    await adapter.update_cell(
        UpdateCellRequest(node_id="sales.csv", row_handle=handle, column="region", value="east")
    )
    reread = await adapter.fetch(FetchRequest(node_id="sales.csv"))

    assert page.update_supported is True
    assert [row[1] for row in page.rows] == ["north", "south"]
    # Read again from the server, not from the copy the first read left.
    assert [row[1] for row in reread.rows] == ["north", "east"]


async def test_sql_reads_a_file_on_the_server(adapter: SshAdapter) -> None:
    await _upload(adapter, "sales.csv", b"id,amount\n1,10\n2,32\n")

    events = [
        event
        async for event in adapter.open_query(
            QueryRequest(text='SELECT sum(amount) FROM "sales.csv"', mode="read", limits=LIMITS)
        ).events()
    ]
    [finished] = [event for event in events if isinstance(event, StatementFinished)]

    assert finished.status == "succeeded", finished.diagnostic
    assert finished.result is not None
    assert finished.result.rows == [["42"]] or finished.result.rows == [[42]]


async def test_a_search_inside_files_reads_only_small_ones(adapter: SshAdapter) -> None:
    await _upload(adapter, "small.log", b"started\nupstream timeout\n")
    await _upload(adapter, "large.log", b"x" * (1024 * 1024) + b"\nupstream timeout\n")

    found = await adapter.search_contents(NodeSearchRequest(query="timeout"))

    assert [match.node.name for match in found.matches] == ["small.log"]
    assert found.notice is not None and "1 MB" in found.notice


async def test_a_file_too_large_to_read_does_not_spend_the_search(adapter: SshAdapter) -> None:
    """Skipped, it costs nothing: its 40 MB once stopped the search at 32.

    The small file is a level down, so the walk — breadth first — passes the
    large one before it whatever order the server lists them in.
    """
    await _upload(adapter, "dump.log", b"x" * (40 * 1024 * 1024))
    await adapter.action("create_folder").perform(None, {"name": "notes"})
    await _upload(adapter, "today.log", b"upstream timeout\n", into="notes")

    found = await adapter.search_contents(NodeSearchRequest(query="timeout"))

    assert [match.node.name for match in found.matches] == ["today.log"]
    assert found.complete is True


async def test_a_file_is_copied_and_moved_on_the_server(adapter: SshAdapter) -> None:
    await _upload(adapter, "notes.txt", b"one\n")
    await adapter.action("create_folder").perform(None, {"name": "kept"})

    await adapter.action("paste").perform(
        "kept", {"sources": ["notes.txt"], "mode": "copy", "conflict": "refuse"}
    )
    await adapter.action("paste").perform(
        "kept", {"sources": ["notes.txt"], "mode": "move", "conflict": "rename"}
    )

    top = sorted(
        node.name for node in await adapter.list_children(None) if node.kind != "report"
    )
    inside = sorted(node.name for node in await adapter.list_children("kept"))
    assert top == ["kept"]
    assert inside == ["notes.txt", "notes.txt (1)"]


async def test_a_file_arrives_on_the_server_in_pieces_and_is_never_staged_here(
    adapter: SshAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A transfer of gigabytes must not pass through this machine's disk (D168).
    def staged_here(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("staged on this server")

    monkeypatch.setattr(type(copies()), "scratch", staged_here)
    storage = adapter.storage
    target = storage.place("arrived.bin")

    def arrive() -> tuple[bytes, list[str]]:
        with storage.incoming(target) as arriving:
            arriving.write(b"first, ")
            arriving.write(b"second")
            arriving.publish(target)
        with storage.incoming(target) as arriving:
            arriving.write(b"never published")
        with storage.incoming(target) as arriving, pytest.raises(FileExistsError):
            arriving.write(b"a taken name")
            arriving.publish(target)
        with storage.open(target) as readable:
            data = readable.read()
        return data, sorted(entry.name for entry in storage.entries(storage.place(None)))

    data, names = await to_thread.run_sync(arrive)

    assert data == b"first, second"
    # Neither the abandoned file nor the refused one is left beside it.
    assert names == ["arrived.bin"]


async def test_a_folder_on_the_server_is_removed_only_while_it_is_empty(
    adapter: SshAdapter,
) -> None:
    # A move removes folders it emptied; one still holding something is an
    # answer, not a server that went away (D169).
    await adapter.action("create_folder").perform(None, {"name": "full"})
    await _upload(adapter, "kept.txt", b"kept", into="full")
    storage = adapter.storage

    def attempt() -> list[str]:
        with pytest.raises(OSError):
            storage.remove_empty(storage.place("full"))
        storage.remove(storage.place("full/kept.txt"))
        storage.remove_empty(storage.place("full"))
        return [entry.name for entry in storage.entries(storage.place(None))]

    assert "full" not in await to_thread.run_sync(attempt)


async def test_a_folder_is_archived_and_extracted_on_the_server(adapter: SshAdapter) -> None:
    await adapter.action("create_folder").perform(None, {"name": "reports"})
    await _upload(adapter, "q3.csv", b"a\n1\n", into="reports")

    await adapter.action("create_archive").perform(
        "reports", {"name": "bundle", "format": "zip"}
    )
    await adapter.action("delete").perform("reports", {})
    await adapter.action("extract_archive").perform("bundle.zip", {"into_folder": True})

    unpacked = await adapter.list_children("bundle/reports")
    assert [node.name for node in unpacked] == ["q3.csv"]


async def test_a_server_is_filled_with_the_sample_files(adapter: SshAdapter) -> None:
    """What an SSH server this application started is given to look at
    (D153): every file sent, the folders with what is inside them."""
    await adapter.install_sample_data()

    top = {node.name for node in await adapter.list_children(None)}
    inside = [node.name for node in await adapter.list_children("reports")]
    page = await adapter.fetch(FetchRequest(node_id="sample.csv"))

    assert {"sample.csv", "guide.md", "bundle.zip", "cities.parquet", "empty"} <= top
    assert inside == ["q3.csv"]
    assert page.rows[0][1] == "city-1"


async def test_a_file_larger_than_a_copy_is_offered_as_a_download(
    adapter: SshAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _upload(adapter, "sales.csv", b"id\n1\n2\n3\n")
    monkeypatch.setattr(copies(), "largest_bytes", 4)

    with pytest.raises(ValueError, match="download it"):
        await adapter.fetch(FetchRequest(node_id="sales.csv"))
    prepared = await adapter.action("download").download(["sales.csv"], {})  # type: ignore[attr-defined]  # Download produces one
    received = b"".join([chunk async for chunk in prepared.body])

    assert received == b"id\n1\n2\n3\n"


async def test_a_recording_larger_than_a_copy_is_played_by_range(
    adapter: SshAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a copy may hold does not bound what plays (D152): the header and
    every range a player asks for are read on the server, where they lie."""
    await _upload(adapter, "clip.mp4", mp4_bytes(timescale=600, duration=1200, moov_last=True))
    await _upload(adapter, "notes.txt", b"one\ntwo\n")
    monkeypatch.setattr(copies(), "largest_bytes", 4)
    request = ContentRequest(node_id="clip.mp4", representation="video")

    described = await adapter.read_content(request)
    stream = await adapter.open_content_stream(request)
    head = b"".join([chunk async for chunk in stream.read(0, 7)])
    text = await adapter.read_content(ContentRequest(node_id="notes.txt", representation="text"))

    assert isinstance(described, VideoContent)
    assert described.duration_seconds == pytest.approx(2.0)
    assert head[4:8] == b"ftyp"
    assert isinstance(text, TextContent)
    assert text.text == "one\ntwo\n"
