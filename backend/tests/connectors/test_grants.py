import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import ConnectorGrant
from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    """Somebody other than the owner, with a token of their own."""
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"shared {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


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


async def _grant(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    user: User,
    access: str,
) -> None:
    response = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=headers,
        json={"user_id": str(user.id), "access": access},
    )
    assert response.status_code == 200, response.text


# --- what a connection of your own says about itself ----------------------


async def test_your_own_connection_says_you_own_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.json()["access"] == "own"
    assert response.json()["owner_email"] is None


# --- no grant -------------------------------------------------------------


async def test_without_a_grant_the_connection_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    _, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(f"{BASE}/{connector_id}", headers=headers)

    assert response.status_code == 404


async def test_a_superuser_without_a_grant_sees_nothing(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """D34: administering accounts is not a standing on somebody's data."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    single = await client.get(f"{BASE}/{connector_id}", headers=superuser_token_headers)
    listed = await client.get(f"{BASE}/", headers=superuser_token_headers)

    assert single.status_code == 404
    assert connector_id not in {item["id"] for item in listed.json()["data"]}


# --- what a grant admits --------------------------------------------------


async def test_a_read_grant_shows_the_connection_and_names_its_owner(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    single = await client.get(f"{BASE}/{connector_id}", headers=headers)
    listed = await client.get(f"{BASE}/", headers=headers)

    assert single.status_code == 200
    assert single.json()["access"] == "read"
    assert single.json()["owner_email"] == settings.EMAIL_TEST_USER
    shared = [item for item in listed.json()["data"] if item["id"] == connector_id]
    assert len(shared) == 1
    assert shared[0]["access"] == "read"


async def test_a_read_grant_reads_rows(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=headers,
        json={"node_id": f"{schema}.customers", "limit": 5},
    )

    assert response.status_code == 200, response.text


async def test_a_read_grant_gets_a_page_it_cannot_change(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """The refusal is in the page, not only in the 403 that would follow."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=headers,
        json={"node_id": f"{schema}.customers", "limit": 5},
    )

    body = response.json()
    assert body["update_supported"] is False
    assert body["insert_supported"] is False
    assert body["delete_supported"] is False
    assert body["update_reason"] is not None
    assert not any(column["editable"] for column in body["columns"])


async def test_a_write_grant_gets_an_editable_page(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=headers,
        json={"node_id": f"{schema}.customers", "limit": 5},
    )

    body = response.json()
    assert body["update_supported"] is True
    assert any(column["editable"] for column in body["columns"])


async def test_a_read_grant_does_not_edit_rows(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    response = await client.patch(
        f"{BASE}/{connector_id}/rows/cell",
        headers=headers,
        json={
            "node_id": f"{schema}.customers",
            "row_handle": "stale-handle",
            "column": "name",
            "value": "x",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "write"


async def test_a_write_grant_does_not_change_the_shape(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/columns",
        headers=headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "note",
            "type_code": "text",
            "nullable": True,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_a_write_grant_is_told_the_shape_is_not_theirs(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """The structure screen reads the relation's own two fields, so they say it."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=headers,
        params={"node_id": f"{schema}.customers"},
    )

    body = response.json()
    assert body["column_changes_supported"] is False
    assert body["column_changes_reason"] is not None
    assert body["column_type_options"] == []


async def test_a_structure_grant_may_change_the_shape_of_a_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "structure")

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=headers,
        params={"node_id": f"{schema}.customers"},
    )

    assert response.json()["column_changes_supported"] is True


async def test_a_structure_grant_changes_the_shape(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "structure")

    response = await client.patch(
        f"{BASE}/{connector_id}/columns",
        headers=headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "region_id",
            "new_name": "area_id",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"name": "area_id"}


async def test_a_write_grant_may_not_change_nullability(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """Whether a column may be empty is the shape, not the rows."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=headers,
        json={"node_id": f"{schema}.customers", "name": "name", "nullable": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_a_write_grant_may_not_change_a_column_type(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=headers,
        json={"node_id": f"{schema}.customers", "name": "name", "type_code": "text"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_a_write_grant_may_not_index_a_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """An index is the shape of a relation, not its rows."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=headers,
        json={
            "node_id": f"{schema}.customers",
            "columns": ["name"],
            "method": "btree",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_a_write_grant_is_not_offered_index_methods(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=headers,
        params={"node_id": f"{schema}.customers"},
    )

    body = response.json()
    assert body["index_changes_supported"] is False
    assert body["index_changes_reason"] is not None
    assert body["index_methods"] == []


async def test_a_write_grant_may_not_constrain_a_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=headers,
        json={
            "node_id": f"{schema}.regions",
            "constraint": {"kind": "unique", "columns": ["code"]},
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_no_grant_reaches_the_connection_itself(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "structure")

    renamed = await client.patch(
        f"{BASE}/{connector_id}", headers=headers, json={"name": "mine now"}
    )
    removed = await client.delete(f"{BASE}/{connector_id}", headers=headers)

    assert renamed.status_code == 403
    assert removed.status_code == 403


# --- actions carry their own level ----------------------------------------


async def test_a_read_grant_is_offered_no_file_actions(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _file_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    response = await client.post(
        f"{BASE}/{connector_id}/actions", headers=headers, json={}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_a_write_grant_is_offered_file_actions(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _file_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/actions", headers=headers, json={}
    )

    assert response.status_code == 200
    assert "create_folder" in {item["name"] for item in response.json()}


async def test_a_read_grant_cannot_run_a_file_action(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _file_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    response = await client.post(
        f"{BASE}/{connector_id}/actions/create_folder",
        headers=headers,
        json={"params": {"name": "intruder"}},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "write"


async def test_renaming_a_relation_needs_structure(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.post(
        f"{BASE}/{connector_id}/actions/rename_relation",
        headers=headers,
        json={"node_id": f"{schema}.customers", "params": {"new_name": "clients"}},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_loading_a_csv_needs_structure(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """Making a table is DDL, and it is not offered to someone who may not."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    offered = await client.post(
        f"{BASE}/{connector_id}/actions",
        headers=headers,
        json={"node_ids": [schema]},
    )
    response = await client.post(
        f"{BASE}/{connector_id}/actions/load_csv/file",
        headers=headers,
        files={"file": ("regions.csv", b"id\n1\n", "text/csv")},
        data={"node_id": schema, "params": "{}"},
    )

    assert "load_csv" not in {action["name"] for action in offered.json()}
    assert response.status_code == 403
    assert response.json()["detail"]["required"] == "structure"


async def test_dropping_a_relation_needs_structure(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """And so does asking what it would take with it: the answer names them."""
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    dropped = await client.post(
        f"{BASE}/{connector_id}/actions/drop_relation",
        headers=headers,
        json={"node_id": f"{schema}.customers", "params": {"cascade": True}},
    )
    asked = await client.post(
        f"{BASE}/{connector_id}/actions/drop_relation/preview",
        headers=headers,
        json={"node_id": f"{schema}.customers", "params": {}},
    )

    assert dropped.status_code == 403
    assert dropped.json()["detail"]["required"] == "structure"
    assert asked.status_code == 403


# --- managing the grants themselves ---------------------------------------


async def test_only_the_owner_reads_and_writes_grants(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "structure")

    listed = await client.get(f"{BASE}/{connector_id}/grants", headers=headers)
    written = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=headers,
        json={"user_id": str(user.id), "access": "structure"},
    )

    assert listed.status_code == 403
    assert written.status_code == 403


async def test_the_owner_sees_who_holds_what(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, _ = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "write")

    response = await client.get(
        f"{BASE}/{connector_id}/grants", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "access": "write",
        }
    ]


async def test_a_grant_can_be_raised_and_lowered(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    await _grant(client, normal_user_token_headers, connector_id, user, "read")
    await _grant(client, normal_user_token_headers, connector_id, user, "structure")
    raised = await client.get(f"{BASE}/{connector_id}", headers=headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")
    lowered = await client.get(f"{BASE}/{connector_id}", headers=headers)

    assert raised.json()["access"] == "structure"
    assert lowered.json()["access"] == "read"


async def test_granting_to_yourself_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    owner = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert owner is not None
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(owner.id), "access": "read"},
    )

    assert response.status_code == 422


async def test_granting_to_an_unknown_user_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(uuid.uuid4()), "access": "read"},
    )

    assert response.status_code == 422


async def test_ownership_cannot_be_granted(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, _ = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(user.id), "access": "own"},
    )

    assert response.status_code == 422


async def test_revoking_takes_the_connection_out_of_sight(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    revoked = await client.delete(
        f"{BASE}/{connector_id}/grants/{user.id}", headers=normal_user_token_headers
    )
    after = await client.get(f"{BASE}/{connector_id}", headers=headers)

    assert revoked.status_code == 200
    assert after.status_code == 404


async def test_revoking_what_was_never_given_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    user, _ = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.delete(
        f"{BASE}/{connector_id}/grants/{user.id}", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_grants_go_with_the_user(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    db: AsyncSession,
) -> None:
    user, _ = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    await crud.delete_user(session=db, user=user)

    remaining = await db.exec(
        select(ConnectorGrant).where(ConnectorGrant.user_id == user.id)
    )
    assert remaining.all() == []


async def test_grants_go_with_the_connection(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    db: AsyncSession,
) -> None:
    user, _ = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _grant(client, normal_user_token_headers, connector_id, user, "read")

    await client.delete(f"{BASE}/{connector_id}", headers=normal_user_token_headers)

    remaining = await db.exec(
        select(ConnectorGrant).where(
            ConnectorGrant.connector_id == uuid.UUID(connector_id)
        )
    )
    assert remaining.all() == []


# --- the directory a share dialog picks from ------------------------------


async def test_the_directory_lists_other_active_users(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    db: AsyncSession,
) -> None:
    user, _ = colleague
    owner = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert owner is not None

    response = await client.get(
        f"{settings.API_V1_STR}/users/directory", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    listed = {item["id"] for item in response.json()["data"]}
    assert str(user.id) in listed
    assert str(owner.id) not in listed
    assert "is_superuser" not in response.json()["data"][0]
