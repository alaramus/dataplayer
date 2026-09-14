"""The metrics routes: agents, the store, the catalog and history."""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.main import app
from app.metrics import crud
from app.metrics.dashboards import Dashboard
from app.metrics.models import MetricsAgent, MetricsStoreSetting
from app.metrics.protocol import HostDescription
from app.metrics.store import (
    AgentRunRow,
    MetricsStore,
    PointRow,
    ProcessPart,
    ProcessRow,
    RestartRow,
    SeriesKey,
    Source,
)
from app.users import crud as user_crud
from tests.metrics.conftest import refresh_rollups
from tests.utils.database import working_postgres_options
from tests.utils.service_engine import FakeEngine, engine_of
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/metrics"
# Days ago rather than a fixed moment: which table history reads depends on
# how old a range is (raw samples are kept a week).
START = (int(time.time()) - 3 * 86400) // 3600 * 3600


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
    await refresh_rollups(store)

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
    # Ten points of a day: three-hour buckets, read from the hourly rollups.
    assert bucketed.json()["bucket_seconds"] == 10800
    assert [len(s["points"]) for s in bucketed.json()["series"]] == [1, 1]
    assert bucketed.json()["series"][0]["points"][0][1:] == [9.5, 0.0, 19.0]

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


async def test_process_tables_and_presets_are_read_through_the_owner_of_the_agent(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    agent_id = uuid.UUID((await _agent(client, normal_user_token_headers))["agent"]["id"])
    source = Source(kind="agent", id=agent_id)
    now = int(datetime.now(UTC).timestamp())
    rows = [
        ProcessRow(
            pid=pid, ppid=1, user="root", state="S", pcpu=float(cpu), pmem=float(10 - cpu),
            rss=4096 * pid, started=now - 3600, name="worker", command=f"worker {pid}",
        )
        for pid, cpu in ((10, 1), (11, 5), (12, 3))
    ]
    await store.write_processes(source, ProcessPart(host="only-ps", ts=now - 120, total=80, rows=rows[:1]))
    await store.write_processes(source, ProcessPart(host="only-ps", ts=now - 30, total=81, rows=rows))
    key = SeriesKey("web-01", "host", "uptime", "")
    await store.series_ids(source, [(key, "s", now)])

    catalog = (await client.get(f"{BASE}/catalog", headers=normal_user_token_headers)).json()
    hosts = {host["host"]: host for host in catalog["agents"][0]["hosts"]}
    assert hosts["only-ps"]["processes"] is True
    assert hosts["only-ps"]["metrics"] == []
    assert hosts["web-01"]["processes"] is False

    query = {"agent_id": str(agent_id), "host": "only-ps", "sort": "pmem", "limit": 10}
    table = await client.get(f"{BASE}/processes", headers=normal_user_token_headers, params=query)
    assert table.status_code == 200, table.text
    assert (table.json()["ts"], table.json()["total"]) == (now - 30, 81)
    assert [row["pid"] for row in table.json()["rows"]] == [10, 12, 11]
    first = table.json()["rows"][0]
    assert (first["state"], first["rss_bytes"], first["name"], first["command"]) == ("S", 40960, "worker", "worker 10")
    assert datetime.fromisoformat(first["started_at"]) == datetime.fromtimestamp(now - 3600, UTC)
    empty = await client.get(f"{BASE}/processes", headers=normal_user_token_headers, params={**query, "host": "web-01"})
    assert empty.json() == {"ts": None, "total": None, "rows": []}
    odd = await client.get(f"{BASE}/processes", headers=normal_user_token_headers, params={**query, "sort": "command"})
    assert odd.status_code == 422
    foreign = await client.get(f"{BASE}/processes", headers=stranger_headers, params=query)
    assert foreign.status_code == 404

    presets = await client.get(
        f"{BASE}/presets", headers=normal_user_token_headers, params={"agent_id": str(agent_id), "host": "web-01"}
    )
    assert presets.status_code == 200, presets.text
    (linux,) = presets.json()
    assert linux["key"] == "linux-host"
    assert [widget["title"] for widget in linux["widgets"]] == ["Uptime"]
    refused = await client.get(
        f"{BASE}/presets", headers=stranger_headers, params={"agent_id": str(agent_id), "host": "web-01"}
    )
    assert refused.status_code == 404


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{settings.API_V1_STR}/connectors/",
        headers=headers,
        json={"name": f"reporting {uuid.uuid4()}", "adapter_type": "postgres", "options": working_postgres_options()},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def test_a_connection_reports_by_its_owner_s_choice_and_is_read_through_its_grants(
    client: AsyncClient,
    db: Any,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    email = random_email()
    colleague_headers = await authentication_token_from_email(client=client, email=email, db=db)
    colleague = await user_crud.get_user_by_email(session=db, email=email)
    assert colleague is not None
    granted = await client.put(
        f"{settings.API_V1_STR}/connectors/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(colleague.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text

    owned = (await client.get(f"{BASE}/connectors", headers=normal_user_token_headers)).json()
    shared = (await client.get(f"{BASE}/connectors", headers=colleague_headers)).json()
    unseen = (await client.get(f"{BASE}/connectors", headers=stranger_headers)).json()
    mine = next(row for row in owned if row["connector_id"] == connector_id)
    assert mine["enabled"] is False and mine["may_change"] is True
    assert next(row for row in shared if row["connector_id"] == connector_id)["may_change"] is False
    assert all(row["connector_id"] != connector_id for row in unseen)

    body = {"enabled": True, "interval_seconds": 15}
    by_colleague = await client.put(f"{BASE}/connectors/{connector_id}", headers=colleague_headers, json=body)
    by_stranger = await client.put(f"{BASE}/connectors/{connector_id}", headers=stranger_headers, json=body)
    by_owner = await client.put(f"{BASE}/connectors/{connector_id}", headers=normal_user_token_headers, json=body)
    odd = await client.put(f"{BASE}/connectors/{connector_id}", headers=normal_user_token_headers, json={"enabled": True, "interval_seconds": 1})
    assert by_colleague.status_code == 403
    assert by_stranger.status_code == 404
    assert by_owner.status_code == 200, by_owner.text
    assert by_owner.json()["enabled"] is True and by_owner.json()["interval_seconds"] == 15
    assert odd.status_code == 422

    source = Source(kind="connector", id=uuid.UUID(connector_id))
    key = SeriesKey("", "sessions", "count", "total")
    series_id = (await store.series_ids(source, [(key, "", START)]))[key]
    await store.write_points([PointRow(series_id, START, 3.0)])

    catalog = (await client.get(f"{BASE}/catalog", headers=colleague_headers)).json()
    (reported,) = [one for one in catalog["connectors"] if one["connector_id"] == connector_id]
    assert reported["adapter_type"] == "postgres"
    assert reported["metrics"][0]["series"][0]["id"] == series_id
    stranger_catalog = (await client.get(f"{BASE}/catalog", headers=stranger_headers)).json()
    assert all(one["connector_id"] != connector_id for one in stranger_catalog["connectors"])

    body = {"series_ids": [series_id], "start": START - 60, "end": START + 60}
    assert (await client.post(f"{BASE}/history", headers=colleague_headers, json=body)).status_code == 200
    assert (await client.post(f"{BASE}/history", headers=stranger_headers, json=body)).status_code == 404

    presets = await client.get(f"{BASE}/presets", headers=colleague_headers, params={"connector_id": connector_id})
    assert presets.status_code == 200, presets.text
    (database,) = presets.json()
    assert database["key"] == "postgres-database"
    assert [widget["title"] for widget in database["widgets"]] == ["Sessions by state"]
    both = await client.get(
        f"{BASE}/presets", headers=colleague_headers, params={"connector_id": connector_id, "host": "x"}
    )
    assert both.status_code == 422


async def test_a_source_that_does_not_report_metrics_cannot_be_switched_on(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/connectors/",
        headers=normal_user_token_headers,
        json={"name": f"files {uuid.uuid4()}", "adapter_type": "file", "options": {"path": "/"}},
    )
    connector_id = response.json()["id"]

    refused = await client.put(
        f"{BASE}/connectors/{connector_id}", headers=normal_user_token_headers, json={"enabled": True}
    )
    listed = (await client.get(f"{BASE}/connectors", headers=normal_user_token_headers)).json()

    assert refused.status_code == 501
    assert all(row["connector_id"] != connector_id for row in listed)



async def test_hosts_that_keep_restarting_are_told_to_their_agent_s_owner_only(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    before = await client.get(f"{BASE}/restarts", headers=normal_user_token_headers)
    assert before.status_code == 200
    assert before.json()["hosts"] == []

    await _connect(client, superuser_token_headers, store_options)
    agent_id = uuid.UUID((await _agent(client, normal_user_token_headers, "crashing"))["agent"]["id"])
    await _agent(client, stranger_headers, "theirs")
    now = int(datetime.now(UTC).timestamp())
    for i in range(4):
        await store.write_restart(RestartRow(agent_id, "crash-probe", now - 33 * i, "agent"))
    await store.write_restart(RestartRow(agent_id, "rebooted-once", now - 10, "host"))

    answer = await client.get(f"{BASE}/restarts", headers=normal_user_token_headers)
    theirs = await client.get(f"{BASE}/restarts", headers=stranger_headers)

    assert answer.status_code == 200, answer.text
    (host,) = answer.json()["hosts"]
    assert host["host"] == "crash-probe"
    assert host["agent_name"] == "crashing"
    assert host["count"] == 4
    assert host["cause"] == "agent"
    assert "runs_iftop" not in host
    assert answer.json()["window_seconds"] > 0
    assert theirs.json()["hosts"] == []


async def test_the_hosts_of_an_agent_say_what_they_are_to_its_owner_only(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    agent_id = uuid.UUID((await _agent(client, normal_user_token_headers, "fleet"))["agent"]["id"])
    await _agent(client, stranger_headers, "theirs")
    now = int(datetime.now(UTC).timestamp())
    described = HostDescription(
        os="Ubuntu 24.04.1 LTS", kernel="6.8.0", arch="amd64", cpus=8, cpu_model="Xeon",
        memory=16 * 1024**3, boot_time=now - 86400, collectors={"cpu": 15, "processes": 60},
    )
    await store.write_run(AgentRunRow(agent_id, "web-01", "a", "0.1.1", now - 600, "boot"), described, now - 590)
    await store.write_run(AgentRunRow(agent_id, "new-01", "b", "0.1.1", now - 5, "boot"))
    key = SeriesKey("web-01", "host", "uptime", "")
    series_id = (await store.series_ids(Source("agent", agent_id), [(key, "s", now - 15)]))[key]
    await store.write_points([PointRow(series_id, now - 15, 86385.0)])

    answer = await client.get(f"{BASE}/hosts", headers=normal_user_token_headers)
    theirs = await client.get(f"{BASE}/hosts", headers=stranger_headers)

    assert answer.status_code == 200, answer.text
    new, web = answer.json()
    assert (new["host"], new["os"], new["last_seen"], new["collectors"]) == ("new-01", None, None, {})
    assert (web["host"], web["agent_name"], web["agent_version"]) == ("web-01", "fleet", "0.1.1")
    assert (web["os"], web["cpus"], web["memory_bytes"], web["collectors"]) == (
        "Ubuntu 24.04.1 LTS", 8, 16 * 1024**3, {"cpu": 15, "processes": 60},
    )
    assert datetime.fromisoformat(web["booted_at"]) == datetime.fromtimestamp(now - 86400, UTC)
    assert datetime.fromisoformat(web["last_seen"]) == datetime.fromtimestamp(now - 15, UTC)
    assert theirs.json() == []


async def test_removing_a_connected_store_drops_its_tables_and_takes_series_off_dashboards(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    agent_id = (await _agent(client, normal_user_token_headers))["agent"]["id"]
    source = Source(kind="agent", id=uuid.UUID(agent_id))
    key = SeriesKey("web-01", "cpu", "uptime", "")
    series_id = (await store.series_ids(source, [(key, "s", START)]))[key]
    created = (
        await client.post(f"{BASE}/dashboards", headers=normal_user_token_headers, json={"name": "Hosts"})
    ).json()
    layout = {"x": 0, "y": 0, "w": 6, "h": 5}
    widgets = [
        {"type": "stat", "id": str(uuid.uuid4()), "title": "Uptime", "layout": layout, "series_id": series_id},
        {
            "type": "processes",
            "id": str(uuid.uuid4()),
            "title": "Processes",
            "layout": layout,
            "agent_id": agent_id,
            "host": "web-01",
        },
    ]
    saved = await client.put(
        f"{BASE}/dashboards/{created['id']}",
        headers=normal_user_token_headers,
        json={"name": "Hosts", "version": created["version"], "widgets": widgets},
    )
    assert saved.status_code == 200, saved.text

    usage = await client.get(f"{BASE}/store/usage", headers=superuser_token_headers)
    assert usage.status_code == 200, usage.text
    assert usage.json()["origin"] == "connected"
    assert usage.json()["series"] == 1
    assert store_options["password"] not in usage.text
    assert [tier["name"] for tier in usage.json()["tiers"]] == ["raw", "5m", "1h"]
    assert (await client.get(f"{BASE}/store/usage", headers=normal_user_token_headers)).status_code == 403
    assert (await client.delete(f"{BASE}/store", headers=normal_user_token_headers)).status_code == 403

    removed = await client.delete(f"{BASE}/store", headers=superuser_token_headers)

    assert removed.status_code == 200, removed.text
    assert "dropped" in removed.json()["message"]
    status = await client.get(f"{BASE}/store", headers=superuser_token_headers)
    assert status.json()["state"] == "not_configured"
    async with store._engine.connect() as connection:
        gone = (await connection.execute(text("SELECT to_regclass('metric_series') IS NULL"))).scalar_one()
    assert gone
    dashboard = (
        await client.get(f"{BASE}/dashboards/{created['id']}", headers=normal_user_token_headers)
    ).json()
    assert [widget["type"] for widget in dashboard["widgets"]] == ["processes"]
    assert dashboard["version"] == saved.json()["version"] + 1
    again = await client.delete(f"{BASE}/store", headers=superuser_token_headers)
    assert again.status_code == 409
    async with async_session_maker() as session:
        await session.exec(delete(Dashboard))
        await session.commit()
