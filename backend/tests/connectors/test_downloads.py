import csv
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.adapters.fetch import FetchColumn, FetchResult
from app.adapters.relation import ColumnType
from app.connectors.downloads import NULL_TEXT, save_csv_page
from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


def test_csv_page_keeps_visible_order_nulls_and_unicode(tmp_path: Path) -> None:
    result = FetchResult(
        columns=[
            FetchColumn(name="id", type=ColumnType(sql="integer", category="number")),
            FetchColumn(name="name", type=ColumnType(sql="text", category="string")),
            FetchColumn(name="hidden", type=ColumnType(sql="text", category="string")),
        ],
        rows=[["1", "Київ", "not exported"], ["2", None, "not exported"]],
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
    with path.open(encoding="utf-8-sig", newline="") as source:
        assert list(csv.reader(source)) == [["name", "id"], ["Київ", "1"], [NULL_TEXT, "2"]]


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


async def test_download_returns_and_keeps_only_the_requested_page(
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

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["relname", "oid"]
    assert len(rows) == 3

    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    saved = list((storage.home_dir(user.id) / "downloads" / connector_id).glob("*.csv"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == response.content


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
