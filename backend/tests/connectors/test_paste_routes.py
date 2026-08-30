import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"paste {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _rows(
    client: AsyncClient, headers: dict[str, str], connector_id: str, schema: str
) -> tuple[list[str], list[str]]:
    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=headers,
        json={"node_id": f"{schema}.customers", "limit": 10, "sorts": [["name", "asc"]]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return (
        [handle for handle in body["row_handles"] if handle is not None],
        [column["name"] for column in body["columns"]],
    )


async def _two_customers(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann'), (1, 'EU', 'bob')"
    )


async def test_pastes_a_block_across_rows(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    await _two_customers(schema)
    handles, columns = await _rows(
        client, normal_user_token_headers, connector_id, schema
    )

    response = await client.patch(
        f"{BASE}/{connector_id}/rows/cells",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "rows": [
                {"row_handle": handles[0], "cells": [{"column": "name", "value": "x"}]},
                {"row_handle": handles[1], "cells": [{"column": "name", "value": "y"}]},
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "updated"
    assert [row["values"][columns.index("name")] for row in body["rows"]] == ["x", "y"]


async def test_unreadable_values_are_named_and_nothing_is_written(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    await _two_customers(schema)
    handles, _ = await _rows(client, normal_user_token_headers, connector_id, schema)

    response = await client.patch(
        f"{BASE}/{connector_id}/rows/cells",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "rows": [
                {"row_handle": handles[0], "cells": [{"column": "name", "value": "x"}]},
                {
                    "row_handle": handles[1],
                    "cells": [{"column": "balance", "value": "nope"}],
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "rejected",
        "cells": [{"row": 1, "column": "balance"}],
    }


async def test_a_stale_row_is_a_conflict(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    await _two_customers(schema)
    handles, _ = await _rows(client, normal_user_token_headers, connector_id, schema)
    await run(
        f"UPDATE {schema}.customers SET name = 'moved' WHERE name = 'bob'"  # noqa: S608 -- fixture-owned schema.
    )

    response = await client.patch(
        f"{BASE}/{connector_id}/rows/cells",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "rows": [
                {"row_handle": handles[1], "cells": [{"column": "name", "value": "x"}]}
            ],
        },
    )

    assert response.status_code == 409


async def test_a_row_may_be_edited_only_once(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    await _two_customers(schema)
    handles, _ = await _rows(client, normal_user_token_headers, connector_id, schema)

    response = await client.patch(
        f"{BASE}/{connector_id}/rows/cells",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "rows": [
                {"row_handle": handles[0], "cells": [{"column": "name", "value": "x"}]},
                {"row_handle": handles[0], "cells": [{"column": "name", "value": "y"}]},
            ],
        },
    )

    assert response.status_code == 422


async def test_requires_a_write_grant(client: AsyncClient) -> None:
    response = await client.patch(
        f"{BASE}/{uuid.uuid4()}/rows/cells",
        json={
            "node_id": "public.x",
            "rows": [{"row_handle": "h", "cells": [{"column": "c", "value": "v"}]}],
        },
    )
    assert response.status_code == 401
