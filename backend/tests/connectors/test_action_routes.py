import io
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from httpx import AsyncClient, Response
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.actions import Action
from app.adapters.file.adapter import FileAdapter
from app.adapters.protocol import ConnectionCheckResult
from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.files import look
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def relation_schema() -> AsyncGenerator[str]:
    async for schema in make_schema():
        yield schema


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
    # Written as bytes: a download is asserted byte for byte, and write_text
    # stores CRLF on Windows.
    (home / "reports" / "q3.csv").write_bytes(b"id,name\n1,one\n")
    (home / "notes.txt").write_bytes(b"first\n")
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


async def test_action_menu_awaits_the_connection_vocabulary_on_every_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)
    original = FileAdapter.all_actions
    calls = AsyncMock()

    async def vocabulary(adapter: FileAdapter) -> list[Action[Any]]:
        await calls()
        actions = await original(adapter)
        return actions if calls.await_count == 1 else []

    monkeypatch.setattr(FileAdapter, "all_actions", vocabulary)
    path = f"{BASE}/{connector_id}/actions"
    first = await client.post(
        path, headers=normal_user_token_headers, json={"node_ids": []}
    )
    assert first.status_code == 200
    assert "create_folder" in {item["name"] for item in first.json()}
    second = await client.post(
        path, headers=normal_user_token_headers, json={"node_ids": []}
    )
    assert second.status_code == 200
    assert second.json() == []
    assert calls.await_count == 2


class NoActionOptions(BaseModel):
    url: str


class NoActionAdapter:
    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)


async def _no_action_connector(
    client: AsyncClient, headers: dict[str, str]
) -> str:
    registry.register(
        name="no-actions",
        title="No actions",
        category="sql",
        description="A source with no management actions",
        options_schema=NoActionOptions,
        adapter_class=NoActionAdapter,
    )(lambda _options, _context: NoActionAdapter())
    created = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"no actions {uuid.uuid4()}",
            "adapter_type": "no-actions",
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200
    return str(created.json()["id"])


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


async def _run_on_set(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    action: str,
    node_ids: list[str],
    **params: object,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/{action}/set",
        headers=headers,
        json={"node_ids": node_ids, "params": params},
    )


async def _offered(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    node_ids: list[str] | None = None,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions",
        headers=headers,
        json={"node_ids": node_ids},
    )


def _applicable(response: Response) -> set[str]:
    """What the answer says can be done to the nodes that were asked about.

    The listing carries the whole vocabulary of the source, so a client can
    show a menu that keeps its shape; which of it applies here is one flag per
    action rather than the length of the list.
    """
    return {action["name"] for action in response.json() if action["applicable"]}


# --- what is offered ---------------------------------------------------------


@pytest.mark.usefixtures("home")
async def test_a_directory_offers_the_actions_that_change_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["reports"]
    )

    assert response.status_code == 200
    offered = {action["name"]: action for action in response.json()}
    assert _applicable(response) == {
        "create_folder",
        "connect_folder",
        "upload",
        "paste",
        "download",
        "create_archive",
        "rename",
        "delete",
    }
    assert offered["delete"]["destructive"] is True
    assert offered["upload"]["takes_file"] is True
    # Several files go into a folder through one filled form, a request
    # each. A client reads this to offer a set rather than one file.
    assert offered["upload"]["takes_many_files"] is True
    assert offered["download"]["downloads"] is True
    assert offered["delete"]["downloads"] is False
    assert offered["connect_folder"]["prepares_connector"] is True
    assert offered["create_folder"]["prepares_connector"] is False
    assert offered["create_folder"]["takes_file"] is False
    assert offered["create_folder"]["takes_many_files"] is False
    assert "name" in offered["create_folder"]["params_schema"]["properties"]


@pytest.mark.usefixtures("home")
async def test_an_action_says_whether_it_changes_the_node_or_its_contents(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """What the client acts on follows from this, not from the name.

    Ticked rows are renamed and deleted; a new folder is made inside the level
    being looked at. A client that read the difference off the names of the
    actions would have to be taught every new one.
    """
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["reports"]
    )

    scopes = {action["name"]: action["acts_on"] for action in response.json()}
    assert scopes == {
        "create_folder": "children",
        "connect_folder": "node",
        "upload": "children",
        "paste": "children",
        "download": "node",
        "create_archive": "node",
        "extract_archive": "node",
        "rename": "node",
        "delete": "node",
    }


@pytest.mark.usefixtures("home")
async def test_an_action_says_where_it_is_offered(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Where a command is drawn is the source's answer, not a name the client
    knows (D79). Everything a file source has belongs in the catalog menu."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["reports"]
    )

    places = {action["offered_in"] for action in response.json()}
    assert places == {"catalog"}


@pytest.mark.usefixtures("home")
async def test_the_root_offers_no_way_to_remove_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id)

    assert _applicable(response) == {"create_folder", "upload", "paste"}


async def test_folder_draft_prepares_a_nested_root_without_saving_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    headers = normal_user_token_headers
    child_name = f"draft-{uuid.uuid4()}"
    child = home / "reports" / child_name
    child.mkdir()
    (child / "inside.txt").write_text("kept", encoding="utf-8")
    parent = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": "nested source",
            "adapter_type": "file",
            "options": {"path": "reports"},
        },
    )
    assert parent.status_code == 200
    parent_id = parent.json()["id"]
    before = await client.get(f"{BASE}/", headers=headers)
    prepared = await client.post(
        f"{BASE}/{parent_id}/actions/connect_folder/connector-draft",
        headers=headers,
        json={"node_id": child_name},
    )
    assert prepared.status_code == 200
    assert prepared.json() == {
        "name": child_name,
        "adapter_type": "file",
        "options": {"path": f"/reports/{child_name}"},
    }
    assert str(home) not in prepared.text
    after = await client.get(f"{BASE}/", headers=headers)
    assert after.json()["count"] == before.json()["count"]

    saved = await client.post(f"{BASE}/", headers=headers, json=prepared.json())
    assert saved.status_code == 200
    saved_id = saved.json()["id"]
    catalog = await client.get(f"{BASE}/{saved_id}/catalog", headers=headers)
    assert catalog.status_code == 200
    assert [node["name"] for node in catalog.json()] == ["inside.txt"]
    escape = await client.get(
        f"{BASE}/{saved_id}/catalog",
        headers=headers,
        params={"node_id": ".."},
    )
    assert escape.status_code == 422
    assert (child / "inside.txt").read_text(encoding="utf-8") == "kept"


@pytest.mark.usefixtures("home")
@pytest.mark.parametrize(
    "node_id", [None, "", "notes.txt", "missing", "../outside", "/etc"]
)
async def test_folder_draft_rechecks_which_node_may_be_connected(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    node_id: str | None,
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)
    refused = await client.post(
        f"{BASE}/{connector_id}/actions/connect_folder/connector-draft",
        headers=normal_user_token_headers,
        json={"node_id": node_id},
    )
    assert refused.status_code == 422


@pytest.mark.usefixtures("home")
async def test_connector_drafts_use_only_the_declared_action_transport(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector_id = await _file_connector(client, headers)
    for action, status in [("rename", 415), ("unknown", 404)]:
        refused = await client.post(
            f"{BASE}/{connector_id}/actions/{action}/connector-draft",
            headers=headers,
            json={"node_id": "reports"},
        )
        assert refused.status_code == status
    ordinary = await _run(client, headers, connector_id, "connect_folder", "reports")
    assert ordinary.status_code == 415
    supplied = await client.post(
        f"{BASE}/{connector_id}/actions/connect_folder/connector-draft",
        headers=headers,
        json={"node_id": "reports", "params": {"path": "elsewhere"}},
    )
    assert supplied.status_code == 422


async def test_postgres_declares_schema_creation_as_an_action_on_the_level(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id)

    assert response.status_code == 200
    create = next(
        action for action in response.json() if action["name"] == "create_schema"
    )
    assert create["applicable"] is True
    assert create["acts_on"] == "level"


@pytest.mark.usefixtures("home")
async def test_what_does_not_apply_here_is_listed_and_marked(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The vocabulary of the source, whatever the node it was asked about.

    A menu that only held what applies would change shape at every step; one
    built from this greys out what cannot be done instead of hiding it.
    """
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id)

    listed = {action["name"] for action in response.json()}
    assert listed == {
        "create_folder",
        "connect_folder",
        "upload",
        "paste",
        "download",
        "create_archive",
        "extract_archive",
        "rename",
        "delete",
    }


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_without_actions_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _no_action_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id)

    assert response.status_code == 501


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_without_actions_refuses_to_run_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _no_action_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "public"
    )

    assert response.status_code == 501


async def test_renaming_a_postgres_relation_returns_its_new_source_identity(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    old_node_id = f"{relation_schema}.customers"
    new_node_id = f"{relation_schema}.clients"

    offered = await _offered(
        client, normal_user_token_headers, connector_id, [old_node_id]
    )
    rename = next(
        action for action in offered.json() if action["name"] == "rename_relation"
    )
    assert rename["applicable"] is True

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "rename_relation",
        old_node_id,
        new_name="clients",
    )

    assert response.status_code == 200
    assert response.json()["reload_node_ids"] == [relation_schema]
    assert response.json()["replacement"] == {
        "old_node_id": old_node_id,
        "new_node_id": new_node_id,
        "title": "clients",
    }
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    assert "clients" in {node["name"] for node in catalog.json()}
    assert "customers" not in {node["name"] for node in catalog.json()}


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
    assert response.json()["reload_node_ids"] == ["reports"]

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
async def test_a_folder_name_defaults_when_the_form_is_submitted_unchanged(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "create_folder", "reports"
    )

    assert response.status_code == 200
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "reports"},
    )
    assert "new folder" in {node["name"] for node in catalog.json()}


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
        client, normal_user_token_headers, connector_id, "delete", None
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
async def test_deleting_a_folder_removes_its_contents_after_confirmation(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client, normal_user_token_headers, connector_id, "delete", "reports"
    )

    assert response.status_code == 200


@pytest.mark.usefixtures("home")
async def test_a_taken_folder_name_gets_the_first_free_number(
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

    assert response.status_code == 200
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
    )
    assert "reports (1)" in {node["name"] for node in catalog.json()}


# --- downloading -------------------------------------------------------------


async def _prepare_download(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    node_ids: list[str],
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/download/download",
        headers=headers,
        json={"node_ids": node_ids},
    )


async def test_an_invalid_download_ticket_is_not_a_connector_id(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{BASE}/action-downloads/not-a-ticket")

    assert response.status_code == 404
    assert response.json()["detail"] == "Download not found"


@pytest.mark.usefixtures("home")
async def test_one_file_downloads_unchanged_through_its_action(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    prepared = await _prepare_download(
        client, normal_user_token_headers, connector_id, ["notes.txt"]
    )
    assert prepared.status_code == 200, prepared.text
    downloaded = await client.get(prepared.json()["download_url"])

    assert downloaded.status_code == 200
    assert downloaded.content == b"first\n"
    assert "notes.txt" in downloaded.headers["content-disposition"]
    assert downloaded.headers["content-type"] == "application/octet-stream"


@pytest.mark.usefixtures("home")
async def test_several_nodes_download_as_one_archive(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    prepared = await _prepare_download(
        client,
        normal_user_token_headers,
        connector_id,
        ["notes.txt", "reports"],
    )
    assert prepared.status_code == 200, prepared.text
    downloaded = await client.get(prepared.json()["download_url"])

    assert downloaded.status_code == 200
    assert "download.zip" in downloaded.headers["content-disposition"]
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.read("notes.txt") == b"first\n"
        assert archive.read("reports/q3.csv") == b"id,name\n1,one\n"


@pytest.mark.usefixtures("home")
async def test_one_folder_is_archived_before_it_downloads(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    prepared = await _prepare_download(
        client, normal_user_token_headers, connector_id, ["reports"]
    )
    assert prepared.status_code == 200, prepared.text
    downloaded = await client.get(prepared.json()["download_url"])

    assert downloaded.status_code == 200
    assert "reports.zip" in downloaded.headers["content-disposition"]
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.read("reports/q3.csv") == b"id,name\n1,one\n"


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
        conflict="replace",
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

    listing = await _offered(client, normal_user_token_headers, connector_id)
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


# --- what a set of nodes admits ----------------------------------------------


@pytest.mark.usefixtures("home")
async def test_a_selection_of_relations_is_dropped_in_one_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    """One request for the set, because the set is the question (D68)."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    nodes = [f"{relation_schema}.rich_customers", f"{relation_schema}.customers"]

    offered = await _offered(client, normal_user_token_headers, connector_id, nodes)
    drop = next(
        action for action in offered.json() if action["name"] == "drop_relation"
    )
    assert drop["applicable"] is True
    assert drop["takes_set"] is True
    assert drop["previews_set"] is True

    preview = await client.post(
        f"{BASE}/{connector_id}/actions/drop_relation/set/preview",
        headers=normal_user_token_headers,
        json={"node_ids": nodes, "params": {}},
    )
    assert preview.status_code == 200
    assert preview.json()["blocked"] is False

    response = await _run_on_set(
        client, normal_user_token_headers, connector_id, "drop_relation", nodes
    )

    assert response.status_code == 200
    assert response.json()["message"] == "2 relations dropped"
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    left = {node["name"] for node in catalog.json()}
    assert "customers" not in left
    assert "rich_customers" not in left


@pytest.mark.usefixtures("home")
async def test_a_node_named_twice_in_a_set_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    node = f"{relation_schema}.rich_customers"

    response = await _run_on_set(
        client, normal_user_token_headers, connector_id, "drop_relation", [node, node]
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_an_action_done_one_node_at_a_time_refuses_a_set_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Delete is bulk, but each file is its own request: the set route is not it."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run_on_set(
        client,
        normal_user_token_headers,
        connector_id,
        "delete",
        ["notes.txt", "reports"],
    )

    assert response.status_code == 415


@pytest.mark.usefixtures("home")
async def test_a_selection_of_files_becomes_one_archive_and_comes_back(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Packing is a set action, and unpacking is one file at a time (D68)."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    made = await _run_on_set(
        client,
        normal_user_token_headers,
        connector_id,
        "create_archive",
        ["notes.txt", "reports"],
        name="bundle",
        format="tar.gz",
    )

    assert made.status_code == 200
    assert made.json()["message"] == "bundle.tar.gz created"
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    assert "bundle.tar.gz" in {node["name"] for node in catalog.json()}

    # Extract is offered for the archive and for nothing else beside it.
    offered = await _offered(
        client, normal_user_token_headers, connector_id, ["bundle.tar.gz"]
    )
    assert "extract_archive" in _applicable(offered)
    plain = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt"]
    )
    assert "extract_archive" not in _applicable(plain)

    back = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "extract_archive",
        "bundle.tar.gz",
    )

    assert back.status_code == 200
    assert back.json()["message"].endswith("extracted into bundle")
    inside = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "bundle"},
    )
    assert {"notes.txt", "reports"} <= {node["name"] for node in inside.json()}


@pytest.mark.usefixtures("home")
async def test_a_file_that_is_not_an_archive_cannot_be_extracted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "extract_archive",
        "notes.txt",
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_two_files_admit_only_what_can_be_done_to_many(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Delete says it applies to many; rename cannot, one name for two files."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt", "reports"]
    )

    assert response.status_code == 200
    assert _applicable(response) == {"download", "create_archive", "delete"}


@pytest.mark.usefixtures("home")
async def test_one_node_in_a_set_admits_everything_it_would_alone(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt"]
    )

    assert _applicable(response) == {
        "download",
        "create_archive",
        "rename",
        "delete",
    }


@pytest.mark.usefixtures("home")
async def test_a_set_admits_nothing_one_of_its_members_refuses(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The root cannot be deleted, so a set holding it cannot be deleted either."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["", "notes.txt"]
    )

    assert response.status_code == 200
    assert _applicable(response) == set()


@pytest.mark.usefixtures("home")
async def test_an_empty_set_of_nodes_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Null means the root; an empty list would be a second way of saying it."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id, [])

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_a_node_that_is_not_there_is_refused_inside_a_set(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt", "nowhere"]
    )

    assert response.status_code == 422


# --- loading a CSV into a database ------------------------------------------


async def _load_csv(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    schema: str,
    filename: str,
    body: bytes,
    **params: object,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/load_csv/file",
        headers=headers,
        files={"file": (filename, body, "text/csv")},
        data={"node_id": schema, "params": json.dumps(params)},
    )


async def test_a_schema_offers_loading_a_csv_and_says_it_takes_a_file(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    offered = await _offered(
        client, normal_user_token_headers, connector_id, [relation_schema]
    )

    load = next(
        action for action in offered.json() if action["name"] == "load_csv"
    )
    assert load["applicable"] is True
    # The screen learns all of this from the answer: that there is a file to
    # attach, which fields the form has, and where the action puts things.
    assert load["takes_file"] is True
    # One file makes one table, so this one is not offered as a set.
    assert load["takes_many_files"] is False
    assert load["acts_on"] == "destination"
    assert list(load["params_schema"]["properties"]) == [
        "name",
        "schema_name",
        "create_schema",
        "columns",
    ]
    # The pairing of file columns to table columns is a workflow of its own,
    # not a field the generic form knows how to draw.
    assert load["params_schema"]["x-ui-workflow"] == "file-to-relation"


async def test_a_system_schema_does_not_admit_a_loaded_csv(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    offered = await _offered(
        client, normal_user_token_headers, connector_id, ["pg_catalog"]
    )

    assert "load_csv" not in _applicable(offered)


async def test_destination_candidates_do_not_become_a_bulk_creation_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    other = f"action_destination_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{other}"')  # noqa: S608 -- generated fixture name.
    try:
        response = await _offered(
            client, normal_user_token_headers, connector_id,
            ["pg_catalog", relation_schema, other],
        )
        assert response.status_code == 200
        offered = {action["name"]: action for action in response.json()}
        for name in ("load_csv", "create_table"):
            assert offered[name]["acts_on"] == "destination"
            assert offered[name]["applicable"] is True
            assert offered[name]["available_node_ids"] == [relation_schema, other]
            assert offered[name]["unavailable_reason"] is None
        assert offered["drop_schema"]["applicable"] is False
        pair = await _offered(
            client, normal_user_token_headers, connector_id, [relation_schema, other]
        )
        pair_actions = {action["name"]: action for action in pair.json()}
        for name in ("rename_schema", "drop_schema"):
            assert pair_actions[name]["acts_on"] == "group"
            assert pair_actions[name]["applicable"] is False
            assert pair_actions[name]["unavailable_reason"] == "Select one grouping to use this"
        refused = await _run_on_set(
            client, normal_user_token_headers, connector_id,
            "create_table", [relation_schema, other],
        )
        assert refused.status_code == 422
    finally:
        await run(f'DROP SCHEMA "{other}" CASCADE')  # noqa: S608 -- generated fixture name.


async def test_an_uploaded_csv_becomes_a_table_that_can_be_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _load_csv(
        client,
        normal_user_token_headers,
        connector_id,
        relation_schema,
        "loaded_regions.csv",
        b"id,code\n7,US\n8,AP\n",
    )

    assert response.status_code == 200, response.text
    assert response.json()["message"] == "loaded_regions created with 2 rows"
    assert response.json()["reload_node_ids"] == [relation_schema]

    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    assert "loaded_regions" in {node["name"] for node in catalog.json()}

    rows = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{relation_schema}.loaded_regions", "limit": 10},
    )
    assert sorted(row[1] for row in rows.json()["rows"]) == ["AP", "US"]


async def test_a_typed_name_wins_over_the_name_of_the_file(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _load_csv(
        client,
        normal_user_token_headers,
        connector_id,
        relation_schema,
        "loaded_regions.csv",
        b"id,code\n7,US\n",
        name="chosen",
    )

    assert response.status_code == 200, response.text
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    names = {node["name"] for node in catalog.json()}
    assert "chosen" in names
    assert "loaded_regions" not in names


async def test_loading_over_a_taken_name_is_a_conflict(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _load_csv(
        client,
        normal_user_token_headers,
        connector_id,
        relation_schema,
        "customers.csv",
        b"id\n1\n",
    )

    assert response.status_code == 409


async def test_a_file_source_cannot_be_asked_to_load_a_csv(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A name that is not in the source's own set does not resolve."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _load_csv(
        client,
        normal_user_token_headers,
        connector_id,
        "",
        "loaded_regions.csv",
        b"id\n1\n",
    )

    assert response.status_code == 404


# --- asking what an action would do -----------------------------------------


async def _preview(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    action: str,
    node_id: str | None = None,
    **params: object,
) -> Response:
    return await client.post(
        f"{BASE}/{connector_id}/actions/{action}/preview",
        headers=headers,
        json={"node_id": node_id, "params": params},
    )


async def test_the_listing_says_which_actions_can_be_asked_first(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    offered = await _offered(
        client, normal_user_token_headers, connector_id, [f"{relation_schema}.customers"]
    )

    previews = {
        action["name"]: action["previews"] for action in offered.json()
    }
    assert previews["drop_relation"] is True
    assert previews["rename_relation"] is False


async def test_a_preview_of_a_cascade_names_what_would_go(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    plain = await _preview(
        client,
        normal_user_token_headers,
        connector_id,
        "drop_relation",
        f"{relation_schema}.customers",
    )
    cascade = await _preview(
        client,
        normal_user_token_headers,
        connector_id,
        "drop_relation",
        f"{relation_schema}.customers",
        cascade=True,
    )

    assert plain.status_code == 200, plain.text
    assert plain.json()["blocked"] is True
    assert any("rich_customers" in item for item in plain.json()["items"])
    assert cascade.status_code == 200
    assert cascade.json()["blocked"] is False
    assert any("rich_customers" in item for item in cascade.json()["items"])

    # Nothing was kept: the question is not the deed.
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    assert "customers" in {node["name"] for node in catalog.json()}


async def test_an_action_with_nothing_to_preview_says_so(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _preview(
        client,
        normal_user_token_headers,
        connector_id,
        "rename_relation",
        f"{relation_schema}.customers",
        new_name="clients",
    )

    assert response.status_code == 501


async def test_previewing_a_name_the_source_does_not_have_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _preview(
        client,
        normal_user_token_headers,
        connector_id,
        "drop_everything",
        f"{relation_schema}.customers",
    )

    assert response.status_code == 404


# --- dropping ----------------------------------------------------------------


async def test_dropping_a_relation_takes_it_out_of_the_catalog(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    relation_schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    refused = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "drop_relation",
        f"{relation_schema}.customers",
    )
    dropped = await _run(
        client,
        normal_user_token_headers,
        connector_id,
        "drop_relation",
        f"{relation_schema}.customers",
        cascade=True,
    )

    assert refused.status_code == 422
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["reload_node_ids"] == [relation_schema]

    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": relation_schema},
    )
    left = {node["name"] for node in catalog.json()}
    assert "customers" not in left
    assert "rich_customers" not in left


async def test_a_file_source_has_no_drop_to_preview(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _preview(
        client, normal_user_token_headers, connector_id, "drop_relation", "notes.txt"
    )

    assert response.status_code == 404
