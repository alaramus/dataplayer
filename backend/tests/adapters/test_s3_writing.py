"""Writing to an S3 store, and its buckets: `docker compose up -d rustfs` (D380, D381).

Every test works in a bucket of its own, made and removed with boto3 directly.
"""

import io
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import boto3
import pytest
from anyio import to_thread
from botocore.config import Config

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import VersionChanged
from app.adapters.fetch import FetchRequest
from app.adapters.registry import AdapterContext
from app.adapters.s3 import storage as s3_storage
from app.adapters.s3.adapter import S3Adapter
from app.adapters.s3.options import S3Options
from app.adapters.s3.storage import S3Storage
from app.adapters.update import UpdateCellRequest
from tests.utils import services


class _Payload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._data.read(size)


@pytest.fixture
def server() -> S3Options:
    parts = urlsplit(services.S3.require())
    return S3Options.model_validate(
        {
            "endpoint": f"http://{parts.hostname}:{parts.port}",
            "access_key_id": parts.username,
            "secret_access_key": parts.password,
        }
    )


def _client(server: S3Options) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=server.endpoint,
        aws_access_key_id=server.access_key_id,
        aws_secret_access_key=server.secret_access_key.get_secret_value(),
        region_name=server.region_name,
        config=Config(s3={"addressing_style": "path"}),
    )


def _emptied(client: Any, bucket: str) -> None:
    for upload in client.list_multipart_uploads(Bucket=bucket).get("Uploads", []):
        client.abort_multipart_upload(
            Bucket=bucket, Key=upload["Key"], UploadId=upload["UploadId"]
        )
    for item in client.list_objects_v2(Bucket=bucket).get("Contents", []):
        client.delete_object(Bucket=bucket, Key=item["Key"])
    client.delete_bucket(Bucket=bucket)


@pytest.fixture
def bucket(server: S3Options) -> Iterator[str]:
    client = _client(server)
    name = f"test-{uuid.uuid4().hex[:12]}"
    client.create_bucket(Bucket=name)
    try:
        yield name
    finally:
        _emptied(client, name)


@pytest.fixture
def options(server: S3Options, bucket: str) -> S3Options:
    return server.model_copy(update={"bucket": bucket})


def _adapter(options: S3Options) -> S3Adapter:
    return S3Adapter(options, AdapterContext(home_dir=Path(".")))


def _keys(server: S3Options, bucket: str) -> list[str]:
    listed = _client(server).list_objects_v2(Bucket=bucket)
    return sorted(item["Key"] for item in listed.get("Contents", []))


async def _upload(
    adapter: S3Adapter, name: str, data: bytes, into: str | None = None
) -> None:
    await adapter.action("upload").perform_with_file(
        into, {"conflict": "refuse"}, _Payload(name, data)
    )


async def test_an_upload_lands_and_a_taken_name_is_refused(options: S3Options) -> None:
    adapter = _adapter(options)
    await _upload(adapter, "sales.csv", b"id,region\n1,north\n")

    with pytest.raises(ActionRefused):
        await _upload(adapter, "sales.csv", b"id,region\n2,south\n")

    page = await adapter.fetch(FetchRequest(node_id="sales.csv"))
    assert [row[1] for row in page.rows] == ["north"]


async def test_a_cell_is_written_back_as_a_whole_object(options: S3Options) -> None:
    adapter = _adapter(options)
    await _upload(adapter, "sales.csv", b"id,region\n1,north\n2,south\n")
    page = await adapter.fetch(FetchRequest(node_id="sales.csv"))
    handle = page.row_handles[1]
    assert handle is not None

    await adapter.update_cell(
        UpdateCellRequest(
            node_id="sales.csv", row_handle=handle, column="region", value="east"
        )
    )
    reread = await adapter.fetch(FetchRequest(node_id="sales.csv"))

    assert [row[1] for row in reread.rows] == ["north", "east"]


async def test_a_version_changed_under_an_edit_is_refused(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    storage = S3Storage(options)
    _client(server).put_object(Bucket=bucket, Key="notes.txt", Body=b"first")

    def edit() -> None:
        place = storage.place("notes.txt")
        read_as = storage.version(place)
        _client(server).put_object(Bucket=bucket, Key="notes.txt", Body=b"meanwhile")
        with storage.staged(place) as staged:
            staged.write_bytes(b"mine")
            storage.publish(staged, place, replace=True, expected_version=read_as)

    with pytest.raises(VersionChanged):
        await to_thread.run_sync(edit)
    body = _client(server).get_object(Bucket=bucket, Key="notes.txt")["Body"].read()
    assert body == b"meanwhile"


async def test_an_incoming_file_is_sent_in_parts(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    storage = S3Storage(options)
    piece = bytes(range(256)) * 4096  # 1 MB
    pieces = 20

    def send() -> None:
        place = storage.place("big.bin")
        with storage.incoming(place) as arriving:
            for _ in range(pieces):
                arriving.write(piece)
            arriving.publish(place)

    await to_thread.run_sync(send)

    head = _client(server).head_object(Bucket=bucket, Key="big.bin")
    assert head["ContentLength"] == len(piece) * pieces
    # Completed from parts, which an ETag of a multipart upload says.
    assert "-" in head["ETag"]


async def test_an_incoming_file_not_published_leaves_no_parts(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    storage = S3Storage(options)

    def abandon() -> None:
        place = storage.place("half.bin")
        with storage.incoming(place) as arriving:
            arriving.write(b"x" * (9 * 1024 * 1024))

    await to_thread.run_sync(abandon)

    client = _client(server)
    assert client.list_multipart_uploads(Bucket=bucket).get("Uploads", []) == []
    assert _keys(server, bucket) == []


async def test_an_incoming_file_does_not_take_a_name_that_is_taken(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    storage = S3Storage(options)
    _client(server).put_object(Bucket=bucket, Key="taken.txt", Body=b"there")

    def send() -> None:
        place = storage.place("taken.txt")
        with storage.incoming(place) as arriving:
            arriving.write(b"new")
            arriving.publish(place)

    with pytest.raises(FileExistsError):
        await to_thread.run_sync(send)


async def test_a_new_folder_is_a_marker_and_a_taken_name_is_not_made_again(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    adapter = _adapter(options)

    await adapter.action("create_folder").perform(None, {"name": "drafts"})
    # A taken name is numbered, as on every storage.
    await adapter.action("create_folder").perform(None, {"name": "drafts"})
    storage = S3Storage(options)

    def again() -> None:
        storage.make_directory(storage.place("drafts"))

    with pytest.raises(FileExistsError):
        await to_thread.run_sync(again)
    assert _keys(server, bucket) == ["drafts (1)/", "drafts/"]
    assert await adapter.list_children("drafts") == []


async def test_a_folder_is_renamed_key_by_key(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    client = _client(server)
    for key in ("old/a.txt", "old/sub/b.txt", "old/empty/"):
        client.put_object(Bucket=bucket, Key=key, Body=b"x")

    await _adapter(options).action("rename").perform("old", {"new_name": "new"})

    assert _keys(server, bucket) == ["new/a.txt", "new/empty/", "new/sub/b.txt"]


async def test_a_file_is_copied_on_the_server(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    _client(server).put_object(Bucket=bucket, Key="a.txt", Body=b"body")
    storage = S3Storage(options)

    def copied() -> None:
        storage.copy(storage.place("a.txt"), storage.place("b.txt"))

    await to_thread.run_sync(copied)

    assert _keys(server, bucket) == ["a.txt", "b.txt"]
    with pytest.raises(FileExistsError):
        await to_thread.run_sync(copied)


async def test_moving_more_objects_than_the_ceiling_is_refused(
    server: S3Options, options: S3Options, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for number in range(3):
        _client(server).put_object(Bucket=bucket, Key=f"many/{number}.txt", Body=b"x")
    monkeypatch.setattr(s3_storage, "MAX_OBJECTS", 2)

    with pytest.raises(ActionRefused) as refused:
        await _adapter(options).action("rename").perform("many", {"new_name": "moved"})

    assert refused.value.reason == "too_large"
    assert [key.split("/")[0] for key in _keys(server, bucket)] == ["many"] * 3


async def test_a_folder_is_deleted_with_everything_in_it(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    client = _client(server)
    for key in ("gone/a.txt", "gone/sub/b.txt", "kept.txt"):
        client.put_object(Bucket=bucket, Key=key, Body=b"x")

    await _adapter(options).action("delete").perform("gone", {})

    assert _keys(server, bucket) == ["kept.txt"]


async def test_an_empty_folder_is_removed_only_while_empty(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    client = _client(server)
    client.put_object(Bucket=bucket, Key="box/", Body=b"")
    client.put_object(Bucket=bucket, Key="box/item.txt", Body=b"x")
    storage = S3Storage(options)

    def emptied() -> None:
        storage.remove_empty(storage.place("box"))

    with pytest.raises(OSError):
        await to_thread.run_sync(emptied)
    client.delete_object(Bucket=bucket, Key="box/item.txt")
    await to_thread.run_sync(emptied)

    assert _keys(server, bucket) == []


async def test_an_archive_unpacks_into_the_bucket(
    server: S3Options, options: S3Options, bucket: str
) -> None:
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("data/one.csv", "a\n1\n")
        archive.writestr("readme.txt", "hello")
    adapter = _adapter(options)
    await _upload(adapter, "bundle.zip", packed.getvalue())

    await adapter.action("extract_archive").perform("bundle.zip", {"into_folder": True})

    assert _keys(server, bucket) == [
        "bundle.zip",
        # The folder made for it first, as New folder makes one.
        "bundle/",
        "bundle/data/one.csv",
        "bundle/readme.txt",
    ]


# --- buckets (D381) -------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["ab", "Upper-case", "under_score", "-start", "end.", "two..dots", "192.168.1.1"],
)
async def test_a_bucket_name_the_rules_refuse_is_refused_before_a_request(
    server: S3Options, name: str
) -> None:
    with pytest.raises(ActionRefused):
        await _adapter(server).action("create_folder").perform(None, {"name": name})


async def test_a_bucket_is_made_and_deleted_with_what_it_holds(
    server: S3Options,
) -> None:
    adapter = _adapter(server)
    name = f"made-{uuid.uuid4().hex[:12]}"

    await adapter.action("create_folder").perform(None, {"name": name})
    try:
        await _upload(adapter, "inside.txt", b"x", into=name)
        assert name in {node.name for node in await adapter.list_children(None)}

        await adapter.action("delete").perform(name, {})
    except BaseException:
        _emptied(_client(server), name)
        raise

    assert name not in {node.name for node in await adapter.list_children(None)}


async def test_a_bucket_is_not_renamed_and_holds_no_file_at_the_root(
    server: S3Options, bucket: str
) -> None:
    adapter = _adapter(server)

    with pytest.raises(ActionRefused):
        await adapter.action("rename").perform(bucket, {"new_name": f"{bucket}-x"})
    with pytest.raises(ActionRefused):
        await adapter.action("create_file").perform(None, {"name": "loose.txt"})
