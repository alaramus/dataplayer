"""An FTP server through the file explorer (D384, D385).

The server is pyftpdlib in this process, over a folder of the test's own
(`tests/utils/ftp.py`). Every test runs twice: once against a server that
speaks MLSD and once against one that answers LIST alone, as vsftpd does.
"""

import io
import os
import socket
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from anyio import to_thread
from pydantic import SecretStr

from app.adapters.explorer.copies import copies
from app.adapters.explorer.storage import VersionChanged
from app.adapters.fetch import FetchRequest
from app.adapters.ftp.adapter import FtpAdapter
from app.adapters.ftp.client import pool_for
from app.adapters.ftp.options import FtpAnonymous, FtpPassword
from app.adapters.query import QueryLimits, QueryRequest, StatementFinished
from app.adapters.registry import AdapterContext
from app.adapters.search import NodeSearchRequest
from app.adapters.update import UpdateCellRequest
from tests.utils.ftp import PASSWORD, USER, Listing, ftp_server

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
def root(tmp_path: Path) -> Path:
    served = tmp_path / "served"
    (served / "reports" / "2026").mkdir(parents=True)
    (served / "sales.csv").write_bytes(b"id,amount\n1,10\n2,32\n")
    (served / "notes.txt").write_bytes(b"hello from a server\n")
    (served / ".hidden").write_bytes(b"dot\n")
    (served / "reports" / "2026" / "q1.csv").write_bytes(b"region,total\nnorth,1\n")
    (served / "with space.txt").write_bytes(b"s\n")
    return served


@pytest.fixture(params=["mlsd", "list"])
def server(request: pytest.FixtureRequest, root: Path) -> Iterator[int]:
    listing: Listing = request.param
    with ftp_server(root, listing) as port:
        yield port


@pytest.fixture
def options(server: int) -> FtpPassword:
    return FtpPassword.model_validate(
        {
            "auth_method": "password",
            "host": "127.0.0.1",
            "port": server,
            "security": "none",
            "username": USER,
            "password": PASSWORD,
        }
    )


@pytest.fixture
async def adapter(options: FtpPassword) -> AsyncGenerator[FtpAdapter]:
    yield FtpAdapter(options, AdapterContext(home_dir=Path(".")))


def _leftovers(root: Path) -> list[str]:
    """What a write staged on the server and did not take away."""
    return [path.name for path in root.iterdir() if path.name.startswith(".dataplayer")]


async def _upload(
    adapter: FtpAdapter, name: str, data: bytes, into: str | None = None
) -> None:
    await adapter.action("upload").perform_with_file(
        into, {"conflict": "refuse"}, _Payload(name, data)
    )


async def test_the_connection_is_checked(adapter: FtpAdapter) -> None:
    result = await adapter.check_connection()

    assert result.ok is True, result.message


async def test_a_wrong_password_is_an_auth_failure(options: FtpPassword) -> None:
    wrong = options.model_copy(update={"password": SecretStr("nope")})

    result = await FtpAdapter(
        wrong, AdapterContext(home_dir=Path("."))
    ).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")


async def test_an_anonymous_user_is_let_in(server: int) -> None:
    options = FtpAnonymous.model_validate(
        {
            "auth_method": "anonymous",
            "host": "127.0.0.1",
            "port": server,
            "security": "none",
        }
    )

    names = {
        node.name
        for node in await FtpAdapter(
            options, AdapterContext(home_dir=Path("."))
        ).list_children(None)
    }

    assert "sales.csv" in names


async def test_a_missing_folder_fails_the_check(options: FtpPassword) -> None:
    elsewhere = options.model_copy(update={"path": "nowhere"})

    result = await FtpAdapter(
        elsewhere, AdapterContext(home_dir=Path("."))
    ).check_connection()

    assert (result.ok, result.error_kind) == (False, "config")


async def test_a_folder_lists_its_folders_and_files(adapter: FtpAdapter) -> None:
    children = await adapter.list_children(None)
    inner = await adapter.list_children("reports/2026")

    assert sorted(node.name for node in children) == [
        ".hidden",
        "notes.txt",
        "reports",
        "sales.csv",
        "with space.txt",
    ]
    assert {node.name: node.kind for node in children}["reports"] == "directory"
    assert [node.name for node in inner] == ["q1.csv"]


async def test_browsing_starts_in_the_folder_of_the_options(
    options: FtpPassword,
) -> None:
    inside = FtpAdapter(
        options.model_copy(update={"path": "reports"}),
        AdapterContext(home_dir=Path(".")),
    )

    assert [node.name for node in await inside.list_children(None)] == ["2026"]


async def test_a_file_is_read_at_any_offset(adapter: FtpAdapter) -> None:
    storage = adapter.storage

    def read() -> tuple[bytes, bytes, bytes]:
        with storage.open(storage.place("notes.txt")) as stream:
            stream.seek(11)
            tail = stream.read()
            stream.seek(0)
            head = stream.read(5)
            stream.seek(6)
            middle = stream.read(4)
        return head, middle, tail

    head, middle, tail = await to_thread.run_sync(read)

    assert (head, middle, tail) == (b"hello", b"from", b"a server\n")


async def test_a_csv_is_rows_and_a_cell_is_written_back(
    adapter: FtpAdapter, root: Path
) -> None:
    page = await adapter.fetch(FetchRequest(node_id="sales.csv"))
    handle = page.row_handles[1]
    assert handle is not None
    await adapter.update_cell(
        UpdateCellRequest(
            node_id="sales.csv", row_handle=handle, column="amount", value="33"
        )
    )
    reread = await adapter.fetch(FetchRequest(node_id="sales.csv"))

    assert [row[1] for row in page.rows] == ["10", "32"]
    assert [row[1] for row in reread.rows] == ["10", "33"]
    assert (root / "sales.csv").read_bytes() == b"id,amount\n1,10\n2,33\n"
    # Nothing staged beside it is left on the server.
    assert _leftovers(root) == []


async def test_a_version_changed_under_an_edit_is_refused(
    adapter: FtpAdapter, root: Path
) -> None:
    storage = adapter.storage
    place = storage.place("notes.txt")

    def edit() -> None:
        version = storage.version(place)
        (root / "notes.txt").write_bytes(b"changed by somebody else, and longer\n")
        with storage.staged(place) as staged:
            staged.write_bytes(b"mine\n")
            storage.publish(staged, place, replace=True, expected_version=version)

    with pytest.raises(VersionChanged):
        await to_thread.run_sync(edit)
    assert (
        root / "notes.txt"
    ).read_bytes() == b"changed by somebody else, and longer\n"


async def test_sql_reads_a_file_on_the_server(adapter: FtpAdapter) -> None:
    events = [
        event
        async for event in adapter.open_query(
            QueryRequest(
                text='SELECT sum(amount) FROM "sales.csv"', mode="read", limits=LIMITS
            )
        ).events()
    ]
    [finished] = [event for event in events if isinstance(event, StatementFinished)]

    assert finished.status == "succeeded", finished.diagnostic
    assert finished.result is not None
    assert finished.result.rows in ([["42"]], [[42]])


async def test_a_search_inside_files_finds_the_text(adapter: FtpAdapter) -> None:
    found = await adapter.search_contents(NodeSearchRequest(query="north"))

    assert [match.node.name for match in found.matches] == ["q1.csv"]


async def test_an_upload_lands_and_a_taken_name_is_refused(
    adapter: FtpAdapter, root: Path
) -> None:
    await _upload(adapter, "new.txt", b"fresh\n", into="reports")

    with pytest.raises(Exception):  # noqa: B017 - the refusal's type is the action layer's
        await _upload(adapter, "new.txt", b"again\n", into="reports")
    assert (root / "reports" / "new.txt").read_bytes() == b"fresh\n"


async def test_folders_and_files_are_made_renamed_copied_and_deleted(
    adapter: FtpAdapter, root: Path
) -> None:
    await adapter.action("create_folder").perform(None, {"name": "kept"})
    await adapter.action("paste").perform(
        "kept",
        {"sources": ["notes.txt", "reports"], "mode": "copy", "conflict": "refuse"},
    )
    await adapter.action("paste").perform(
        "kept", {"sources": ["sales.csv"], "mode": "move", "conflict": "refuse"}
    )
    await adapter.action("rename").perform(
        "kept/notes.txt", {"new_name": "renamed.txt"}
    )

    assert sorted(path.name for path in (root / "kept").iterdir()) == [
        "renamed.txt",
        "reports",
        "sales.csv",
    ]
    assert (
        root / "kept" / "reports" / "2026" / "q1.csv"
    ).read_bytes() == b"region,total\nnorth,1\n"
    assert not (root / "sales.csv").exists()

    await adapter.action("delete").perform("kept", {})

    assert not (root / "kept").exists()


async def test_a_file_arrives_in_pieces_and_is_never_staged_here(
    adapter: FtpAdapter, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def staged_here(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("staged on this server")

    monkeypatch.setattr(type(copies()), "scratch", staged_here)
    storage = adapter.storage
    target = storage.place("arrived.bin")

    def arrive() -> None:
        with storage.incoming(target) as arriving:
            arriving.write(b"first, ")
            arriving.write(b"second")
            arriving.publish(target)
        with storage.incoming(target) as arriving:
            arriving.write(b"never published")
        with storage.incoming(target) as arriving, pytest.raises(FileExistsError):
            arriving.write(b"a taken name")
            arriving.publish(target)

    await to_thread.run_sync(arrive)

    assert (root / "arrived.bin").read_bytes() == b"first, second"
    assert _leftovers(root) == []


async def test_a_folder_is_removed_only_while_it_is_empty(
    adapter: FtpAdapter, root: Path
) -> None:
    storage = adapter.storage

    def attempt() -> None:
        with pytest.raises(OSError):
            storage.remove_empty(storage.place("reports"))
        storage.remove(storage.place("reports/2026"))
        storage.remove_empty(storage.place("reports"))

    await to_thread.run_sync(attempt)

    assert not (root / "reports").exists()


async def test_a_folder_is_archived_and_extracted_on_the_server(
    adapter: FtpAdapter,
) -> None:
    await adapter.action("create_archive").perform(
        "reports", {"name": "bundle", "format": "zip"}
    )
    await adapter.action("delete").perform("reports", {})
    await adapter.action("extract_archive").perform("bundle.zip", {"into_folder": True})

    unpacked = await adapter.list_children("bundle/reports/2026")
    assert [node.name for node in unpacked] == ["q1.csv"]


@pytest.mark.skipif(
    os.name != "posix", reason="Windows refuses a symbolic link without privileges"
)
async def test_a_link_is_described_by_what_it_points_at(
    adapter: FtpAdapter, root: Path
) -> None:
    (root / "latest").symlink_to(root / "reports" / "2026", target_is_directory=True)

    children = {node.name: node.kind for node in await adapter.list_children(None)}

    assert children["latest"] == "directory"
    assert [node.name for node in await adapter.list_children("latest")] == ["q1.csv"]


async def test_a_kept_connection_the_server_closed_is_replaced(
    adapter: FtpAdapter, options: FtpPassword
) -> None:
    """A server closes an idle connection and says so only to the next
    command; that command is tried again on a new connection (D384)."""
    pool = pool_for(options)

    def drop_one() -> None:
        lent = pool.take()
        pool.give(lent)
        lent.ftp.sock.shutdown(socket.SHUT_RDWR)

    await adapter.list_children(None)
    await to_thread.run_sync(drop_one)

    assert "sales.csv" in {node.name for node in await adapter.list_children(None)}


@pytest.mark.parametrize("verify", [False, True])
async def test_explicit_tls_carries_both_channels(root: Path, verify: bool) -> None:
    """The control channel and every data channel are encrypted, the second
    resuming the first's session; a certificate of the server's own making is
    refused unless its check is switched off (D384, D386)."""
    with ftp_server(root, "list", tls=True) as port:
        options = FtpPassword.model_validate(
            {
                "auth_method": "password",
                "host": "127.0.0.1",
                "port": port,
                "security": "explicit",
                "verify_tls": verify,
                "username": USER,
                "password": PASSWORD,
            }
        )
        adapter = FtpAdapter(options, AdapterContext(home_dir=Path(".")))

        result = await adapter.check_connection()
        if verify:
            assert (result.ok, result.error_kind) == (False, "config")
            return
        assert result.ok is True, result.message
        await _upload(adapter, "sent.txt", b"over tls")
        page = await adapter.fetch(FetchRequest(node_id="sales.csv"))

    assert [row[1] for row in page.rows] == ["10", "32"]
    assert (root / "sent.txt").read_bytes() == b"over tls"


async def test_a_plain_server_is_not_signed_into_without_tls_by_default(
    options: FtpPassword,
) -> None:
    explicit = options.model_copy(update={"security": "explicit"})

    result = await FtpAdapter(
        explicit, AdapterContext(home_dir=Path("."))
    ).check_connection()

    assert (result.ok, result.error_kind) == (False, "config")
