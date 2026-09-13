"""The metrics routes: agents, the store, the catalog and history."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.main import app
from app.metrics import crud
from app.metrics.models import MetricsAgent, MetricsStoreSetting
from app.metrics.store import MetricsStore, PointRow, SeriesKey, Source
from tests.metrics.conftest import needs_store
from tests.utils.service_engine import FakeEngine, engine_of
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/metrics"
START = 1_789_000_000


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(MetricsStoreSetting))
        await session.exec(delete(MetricsAgent))
        await session.commit()


@pytest.fixture
async def stranger_headers(client: AsyncClient, db: Any) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _agent(client: AsyncClient, headers: dict[str, str], name: str = "web") -> dict[str, Any]:
    response = await client.post(f"{BASE}/agents", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


async def _connect(client: AsyncClient, headers: dict[str, str], options: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/store/connect", headers=headers, json={"options": options}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_registering_an_agent_issues_a_key_only_its_owner_reads(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    created = await _agent(client, normal_user_token_headers)
    agent_id = created["agent"]["id"]

    assert len(created["key"]) >= 32
    assert created["udp_port"] == settings.METRICS_UDP_PORT
    again = await client.get(f"{BASE}/agents/{agent_id}/key", headers=normal_user_token_headers)
    assert again.json()["key"] == created["key"]
    foreign = await client.get(f"{BASE}/agents/{agent_id}/key", headers=stranger_headers)
    assert foreign.status_code == 404
    listed = await client.get(f"{BASE}/agents", headers=stranger_headers)
    assert listed.json() == []


async def test_a_rotated_key_replaces_the_old_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _agent(client, normal_user_token_headers)
    agent_id = created["agent"]["id"]

    rotated = await client.post(f"{BASE}/agents/{agent_id}/key", headers=normal_user_token_headers)

    assert rotated.json()["key"] != created["key"]
    async with async_session_maker() as session:
        assert await crud.agent_by_key(session, created["key"]) is None
        found = await crud.agent_by_key(session, rotated.json()["key"])
        assert found is not None and str(found.id) == agent_id


async def test_the_key_is_not_stored_in_the_clear(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _agent(client, normal_user_token_headers)

    async with async_session_maker() as session:
        agent = await session.get(MetricsAgent, uuid.UUID(created["agent"]["id"]))
        assert agent is not None
        assert created["key"] not in agent.key_fingerprint
        assert created["key"].encode() not in agent.key_sealed


async def test_an_agent_is_renamed_and_removed_by_its_owner_only(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    agent_id = (await _agent(client, normal_user_token_headers))["agent"]["id"]

    refused = await client.patch(
        f"{BASE}/agents/{agent_id}", headers=stranger_headers, json={"name": "mine now"}
    )
    renamed = await client.patch(
        f"{BASE}/agents/{agent_id}", headers=normal_user_token_headers, json={"name": "db"}
    )
    removed = await client.delete(f"{BASE}/agents/{agent_id}", headers=normal_user_token_headers)

    assert refused.status_code == 404
    assert renamed.json()["name"] == "db"
    assert removed.status_code == 200
    assert (await client.get(f"{BASE}/agents", headers=normal_user_token_headers)).json() == []


async def test_before_setup_an_ordinary_user_is_told_and_offered_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    status = await client.get(f"{BASE}/store", headers=normal_user_token_headers)

    assert status.json()["state"] == "not_configured"
    assert status.json()["may_set_up"] is False
    assert status.json()["start"] is None
    catalog = await client.get(f"{BASE}/catalog", headers=normal_user_token_headers)
    assert catalog.status_code == 409


async def test_before_setup_a_superuser_is_told_whether_starting_is_possible(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    with engine_of(app, FakeEngine(available=False)):
        status = await client.get(f"{BASE}/store", headers=superuser_token_headers)

    assert status.json()["state"] == "not_configured"
    assert status.json()["may_set_up"] is True
    assert status.json()["start"]["available"] is False
    assert status.json()["start"]["reason"]


async def test_only_a_superuser_sets_the_store_up(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    started = await client.post(f"{BASE}/store/start", headers=normal_user_token_headers)
    connected = await client.post(
        f"{BASE}/store/connect", headers=normal_user_token_headers, json={"options": {}}
    )

    assert started.status_code == 403
    assert connected.status_code == 403


async def test_options_that_are_not_the_adapter_s_are_refused(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/store/connect",
        headers=superuser_token_headers,
        json={"options": {"auth_method": "user_password", "host": "x"}},
    )

    assert response.status_code == 422


async def test_a_database_that_does_not_answer_is_not_accepted(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/store/connect",
        headers=superuser_token_headers,
        json={
            "options": {
                "auth_method": "user_password",
                "host": "127.0.0.1",
                "port": 1,
                "database": "metrics",
                "user": "nobody",
                "password": "never-shown",
            }
        },
    )

    assert response.status_code == 422
    assert "never-shown" not in response.text
    status = await client.get(f"{BASE}/store", headers=superuser_token_headers)
    assert status.json()["state"] == "not_configured"


@needs_store
async def test_an_existing_timescale_becomes_the_store_and_answers(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    store_options: dict[str, Any],
) -> None:
    status = await _connect(client, superuser_token_headers, store_options)

    assert status["state"] == "ready"
    seen_by_user = await client.get(f"{BASE}/store", headers=normal_user_token_headers)
    assert seen_by_user.json()["state"] == "ready"
    twice = await client.post(
        f"{BASE}/store/connect", headers=superuser_token_headers, json={"options": store_options}
    )
    assert twice.status_code == 409
    async with async_session_maker() as session:
        setting = await crud.store_setting(session)
        assert setting is not None
        assert "password" not in setting.config
        assert store_options["password"].encode() not in setting.secrets


@needs_store
async def test_history_is_read_through_the_owner_of_the_agent(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    agent_id = uuid.UUID((await _agent(client, normal_user_token_headers))["agent"]["id"])
    keys = [SeriesKey("web-01", "cpu", "cpu", "cpu10"), SeriesKey("web-01", "cpu", "cpu", "cpu2")]
    ids = await store.series_ids(
        Source(kind="agent", id=agent_id), [(key, "%", START) for key in keys]
    )
    await store.write_points(
        [PointRow(series_id, START + i * 30, float(i)) for series_id in ids.values() for i in range(20)]
    )

    catalog = await client.get(f"{BASE}/catalog", headers=normal_user_token_headers)
    (agent,) = catalog.json()["agents"]
    (host,) = agent["hosts"]
    labels = [series["label"] for series in host["metrics"][0]["series"]]
    assert labels == ["cpu2", "cpu10"]

    body = {"series_ids": list(ids.values()), "start": START, "end": START + 3600}
    history = await client.post(f"{BASE}/history", headers=normal_user_token_headers, json=body)
    assert history.status_code == 200, history.text
    assert history.json()["bucket_seconds"] is None
    assert [len(series["points"]) for series in history.json()["series"]] == [20, 20]

    bucketed = await client.post(
        f"{BASE}/history", headers=normal_user_token_headers, json={**body, "max_points": 10, "end": START + 86400}
    )
    assert bucketed.json()["bucket_seconds"] is not None
    assert all(len(point) == 4 for s in bucketed.json()["series"] for point in s["points"])

    foreign = await client.post(f"{BASE}/history", headers=stranger_headers, json=body)
    assert foreign.status_code == 404
    unknown = await client.post(
        f"{BASE}/history", headers=normal_user_token_headers, json={**body, "series_ids": [10**12]}
    )
    assert unknown.status_code == 404
    short = await client.post(
        f"{BASE}/history", headers=normal_user_token_headers, json={**body, "end": START + 10}
    )
    assert short.status_code == 422

    listed = await client.get(f"{BASE}/agents", headers=normal_user_token_headers)
    assert listed.json()[0]["last_heard_at"] is not None

    purged = await client.post(f"{BASE}/agents/{agent_id}/purge", headers=normal_user_token_headers)
    assert purged.status_code == 200
    after = await client.get(f"{BASE}/catalog", headers=normal_user_token_headers)
    assert after.json()["agents"][0]["hosts"] == []
