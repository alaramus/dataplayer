import base64
import uuid
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage

BASE = f"{settings.API_V1_STR}/connectors"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "reports").mkdir(exist_ok=True)
    (home / "reports" / "q3.csv").write_text("id,name\n1,one\n2,two\n")
    (home / "notes.txt").write_text("first\nsecond\n")
    (home / "document.json").write_text('{"id": 10000000000000001, "name": "one"}')
    (home / "pixel.png").write_bytes(PNG_1X1)
    (home / "opaque.zip").write_bytes(b"opaque archive bytes")
    _write_datasets(home)
    with zipfile.ZipFile(home / "bundle.zip", "w") as bundle:
        bundle.writestr("readme.md", "# Inside\n")
        bundle.writestr("docs/notes.txt", "first\nsecond\n")
    return home


def _write_datasets(home: Path) -> None:
    """A columnar file and a workbook, the two datasets of D51."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from openpyxl import Workbook

    pq.write_table(
        pa.table(
            {
                "id": pa.array([1, 2, 3], type=pa.int64()),
                "city": pa.array(["one", "two", "three"]),
            }
        ),
        home / "cities.parquet",
    )
    book = Workbook()
    revenue = book.active
    assert revenue is not None
    revenue.title = "Revenue"
    revenue.append(["quarter", "amount"])
    revenue.append(["Q1", 820])
    people = book.create_sheet("People")
    people.append(["name"])
    people.append(["Ann"])
    book.save(home / "budget.xlsx")


async def _create_connector(
    client: AsyncClient, headers: dict[str, str], path: str = "/"
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": path},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_the_catalog_shows_the_personal_directory(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    kinds = {node["name"]: node["kind"] for node in response.json()}
    assert kinds["reports"] == "directory"
    assert kinds["notes.txt"] == "file"


@pytest.mark.usefixtures("home")
async def test_the_catalog_declares_the_default_and_alternative_file_views(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    document = next(node for node in response.json() if node["name"] == "document.json")
    assert [item["kind"] for item in document["representations"]] == [
        "json",
        "table",
    ]
    image = next(node for node in response.json() if node["name"] == "pixel.png")
    opaque = next(node for node in response.json() if node["name"] == "opaque.zip")
    assert image["representations"] == [{"kind": "image", "title": "View image"}]
    assert opaque["representations"] == []


@pytest.mark.usefixtures("home")
async def test_an_image_preview_uses_verified_bytes_and_a_separate_ticket(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    opened = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "pixel.png", "representation": "image"},
    )

    assert opened.status_code == 200, opened.text
    assert opened.json()["media_type"] == "image/png"
    preview = await client.get(opened.json()["preview_url"])
    assert preview.status_code == 200
    assert preview.content == PNG_1X1
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.headers["x-content-type-options"] == "nosniff"


async def test_an_invalid_content_ticket_is_not_a_connector_id(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{BASE}/content-files/not-a-ticket")

    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"


@pytest.mark.usefixtures("home")
async def test_a_json_document_is_read_through_the_content_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "document.json", "representation": "json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "json"
    fields = {entry["name"]: entry["value"] for entry in body["value"]["entries"]}
    assert fields["id"] == {"kind": "number", "value": "10000000000000001"}


@pytest.mark.usefixtures("home")
async def test_text_content_can_be_opened_and_saved_through_the_editor_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    opened = await client.post(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt"},
    )
    assert opened.status_code == 200
    assert opened.json()["writable"] is True

    saved = await client.patch(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={
            "node_id": "notes.txt",
            "text": "edited through the API\n",
            "version": opened.json()["version"],
        },
    )

    assert saved.status_code == 200
    reopened = await client.post(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt"},
    )
    assert reopened.json()["text"] == "edited through the API\n"
    assert reopened.json()["version"] == saved.json()["version"]


@pytest.mark.usefixtures("home")
async def test_saving_a_stale_file_version_answers_with_a_conflict(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)
    opened = await client.post(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt"},
    )

    first = await client.patch(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={
            "node_id": "notes.txt",
            "text": "first writer\n",
            "version": opened.json()["version"],
        },
    )
    stale = await client.patch(
        f"{BASE}/{connector_id}/content/editor",
        headers=normal_user_token_headers,
        json={
            "node_id": "notes.txt",
            "text": "stale writer\n",
            "version": opened.json()["version"],
        },
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert "changed" in stale.json()["detail"]["message"]


@pytest.mark.usefixtures("home")
async def test_a_delimited_file_is_read_as_rows(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "reports/q3.csv", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert [column["name"] for column in body["columns"]] == ["id", "name"]
    assert body["rows"] == [["1", "one"]]
    assert body["has_more"] is True
    assert body["export_supported"] is False
    assert body["export_reason"] == "This source cannot export all matching rows"


@pytest.mark.usefixtures("home")
async def test_the_answer_says_the_source_cannot_sort_or_filter(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt"},
    )

    body = response.json()
    assert all(column["sortable"] is False for column in body["columns"])
    assert all(column["filter_operators"] == [] for column in body["columns"])


@pytest.mark.usefixtures("home")
async def test_a_delimited_file_takes_a_row_and_gives_it_back_deletable(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A CSV is a table the row routes may change, handles and all."""
    connector_id = await _create_connector(client, normal_user_token_headers)

    inserted = await client.post(
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={
            "node_id": "reports/q3.csv",
            "values": [
                {"column": "id", "value": "3"},
                {"column": "name", "value": "three"},
            ],
        },
    )

    assert inserted.status_code == 200, inserted.text
    assert inserted.json()["values"] == ["3", "three"]

    deleted = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={
            "node_id": "reports/q3.csv",
            "row_handles": [inserted.json()["row_handle"]],
        },
    )

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1

    read = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "reports/q3.csv"},
    )
    assert read.json()["rows"] == [["1", "one"], ["2", "two"]]


@pytest.mark.usefixtures("home")
async def test_a_file_that_is_not_a_table_is_not_edited_as_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The capability is the source's; whether a node admits it is per node."""
    connector_id = await _create_connector(client, normal_user_token_headers)

    inserted = await client.post(
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "notes.txt", "values": [{"column": "line", "value": "x"}]},
    )

    assert inserted.status_code == 422


@pytest.mark.usefixtures("home")
async def test_browsing_out_of_the_root_is_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Not a source failure: the request named something it may not name."""
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "../.."},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_reading_out_of_the_root_is_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "../../etc/passwd"},
    )

    assert response.status_code == 422


async def test_a_folder_outside_the_home_is_refused_by_the_form(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"escape {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "../someone-else"},
        },
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_asking_a_file_source_to_sort_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "reports/q3.csv", "sort": [{"column": "id"}]},
    )

    assert response.status_code == 422


async def test_the_error_never_names_the_server_layout(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "nowhere"},
    )

    assert response.status_code == 422
    assert str(home) not in response.text


@pytest.mark.usefixtures("home")
async def test_a_workbook_lists_its_sheets_as_children(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    listing = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    workbook = next(
        node for node in listing.json() if node["name"] == "budget.xlsx"
    )
    # Both: it opens as its first sheet and holds the rest of them (D51).
    assert workbook["has_children"] is True
    assert [one["kind"] for one in workbook["representations"]] == ["table"]

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": workbook["id"]},
    )

    assert response.status_code == 200
    sheets = response.json()
    assert [sheet["name"] for sheet in sheets] == ["Revenue", "People"]
    assert sheets[0]["kind"] == "dataset"
    assert sheets[0]["describable"] is True
    assert [item["kind"] for item in sheets[0]["representations"]] == ["table"]


@pytest.mark.usefixtures("home")
async def test_one_sheet_is_fetched_by_the_id_the_source_issued(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)
    sheets = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "budget.xlsx"},
    )
    second = sheets.json()[1]["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": second},
    )

    assert response.status_code == 200
    body = response.json()
    assert [column["name"] for column in body["columns"]] == ["name"]
    assert body["rows"] == [["Ann"]]


@pytest.mark.usefixtures("home")
async def test_a_columnar_file_is_described_with_the_facts_of_its_format(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": "cities.parquet"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "dataset"
    assert [column["name"] for column in body["columns"]] == ["id", "city"]
    assert body["dataset"]["kind"] == "parquet"
    assert body["dataset"]["rows"] == 3
    assert body["schema_name"] is None
    assert body["owner"] is None


@pytest.mark.usefixtures("home")
async def test_a_sheet_is_described_by_where_it_sits(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": "budget.xlsx/2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dataset"] == {
        "kind": "worksheet",
        "workbook": "budget.xlsx",
        "sheet_name": "People",
        "sheet_position": 2,
        "sheet_count": 2,
        "hidden": False,
        "rows": 1,
        "columns": 1,
    }


@pytest.mark.usefixtures("home")
async def test_a_file_that_states_no_columns_has_no_structure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A CSV reads its names off a line of text, which is a header, not a shape."""
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": "notes.txt"},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_a_sheet_admits_no_action(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Every action names the kinds it acts on, and a dataset is none of them."""
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/actions",
        headers=normal_user_token_headers,
        json={"node_ids": ["budget.xlsx/1"]},
    )

    assert response.status_code == 200
    offered = response.json()
    assert offered != []
    assert all(action["applicable"] is False for action in offered)


@pytest.mark.usefixtures("home")
async def test_an_archive_lists_its_entries_as_a_tree(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    listing = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    bundle = next(node for node in listing.json() if node["name"] == "bundle.zip")
    assert bundle["has_children"] is True
    assert bundle["representations"] == []

    inside = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "bundle.zip"},
    )
    assert inside.status_code == 200
    entries = inside.json()
    assert [entry["name"] for entry in entries] == ["docs", "readme.md"]
    assert entries[0]["kind"] == "entry"

    folder = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "bundle.zip/docs"},
    )
    assert [entry["name"] for entry in folder.json()] == ["notes.txt"]


@pytest.mark.usefixtures("home")
async def test_a_document_inside_an_archive_is_read_without_unpacking_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "bundle.zip/docs/notes.txt", "representation": "text"},
    )

    assert response.status_code == 200
    assert response.json()["text"].startswith("first")


@pytest.mark.usefixtures("home")
async def test_an_entry_that_is_not_there_is_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/content",
        headers=normal_user_token_headers,
        json={"node_id": "bundle.zip/docs/missing.txt", "representation": "text"},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_an_entry_offers_download_and_no_other_action(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/actions",
        headers=normal_user_token_headers,
        json={"node_ids": ["bundle.zip/docs/notes.txt"]},
    )

    assert response.status_code == 200
    applicable = [
        action["name"] for action in response.json() if action["applicable"]
    ]
    assert applicable == ["download"]


@pytest.mark.usefixtures("home")
async def test_one_entry_is_downloaded_through_the_ticket_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    started = await client.post(
        f"{BASE}/{connector_id}/actions/download/download",
        headers=normal_user_token_headers,
        json={"node_ids": ["bundle.zip/docs/notes.txt"]},
    )
    assert started.status_code == 200, started.text

    response = await client.get(started.json()["download_url"])

    assert response.status_code == 200
    assert response.content == b"first\nsecond\n"
    assert "notes.txt" in response.headers["content-disposition"]
