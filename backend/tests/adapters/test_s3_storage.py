"""An S3 store through the file explorer: `docker compose up -d rustfs` (D379).

Every test fills a bucket of its own with boto3 directly — keys the explorer
could never write among them — and removes it afterwards.
"""

import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from anyio import to_thread
from botocore.config import Config

from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.query import QueryLimits, QueryRequest, StatementFinished
from app.adapters.registry import AdapterContext
from app.adapters.s3.adapter import S3Adapter
from app.adapters.s3.options import S3Options
from app.adapters.s3.storage import S3Storage
from tests.utils import services

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

# Keys a node id could never name again: each is in the bucket and absent from
# every listing. Keys with `.`, `..` or an empty segment are refused by the
# test server itself, as by MinIO; Amazon S3 takes them, and the same rule
# leaves them out.
UNNAMEABLE = ["C:evil.txt", "back\\slash.txt", "D:/inside.txt"]


def _parquet() -> bytes:
    sink = io.BytesIO()
    pq.write_table(pa.table({"id": [1, 2, 3], "amount": [5, 7, 30]}), sink)
    return sink.getvalue()


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


@pytest.fixture
def bucket(server: S3Options) -> Iterator[str]:
    client = boto3.client(
        "s3",
        endpoint_url=server.endpoint,
        aws_access_key_id=server.access_key_id,
        aws_secret_access_key=server.secret_access_key.get_secret_value(),
        region_name=server.region_name,
        config=Config(s3={"addressing_style": "path"}),
    )
    name = f"test-{uuid.uuid4().hex[:12]}"
    client.create_bucket(Bucket=name)
    objects = {
        "sales.csv": b"id,amount\n1,10\n2,32\n",
        "numbers.parquet": _parquet(),
        "notes.txt": b"hello from a bucket\n",
        "reports/2026/q1.csv": b"region,total\nnorth,1\n",
        "empty/": b"",
        **dict.fromkeys(UNNAMEABLE, b"x"),
    }
    for key, body in objects.items():
        client.put_object(Bucket=name, Key=key, Body=body)
    try:
        yield name
    finally:
        listed = client.list_objects_v2(Bucket=name)
        for item in listed.get("Contents", []):
            client.delete_object(Bucket=name, Key=item["Key"])
        client.delete_bucket(Bucket=name)


def _adapter(options: S3Options) -> S3Adapter:
    return S3Adapter(options, AdapterContext(home_dir=Path(".")))


@pytest.fixture
def options(server: S3Options, bucket: str) -> S3Options:
    return server.model_copy(update={"bucket": bucket})


async def test_a_bucket_lists_its_folders_and_objects(options: S3Options) -> None:
    children = await _adapter(options).list_children(None)

    assert sorted(node.name for node in children) == [
        "empty",
        "notes.txt",
        "numbers.parquet",
        "reports",
        "sales.csv",
    ]


async def test_a_key_no_id_could_name_again_is_left_out(options: S3Options) -> None:
    names = {node.name for node in await _adapter(options).list_children(None)}

    assert names.isdisjoint({"C:evil.txt", "back\\slash.txt", "D:", "inside.txt"})


@pytest.mark.parametrize(
    "node_id",
    ["../up.txt", "a/../../up.txt", "/etc/passwd", "C:evil.txt", "back\\slash.txt"],
)
async def test_an_id_out_of_the_root_is_refused(
    options: S3Options, node_id: str
) -> None:
    storage = S3Storage(options)

    with pytest.raises(ValueError):
        storage.place(node_id)
    with pytest.raises((ValueError, NodeNotFound)):
        await _adapter(options).list_children(node_id)


async def test_a_folder_is_a_marker_or_a_prefix(options: S3Options) -> None:
    storage = S3Storage(options)

    def look(node_id: str) -> object:
        return storage.entry(storage.place(node_id))

    empty, reports, year, missing = [
        await to_thread.run_sync(look, node_id)
        for node_id in ("empty", "reports", "reports/2026", "nowhere")
    ]

    assert getattr(empty, "is_directory", None) is True
    assert getattr(reports, "is_directory", None) is True
    assert getattr(year, "is_directory", None) is True
    assert missing is None
    assert await _adapter(options).list_children("empty") == []
    with pytest.raises(ValueError):
        await _adapter(options).list_children("nowhere")


async def test_an_object_is_read_at_any_offset(options: S3Options) -> None:
    storage = S3Storage(options)

    def read() -> tuple[bytes, bytes]:
        with storage.open(storage.place("notes.txt")) as stream:
            stream.seek(11)
            tail = stream.read()
            stream.seek(0)
            head = stream.read(5)
        return head, tail

    head, tail = await to_thread.run_sync(read)

    assert head == b"hello"
    assert tail == b"a bucket\n"


async def test_a_csv_in_a_bucket_is_rows(options: S3Options) -> None:
    page = await _adapter(options).fetch(FetchRequest(node_id="reports/2026/q1.csv"))

    assert page.rows == [["north", "1"]] or page.rows == [["north", 1]]


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ('SELECT sum(amount) FROM "sales.csv"', 42),
        ('SELECT sum(amount) FROM "numbers.parquet"', 42),
    ],
)
async def test_sql_reads_a_csv_and_a_parquet_file_in_the_bucket(
    options: S3Options, statement: str, expected: int
) -> None:
    events = [
        event
        async for event in _adapter(options)
        .open_query(QueryRequest(text=statement, mode="read", limits=LIMITS))
        .events()
    ]
    [finished] = [event for event in events if isinstance(event, StatementFinished)]

    assert finished.status == "succeeded", finished.diagnostic
    assert finished.result is not None
    assert [[int(value) for value in row] for row in finished.result.rows] == [
        [expected]
    ]


async def test_a_prefix_is_where_browsing_starts(options: S3Options) -> None:
    inside = options.model_copy(update={"prefix": "reports"})

    children = await _adapter(inside).list_children(None)

    assert [node.name for node in children] == ["2026"]
    assert [node.name for node in await _adapter(inside).list_children("2026")] == [
        "q1.csv"
    ]


async def test_without_a_bucket_the_root_lists_buckets(
    server: S3Options, bucket: str
) -> None:
    adapter = _adapter(server)

    buckets = {node.name for node in await adapter.list_children(None)}
    inside = {node.name for node in await adapter.list_children(f"{bucket}/reports")}

    assert bucket in buckets
    assert inside == {"2026"}


async def test_a_folder_downloads_as_a_tree(options: S3Options) -> None:
    storage = S3Storage(options)

    def fetched() -> list[str]:
        with storage.local_tree(storage.place("reports")) as tree:
            return sorted(path.relative_to(tree).as_posix() for path in tree.rglob("*"))

    assert await to_thread.run_sync(fetched) == ["2026", "2026/q1.csv"]


async def test_a_wrong_secret_is_refused_in_words_that_name_nothing(
    options: S3Options,
) -> None:
    wrong = options.model_copy(
        update={
            "secret_access_key": options.secret_access_key.__class__(
                "not-the-secret-x1"
            )
        }
    )

    result = await _adapter(wrong).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"
    for named in ("not-the-secret-x1", options.access_key_id, "127.0.0.1", "9010"):
        assert named not in result.message


async def test_an_unreachable_store_is_a_network_failure_that_names_no_address(
    server: S3Options,
) -> None:
    gone = server.model_copy(update={"endpoint": "http://127.0.0.1:1"})

    result = await _adapter(gone).check_connection()

    assert result.ok is False
    assert result.error_kind in ("network", "timeout")
    assert "127.0.0.1" not in result.message


async def test_a_bucket_that_is_not_there_is_said_so(server: S3Options) -> None:
    result = await _adapter(
        server.model_copy(update={"bucket": f"missing-{uuid.uuid4().hex[:8]}"})
    ).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"
