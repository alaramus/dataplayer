import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage

BASE = f"{settings.API_V1_STR}/connectors"


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
    return home


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
async def test_a_file_source_has_no_row_mutation_capabilities(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    inserted = await client.post(
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "reports/q3.csv", "values": []},
    )
    deleted = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "reports/q3.csv", "row_handles": ["opaque"]},
    )

    assert inserted.status_code == 501
    assert deleted.status_code == 501


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
