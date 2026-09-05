"""What the editor is told, and what the source writes for it.

Against a real PostgreSQL: metadata is the catalog's own answer, formatting is
the dialect's own layout, and a generated statement is the source quoting its
own names (D65).
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.queries.conftest import silent_connector
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _file(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _metadata(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json=body
    )
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def test_the_source_names_its_schemas_and_the_relations_in_context(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    metadata = await _metadata(
        client, headers, connector_id, search_path=["pg_catalog"]
    )

    assert "public" in metadata["schemas"]
    assert "pg_catalog" in metadata["schemas"]
    # The catalog is a real schema somebody writing PostgreSQL does read.
    names = {relation["name"] for relation in metadata["relations"]}
    assert "pg_class" in names
    assert metadata["complete"] is True


async def test_the_internal_schemas_nobody_completes_against_are_left_out(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    metadata = await _metadata(client, headers, connector_id)

    assert "information_schema" not in metadata["schemas"]
    assert not any(name.startswith("pg_toast") for name in metadata["schemas"])


async def test_columns_arrive_only_for_the_relations_that_were_asked_for(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Progressive: a console does not read a database to fill a dropdown."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    without = await _metadata(client, headers, connector_id, search_path=["pg_catalog"])
    with_columns = await _metadata(
        client,
        headers,
        connector_id,
        search_path=["pg_catalog"],
        relations=["pg_catalog.pg_class"],
    )

    assert without["columns"] == {}
    columns = with_columns["columns"]["pg_catalog.pg_class"]
    assert {column["name"] for column in columns} >= {"relname", "relkind"}
    assert all(column["type_sql"] for column in columns)


async def test_a_relation_that_is_not_there_is_simply_absent(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Not an error: an editor asks about what somebody is typing."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    metadata = await _metadata(
        client, headers, connector_id, relations=["public.no_such_relation"]
    )

    assert metadata["columns"] == {}


async def test_a_name_that_is_not_a_qualified_relation_is_ignored(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    metadata = await _metadata(
        client,
        headers,
        connector_id,
        relations=["nonsense", "a.b.c", "'; drop table pg_class; --"],
    )

    assert metadata["columns"] == {}


async def test_metadata_is_kept_for_a_while_and_thrown_away_by_a_change(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    first = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )
    again = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )
    # Editing the connection is what throws its cached reads away.
    await client.patch(
        f"{CONNECTORS}/{connector_id}", headers=headers, json={"name": "renamed"}
    )
    after = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )

    assert first.headers["x-data-cache"] == "miss"
    assert again.headers["x-data-cache"] == "hit"
    assert after.headers["x-data-cache"] == "miss"


@pytest.mark.usefixtures("silent_source")
async def test_a_source_that_cannot_describe_itself_says_so(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await silent_connector(client, headers)

    metadata = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )
    formatted = await client.post(
        f"{BASE}/connectors/{connector_id}/format",
        headers=headers,
        json={"text": "select 1"},
    )
    generated = await client.post(
        f"{BASE}/connectors/{connector_id}/generate",
        headers=headers,
        json={"node_id": "anything"},
    )

    assert metadata.status_code == 501
    assert formatted.status_code == 501
    assert generated.status_code == 501


async def test_the_profile_says_what_the_source_can_actually_do(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D62: derived from what is implemented, not a second list to keep."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    profile = await client.get(
        f"{BASE}/connectors/{connector_id}/profile", headers=headers
    )

    assert profile.status_code == 200, profile.text
    answered = profile.json()
    assert answered["supports_metadata"] is True
    assert answered["supports_formatting"] is True
    assert answered["supports_generated_query"] is True
    assert answered["supports_explain"] is True


async def test_formatting_lays_a_statement_out_again(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/connectors/{connector_id}/format",
        headers=headers,
        json={"text": "select a,b from t where x=1"},
    )

    assert response.status_code == 200, response.text
    formatted = response.json()["text"]
    assert "SELECT" in formatted
    assert "\n" in formatted


async def test_formatting_leaves_what_it_cannot_read_exactly_as_it_was(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Pressing Format must never quietly rewrite somebody's work."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    original = "select from where"

    response = await client.post(
        f"{BASE}/connectors/{connector_id}/format",
        headers=headers,
        json={"text": original},
    )

    assert response.json()["text"] == original


async def test_formatting_keeps_what_is_between_statements(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/connectors/{connector_id}/format",
        headers=headers,
        json={"text": "select 1; -- a note\nselect 2"},
    )

    assert "-- a note" in response.json()["text"]


async def test_the_source_writes_a_bounded_select_about_its_own_node(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/connectors/{connector_id}/generate",
        headers=headers,
        json={"node_id": "pg_catalog.pg_class", "kind": "select"},
    )

    assert response.status_code == 200, response.text
    text = response.json()["text"]
    assert text.startswith("SELECT ")
    assert '"pg_catalog"."pg_class"' in text
    assert "LIMIT 100" in text


async def test_the_source_writes_a_name_and_a_column_list_too(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    name = await client.post(
        f"{BASE}/connectors/{connector_id}/generate",
        headers=headers,
        json={"node_id": "pg_catalog.pg_class", "kind": "name"},
    )
    columns = await client.post(
        f"{BASE}/connectors/{connector_id}/generate",
        headers=headers,
        json={"node_id": "pg_catalog.pg_class", "kind": "columns"},
    )

    assert name.json()["text"] == '"pg_catalog"."pg_class"'
    assert '"relname"' in columns.json()["text"]


async def test_a_node_that_is_not_a_relation_of_this_source_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/connectors/{connector_id}/generate",
        headers=headers,
        json={"node_id": "public.no_such_relation"},
    )

    assert response.status_code == 404


async def test_none_of_this_is_offered_to_somebody_without_the_connection(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    for path, body in [
        (f"{BASE}/connectors/{connector_id}/metadata", {}),
        (f"{BASE}/connectors/{connector_id}/format", {"text": "select 1"}),
        (f"{BASE}/connectors/{connector_id}/generate", {"node_id": "public.t"}),
    ]:
        response = await client.post(path, headers=stranger, json=body)
        assert response.status_code == 404, path


async def test_a_connection_that_caches_nothing_still_completes_from_memory(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg no cache {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
            "cache_ttl_seconds": 0,
        },
    )
    assert response.status_code == 200, response.text
    connector_id = str(response.json()["id"])

    first = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )
    again = await client.post(
        f"{BASE}/connectors/{connector_id}/metadata", headers=headers, json={}
    )

    # The window belongs to the data somebody is looking at. What an editor
    # completes against is a whole description of the database, and it keeps
    # the source's own five minutes whatever the rows were told to do (D105).
    assert first.headers["x-data-cache"] == "miss"
    assert again.headers["x-data-cache"] == "hit"
