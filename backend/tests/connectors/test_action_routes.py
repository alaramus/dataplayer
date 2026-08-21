import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.files import look

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    for stale in home.iterdir():
        if stale.is_dir():
            continue
        stale.unlink()
    (home / "reports").mkdir(exist_ok=True)
    (home / "reports" / "q3.csv").write_text("id,name\n1,one\n", encoding="utf-8")
    (home / "notes.txt").write_text("first\n", encoding="utf-8")
    return home


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    options = working_postgres_options()
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": {**options, "password": options["password"]},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _run(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    action: str,
    node_id: str | None = None,
    **params: object,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/{action}",
        headers=headers,
        json={"node_id": node_id, "params": params},
    )


# --- what is offered ---------------------------------------------------------


@pytest.mark.usefixtures("home")
async def test_a_directory_offers_the_actions_that_change_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/actions",
        headers=normal_user_token_headers,
        params={"node_id": "reports"},
    )

    assert response.status_code == 200
    offered = {action["name"]: action for action in response.json()}
    assert set(offered) == {"create_folder", "upload", "rename", "delete"}
    assert offered["delete"]["destructive"] is True
    assert offered["upload"]["takes_file"] is True
    assert offered["create_folder"]["takes_file"] is False
    assert "name" in offered["create_folder"]["params_schema"]["properties"]


@pytest.mark.usefixtures("home")
async def test_the_root_offers_no_way_to_remove_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/actions", headers=normal_user_token_headers
    )

    names = {action["name"] for action in response.json()}
    assert names == {"create_folder", "upload"}


async def test_a_source_without_actions_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/actions", headers=normal_user_token_headers
    )

    assert response.status_code == 501


async def test_a_source_without_actions_refuses_to_run_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "public"
    )

    assert response.status_code == 501


# --- running an action -------------------------------------------------------


@pytest.mark.usefixtures("home")
async def test_creating_a_folder_shows_it_in_the_catalog(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "create_folder",
        "reports",
        name="2026",
    )

    assert response.status_code == 200
    assert response.json()["reload_node_id"] == "reports"

    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "reports"},
    )
    assert "2026" in {node["name"] for node in catalog.json()}


@pytest.mark.usefixtures("home")
async def test_renaming_a_file_changes_the_catalog(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "rename",
        "notes.txt",
        new_name="renamed.txt",
    )

    assert response.status_code == 200
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    assert "renamed.txt" in {node["name"] for node in catalog.json()}


@pytest.mark.usefixtures("home")
async def test_deleting_a_file_removes_it_from_the_catalog(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "notes.txt"
    )

    assert response.status_code == 200
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    assert "notes.txt" not in {node["name"] for node in catalog.json()}


@pytest.mark.usefixtures("home")
async def test_an_unknown_action_is_not_found(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Nothing outside the registry resolves — not even a method of the driver."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "check_connection", None
    )

    assert response.status_code == 404


@pytest.mark.usefixtures("home")
async def test_parameters_that_miss_the_schema_are_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "create_folder", "reports"
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "params", "name"]


@pytest.mark.usefixtures("home")
async def test_an_action_the_node_does_not_admit_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "create_folder",
        "notes.txt",
        name="inside-a-file",
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_the_root_of_a_connector_cannot_be_deleted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", None, recursive=True
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_a_node_outside_the_root_cannot_be_acted_on(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "../../etc"
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_deleting_a_folder_with_files_is_a_conflict(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "reports"
    )

    assert response.status_code == 409


@pytest.mark.usefixtures("home")
async def test_a_taken_name_is_a_conflict(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "create_folder",
        None,
        name="reports",
    )

    assert response.status_code == 409


# --- uploading ---------------------------------------------------------------


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    filename: str,
    body: bytes,
    node_id: str | None = None,
    **params: object,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/upload/file",
        headers=headers,
        files={"file": (filename, body, "text/csv")},
        data={"node_id": node_id or "", "params": json.dumps(params)},
    )


@pytest.mark.usefixtures("home")
async def test_an_uploaded_file_can_be_read_as_rows(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _upload(
        client,
        normal_user_token_headers,
        connector_id,
        "uploaded.csv",
        b"id,name\n7,seven\n",
        "reports",
    )

    assert response.status_code == 200
    rows = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "reports/uploaded.csv"},
    )
    assert rows.json()["rows"] == [["7", "seven"]]


@pytest.mark.usefixtures("home")
async def test_uploading_over_a_taken_name_is_a_conflict(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _upload(
        client, normal_user_token_headers, connector_id, "q3.csv", b"new", "reports"
    )

    assert response.status_code == 409


@pytest.mark.usefixtures("home")
async def test_uploading_over_a_taken_name_is_allowed_when_asked(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _upload(
        client,
        normal_user_token_headers,
        connector_id,
        "q3.csv",
        b"id,name\n9,nine\n",
        "reports",
        overwrite=True,
    )

    assert response.status_code == 200


@pytest.mark.usefixtures("home")
async def test_an_uploaded_name_cannot_leave_the_folder(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    """The filename is a client string too, and gets the rule of a path segment."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _upload(
        client, normal_user_token_headers, connector_id, "../escaped.txt", b"body"
    )

    assert response.status_code == 422
    assert not (home.parent / "escaped.txt").exists()


@pytest.mark.usefixtures("home")
async def test_an_upload_larger_than_the_ceiling_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 16)
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _upload(
        client, normal_user_token_headers, connector_id, "big.bin", b"x" * 1024
    )

    assert response.status_code == 413
    assert not (home / "big.bin").exists()
    assert await look(lambda: list(home.glob(".upload-*"))) == []


@pytest.mark.usefixtures("home")
async def test_an_action_needing_a_file_refuses_a_plain_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "upload", "reports"
    )

    assert response.status_code == 415


@pytest.mark.usefixtures("home")
async def test_an_action_without_a_file_refuses_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/actions/create_folder/file",
        headers=normal_user_token_headers,
        files={"file": ("thing.txt", b"body", "text/plain")},
        data={"node_id": "", "params": json.dumps({"name": "smuggled"})},
    )

    assert response.status_code == 415


# --- who may ask -------------------------------------------------------------


@pytest.mark.usefixtures("home")
async def test_a_connector_of_another_user_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """Owned by someone else, so it is not there at all — no action, no listing."""
    connector_id = await _file_connector(client, superuser_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "notes.txt"
    )

    assert response.status_code == 404

    listing = await client.get(
        f"{BASE}/{connector_id}/actions", headers=normal_user_token_headers
    )
    assert listing.status_code == 404


@pytest.mark.usefixtures("home")
async def test_an_error_never_names_the_server_layout(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "nowhere"
    )

    assert response.status_code == 422
    assert str(home) not in response.text
