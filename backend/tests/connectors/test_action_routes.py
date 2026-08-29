import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient, Response
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult
from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.files import look
from tests.utils.relation_fixture import make_schema

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
    assert _applicable(response) == {"create_folder", "upload", "rename", "delete"}
    assert offered["delete"]["destructive"] is True
    assert offered["upload"]["takes_file"] is True
    assert offered["create_folder"]["takes_file"] is False
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
        "upload": "children",
        "rename": "node",
        "delete": "node",
    }


@pytest.mark.usefixtures("home")
async def test_the_root_offers_no_way_to_remove_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(client, normal_user_token_headers, connector_id)

    assert _applicable(response) == {"create_folder", "upload"}


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
    assert listed == {"create_folder", "upload", "rename", "delete"}


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
    assert response.json()["reload_node_id"] == relation_schema
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
async def test_two_files_admit_only_what_can_be_done_to_many(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Delete says it applies to many; rename cannot, one name for two files."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt", "reports"]
    )

    assert response.status_code == 200
    assert _applicable(response) == {"delete"}


@pytest.mark.usefixtures("home")
async def test_one_node_in_a_set_admits_everything_it_would_alone(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _offered(
        client, normal_user_token_headers, connector_id, ["notes.txt"]
    )

    assert _applicable(response) == {"rename", "delete"}


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
