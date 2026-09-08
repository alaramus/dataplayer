import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Response

from app.adapters.fetch import FetchColumn, FetchResult
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.relation import ColumnType
from app.adapters.specializations import TimescaleHypertable
from app.adapters.summary import NodeSummary, RelationContents
from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.mark.parametrize("surface", ["node-summary", "fetch"])
async def test_timescale_reads_recheck_grants_before_serving_cached_data(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    summary = NodeSummary(
        node_id="lab.metrics", name="metrics", kind="table",
        contents=RelationContents(
            relation_kind="table", schema_name="lab", columns=1, indexes=0,
            constraints=0, specialization=TimescaleHypertable(),
        ),
    )
    rows = FetchResult(
        columns=[FetchColumn(name="value", type=ColumnType(sql="bigint", category="number"))],
        rows=[["9007199254740993"]], has_more=False, row_handles=[None],
        update_supported=False, insert_supported=False, delete_supported=False,
    )
    method = AsyncMock(return_value=summary if surface == "node-summary" else rows)
    monkeypatch.setattr(PostgresAdapter, "node_summary" if surface == "node-summary" else "fetch", method)
    owner, reader = normal_user_token_headers, superuser_token_headers
    options = {**working_postgres_options(), "password": "timescale-route-secret-sentinel"}
    created = await client.post(f"{BASE}/", headers=owner, json={
        "name": f"timescale access {uuid.uuid4()}", "adapter_type": "postgres",
        "options": options,
    })
    assert created.status_code == 200
    connector_id = created.json()["id"]
    path = f"{BASE}/{connector_id}/{surface}"

    async def read(headers: dict[str, str]) -> Response:
        if surface == "node-summary":
            return await client.get(path, headers=headers, params={"node_id": "lab.metrics"})
        return await client.post(path, headers=headers, json={"node_id": "lab.metrics"})

    assert (await read(reader)).status_code == 404
    method.assert_not_awaited()
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=reader)
    assert me.status_code == 200
    reader_id = me.json()["id"]
    granted = await client.put(f"{BASE}/{connector_id}/grants", headers=owner, json={
        "user_id": reader_id, "access": "read",
    })
    assert granted.status_code == 200
    for _ in range(2):
        response = await read(reader)
        assert response.status_code == 200
        body = response.json()
        if surface == "node-summary":
            assert body["contents"]["specialization"] == {"kind": "timescale_hypertable"}
        else:
            assert body["rows"] == [["9007199254740993"]]
            assert not body["update_supported"] and not body["insert_supported"] and not body["delete_supported"]
        assert options["password"] not in response.text
    assert method.await_count >= 1
    method.reset_mock()
    revoked = await client.delete(f"{BASE}/{connector_id}/grants/{reader_id}", headers=owner)
    assert revoked.status_code == 200
    assert (await read(reader)).status_code == 404
    method.assert_not_awaited()
    disabled = await client.patch(f"{BASE}/{connector_id}", headers=owner, json={"enabled": False})
    assert disabled.status_code == 200
    assert (await read(owner)).status_code == 409
    method.assert_not_awaited()
