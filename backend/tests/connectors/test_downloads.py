import csv
import io
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.adapters.export import ExportBatch
from app.adapters.fetch import FetchColumn, FetchResult
from app.adapters.protocol import AdapterError
from app.adapters.relation import ColumnType
from app.connectors.downloads import (
    NULL_QUOTING,
    issue_export_ticket,
    read_export_ticket,
    save_csv_export,
    save_csv_page,
)
from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/connectors"


def matching_files(directory: Path, pattern: str) -> list[Path]:
    return list(directory.rglob(pattern))


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def test_csv_page_keeps_visible_order_nulls_and_unicode(tmp_path: Path) -> None:
    result = FetchResult(
        columns=[
            FetchColumn(name="id", type=ColumnType(sql="integer", category="number")),
            FetchColumn(name="name", type=ColumnType(sql="text", category="string")),
            FetchColumn(name="hidden", type=ColumnType(sql="text", category="string")),
        ],
        rows=[
            ["1", "Київ", "not exported"],
            ["2", None, "not exported"],
            ["3", "", "not exported"],
        ],
        has_more=True,
    )

    path = save_csv_page(
        home=tmp_path,
        connector_id=uuid.UUID(int=7),
        title="../Projects report",
        columns=["name", "id"],
        result=result,
        now=datetime(2026, 8, 28, 12, 30, tzinfo=UTC),
    )

    assert path.parent == tmp_path / "downloads" / str(uuid.UUID(int=7))
    assert path.name.startswith("Projects-report-20260828-123000-")
    # SQL NULL is an empty unquoted field and the empty string is a quoted one,
    # so the two survive the round trip as different values rather than both
    # arriving as "". A sentinel string could not tell them apart.
    with path.open(encoding="utf-8-sig", newline="") as source:
        assert source.read().splitlines() == [
            '"name","id"',
            '"Київ","1"',
            ',"2"',
            '"","3"',
        ]
    with path.open(encoding="utf-8-sig", newline="") as source:
        assert list(csv.reader(source, quoting=NULL_QUOTING)) == [
            ["name", "id"],
            ["Київ", "1"],
            [None, "2"],
            ["", "3"],
        ]


def test_csv_page_does_not_follow_a_downloads_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    try:
        (home / "downloads").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Creating symlinks requires Windows developer mode")
        raise
    result = FetchResult(
        columns=[FetchColumn(name="id", type=ColumnType(sql="text", category="string"))],
        rows=[["1"]],
        has_more=False,
    )

    with pytest.raises(ValueError, match="not safe"):
        save_csv_page(
            home=home,
            connector_id=uuid.UUID(int=8),
            title="page",
            columns=["id"],
            result=result,
        )

    assert list(outside.iterdir()) == []


async def test_streamed_csv_keeps_batches_out_of_the_finished_shape(
    tmp_path: Path,
) -> None:
    async def batches() -> AsyncIterator[ExportBatch]:
        yield ExportBatch(rows=[["1", "Київ"], ["2", None]])
        yield ExportBatch(rows=[["3", ""]])

    path, count = await save_csv_export(
        home=tmp_path,
        connector_id=uuid.UUID(int=9),
        title="whole table",
        columns=["id", "name"],
        batches=batches(),
    )

    assert count == 3
    assert not path.with_suffix(".csv.part").exists()
    with path.open(encoding="utf-8-sig", newline="") as source:
        assert list(csv.reader(source, quoting=NULL_QUOTING)) == [
            ["id", "name"],
            ["1", "Київ"],
            ["2", None],
            ["3", ""],
        ]


async def test_failed_stream_leaves_no_finished_or_partial_file(tmp_path: Path) -> None:
    async def batches() -> AsyncIterator[ExportBatch]:
        yield ExportBatch(rows=[["1"]])
        raise AdapterError("network", "Export failed")

    with pytest.raises(AdapterError):
        await save_csv_export(
            home=tmp_path,
            connector_id=uuid.UUID(int=10),
            title="broken",
            columns=["id"],
            batches=batches(),
        )

    assert matching_files(tmp_path, "*.csv") == []
    assert matching_files(tmp_path, "*.part") == []


def test_an_expired_export_ticket_is_not_accepted() -> None:
    ticket = issue_export_ticket(
        user_id=uuid.UUID(int=1),
        connector_id=uuid.UUID(int=2),
        filename="table.csv",
        now=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert read_export_ticket(ticket) is None


async def test_an_invalid_export_ticket_is_not_a_connector_id(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{BASE}/export-downloads/not-a-ticket")

    assert response.status_code == 404
    assert response.json()["detail"] == "Export not found"


async def test_a_download_hands_the_page_over_and_keeps_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "download source",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/downloads/page",
        headers=normal_user_token_headers,
        json={
            "node_id": "pg_catalog.pg_class",
            "limit": 2,
            "offset": 1,
            "sort": [{"column": "oid", "descending": False}],
            "title": "PostgreSQL classes",
            "columns": ["relname", "oid"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["relname", "oid"]
    assert len(rows) == 3

    # Nothing was filed away. The two used to happen at once, and a person who
    # only wanted the file found a copy of everything they had ever downloaded
    # in their own storage.
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    kept = storage.home_dir(user.id) / "downloads" / connector_id
    assert not kept.exists() or list(kept.glob("*.csv")) == []


async def test_a_kept_page_is_filed_and_not_sent_back(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db
) -> None:
    """The other half of the same choice: a copy, and no download."""
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "kept page source",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/downloads/page/keep",
        headers=normal_user_token_headers,
        json={
            "node_id": "pg_catalog.pg_class",
            "limit": 2,
            "title": "PostgreSQL classes",
            "columns": ["relname", "oid"],
        },
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["row_count"] == 2
    assert answer["filename"].endswith(".csv")
    # An address is deliberately absent: it would be an invitation to do both
    # things again.
    assert "download_url" not in answer

    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    saved = storage.home_dir(user.id) / "downloads" / connector_id / answer["filename"]
    rows = list(csv.reader(io.StringIO(saved.read_text(encoding="utf-8-sig"))))
    assert rows[0] == ["relname", "oid"]
    assert len(rows) == 3


async def test_download_refuses_a_column_outside_the_fetched_table(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "download validation",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )

    response = await client.post(
        f"{BASE}/{created.json()['id']}/downloads/page",
        headers=normal_user_token_headers,
        json={
            "node_id": "pg_catalog.pg_class",
            "limit": 2,
            "title": "classes",
            "columns": ["does_not_exist"],
        },
    )

    assert response.status_code == 422


async def test_whole_export_is_staged_outside_personal_storage_and_then_goes(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db,
    schema: str,
) -> None:
    await run(
        f"CREATE TABLE {schema}.export_route ("  # noqa: S608 -- schema is fixture-owned.
        "id integer PRIMARY KEY, label text NOT NULL)"
    )
    await run(
        f"INSERT INTO {schema}.export_route "  # noqa: S608 -- schema is fixture-owned.
        "SELECT value, 'row-' || value FROM generate_series(1, 1201) AS value"
    )
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "whole export",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/downloads/export",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.export_route",
            "title": "export route",
            "columns": ["label", "id"],
            "filters": [{"column": "id", "op": "gte", "value": "2"}],
            "sort": [{"column": "id", "descending": True}],
        },
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["row_count"] == 1200
    # Staged, but not in the caller's own files: a download keeps nothing.
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    kept = storage.home_dir(user.id) / "downloads" / connector_id
    assert not kept.exists() or list(kept.glob("*.csv")) == []

    downloaded = await client.get(answer["download_url"])
    assert downloaded.status_code == 200
    rows = list(csv.reader(io.StringIO(downloaded.content.decode("utf-8-sig"))))
    assert rows[0] == ["label", "id"]
    assert rows[1] == ["row-1201", "1201"]
    assert rows[-1] == ["row-2", "2"]

    # And the staged file goes with the ticket that was redeemed for it.
    again = await client.get(answer["download_url"])
    assert again.status_code == 404


async def test_a_kept_export_stays_in_personal_storage(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db,
    schema: str,
) -> None:
    await run(
        f"CREATE TABLE {schema}.kept_export ("  # noqa: S608 -- schema is fixture-owned.
        "id integer PRIMARY KEY, label text NOT NULL)"
    )
    await run(
        f"INSERT INTO {schema}.kept_export "  # noqa: S608 -- schema is fixture-owned.
        "SELECT value, 'row-' || value FROM generate_series(1, 5) AS value"
    )
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "kept export",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/downloads/export/keep",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.kept_export",
            "title": "kept export",
            "columns": ["label", "id"],
            "filters": [],
            "sort": [{"column": "id", "descending": False}],
        },
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["row_count"] == 5
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    saved = storage.home_dir(user.id) / "downloads" / connector_id / answer["filename"]
    assert saved.is_file()
    assert not saved.with_suffix(".csv.part").exists()
    rows = list(csv.reader(io.StringIO(saved.read_text(encoding="utf-8-sig"))))
    assert rows[0] == ["label", "id"]
    assert rows[-1] == ["row-5", "5"]


async def test_file_source_refuses_a_whole_row_export(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "page-only files",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )

    response = await client.post(
        f"{BASE}/{created.json()['id']}/downloads/export",
        headers=normal_user_token_headers,
        json={"node_id": "sample.csv", "title": "sample", "columns": ["id"]},
    )

    assert response.status_code == 501
