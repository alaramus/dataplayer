"""A dashboard shared with somebody, and what that lets them read (D129)."""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.metrics.access import live_series, readable_sources
from app.metrics.dashboards import Dashboard
from app.metrics.models import MetricsAgent, MetricsStoreSetting
from app.metrics.store import (
    MetricsStore,
    PointRow,
    ProcessPart,
    ProcessRow,
    SeriesKey,
    Source,
)
from app.users import crud as user_crud
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/metrics"
NOW = int(time.time()) // 60 * 60


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Dashboard))
        await session.exec(delete(MetricsStoreSetting))
        await session.exec(delete(MetricsAgent))
        await session.commit()


@dataclass
class Person:
    id: uuid.UUID
    headers: dict[str, str]


async def _person(client: AsyncClient, db: Any) -> Person:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await user_crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return Person(id=user.id, headers=headers)


def _layout() -> dict[str, int]:
    return {"x": 0, "y": 0, "w": 6, "h": 5}


def _chart(series_ids: list[int]) -> dict[str, Any]:
    return {"type": "timeseries", "id": str(uuid.uuid4()), "title": "CPU", "layout": _layout(), "series_ids": series_ids}


def _table(agent_id: uuid.UUID, host: str) -> dict[str, Any]:
    return {
        "type": "processes", "id": str(uuid.uuid4()), "title": "Processes", "layout": _layout(),
        "agent_id": str(agent_id), "host": host,
    }


async def _agent_series(
    client: AsyncClient, store: MetricsStore, owner: Person, name: str, host: str = "web-01"
) -> tuple[uuid.UUID, int]:
    answer = await client.post(f"{BASE}/agents", headers=owner.headers, json={"name": name})
    agent_id = uuid.UUID(answer.json()["agent"]["id"])
    key = SeriesKey(host, "cpu", "cpu", "total")
    series_id = (await store.series_ids(Source("agent", agent_id), [(key, "%", NOW)]))[key]
    await store.write_points([PointRow(series_id, NOW - 60 * i, float(i)) for i in range(5)])
    return agent_id, series_id


async def _dashboard(client: AsyncClient, owner: Person, widgets: list[dict[str, Any]]) -> dict[str, Any]:
    created = (await client.post(f"{BASE}/dashboards", headers=owner.headers, json={"name": "Hosts"})).json()
    saved = await client.put(
        f"{BASE}/dashboards/{created['id']}",
        headers=owner.headers,
        json={"name": "Hosts", "version": created["version"], "widgets": widgets},
    )
    assert saved.status_code == 200, saved.text
    return dict(saved.json())


async def _grant(client: AsyncClient, owner: Person, dashboard_id: str, who: Person, level: str) -> None:
    granted = await client.put(
        f"{BASE}/dashboards/{dashboard_id}/grants",
        headers=owner.headers,
        json={"user_id": str(who.id), "access": level},
    )
    assert granted.status_code == 200, granted.text


def _history(series_id: int, dashboard_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"series_ids": [series_id], "start": NOW - 600, "end": NOW}
    if dashboard_id is not None:
        body["dashboard_id"] = dashboard_id
    return body


async def _connect(client: AsyncClient, superuser_token_headers: dict[str, str], store_options: dict[str, Any]) -> None:
    connected = await client.post(f"{BASE}/store/connect", headers=superuser_token_headers, json={"options": store_options})
    assert connected.status_code == 200, connected.text


async def test_only_the_owner_gives_and_takes_access(client: AsyncClient, db: Any) -> None:
    owner, reader, stranger = await _person(client, db), await _person(client, db), await _person(client, db)
    created = (await client.post(f"{BASE}/dashboards", headers=owner.headers, json={"name": "Hosts"})).json()
    url = f"{BASE}/dashboards/{created['id']}/grants"
    await _grant(client, owner, created["id"], reader, "read")

    assert (await client.get(url, headers=reader.headers)).status_code == 403
    assert (await client.get(url, headers=stranger.headers)).status_code == 404
    by_reader = await client.put(url, headers=reader.headers, json={"user_id": str(stranger.id), "access": "write"})
    assert by_reader.status_code == 403
    to_self = await client.put(url, headers=owner.headers, json={"user_id": str(owner.id), "access": "read"})
    assert to_self.status_code == 422
    nobody = await client.put(url, headers=owner.headers, json={"user_id": str(uuid.uuid4()), "access": "read"})
    assert nobody.status_code == 422
    own_level = await client.put(url, headers=owner.headers, json={"user_id": str(reader.id), "access": "own"})
    assert own_level.status_code == 422
    listed = (await client.get(url, headers=owner.headers)).json()
    assert [(row["user_id"], row["access"]) for row in listed] == [(str(reader.id), "read")]

    shared = (await client.get(f"{BASE}/dashboards", headers=reader.headers)).json()
    assert [(one["id"], one["access"]) for one in shared] == [(created["id"], "read")]
    assert shared[0]["owner"]
    assert (await client.get(f"{BASE}/dashboards", headers=owner.headers)).json()[0]["access"] == "own"
    assert (await client.get(f"{BASE}/dashboards/{created['id']}", headers=stranger.headers)).status_code == 404

    revoked = await client.delete(f"{url}/{reader.id}", headers=owner.headers)
    assert revoked.status_code == 200
    assert (await client.get(f"{BASE}/dashboards/{created['id']}", headers=reader.headers)).status_code == 404
    assert (await client.delete(f"{url}/{reader.id}", headers=owner.headers)).status_code == 404


async def test_a_reader_sees_it_an_editor_changes_it_and_only_the_owner_deletes_it(client: AsyncClient, db: Any) -> None:
    owner, reader, editor = await _person(client, db), await _person(client, db), await _person(client, db)
    created = (await client.post(f"{BASE}/dashboards", headers=owner.headers, json={"name": "Hosts"})).json()
    await _grant(client, owner, created["id"], reader, "read")
    await _grant(client, owner, created["id"], editor, "write")
    url = f"{BASE}/dashboards/{created['id']}"
    body = {"name": "Renamed by the editor", "version": 1, "widgets": []}

    assert (await client.put(url, headers=reader.headers, json=body)).status_code == 403
    edited = await client.put(url, headers=editor.headers, json=body)
    assert edited.status_code == 200, edited.text
    assert edited.json()["access"] == "write"
    assert (await client.get(url, headers=reader.headers)).json()["name"] == "Renamed by the editor"
    assert (await client.delete(url, headers=editor.headers)).status_code == 403
    assert (await client.delete(url, headers=owner.headers)).status_code == 200


async def test_a_series_is_read_through_the_dashboard_it_is_on_and_no_other_way(
    client: AsyncClient,
    db: Any,
    superuser_token_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    owner, reader = await _person(client, db), await _person(client, db)
    agent_id, on_it = await _agent_series(client, store, owner, "web")
    _, elsewhere = await _agent_series(client, store, owner, "db", host="db-01")
    dashboard = await _dashboard(client, owner, [_chart([on_it]), _table(agent_id, "web-01")])
    await _grant(client, owner, dashboard["id"], reader, "read")
    await store.write_processes(
        Source("agent", agent_id),
        ProcessPart("web-01", NOW, 90, [ProcessRow(1, 0, "root", "S", 0.1, 0.1, 4096, NOW - 60, "init", "init")]),
    )

    through = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(on_it, dashboard["id"]))
    assert through.status_code == 200, through.text
    assert len(through.json()["series"][0]["points"]) == 5
    assert (await client.post(f"{BASE}/history", headers=reader.headers, json=_history(on_it))).status_code == 404
    other = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(elsewhere, dashboard["id"]))
    assert other.status_code == 404

    processes = {"agent_id": str(agent_id), "host": "web-01", "dashboard_id": dashboard["id"]}
    table = await client.get(f"{BASE}/processes", headers=reader.headers, params=processes)
    assert table.status_code == 200, table.text
    assert [row["command"] for row in table.json()["rows"]] == ["init"]
    wrong_host = await client.get(f"{BASE}/processes", headers=reader.headers, params={**processes, "host": "db-01"})
    assert wrong_host.status_code == 404

    catalog = (await client.get(f"{BASE}/dashboards/{dashboard['id']}/catalog", headers=reader.headers)).json()
    (agent,) = catalog["agents"]
    (host,) = agent["hosts"]
    assert agent["name"] == "web"
    assert host["processes"] is True
    assert [series["id"] for metric in host["metrics"] for series in metric["series"]] == [on_it]
    assert (await client.get(f"{BASE}/catalog", headers=reader.headers)).json()["agents"] == []

    async with async_session_maker() as session:
        direct = await readable_sources(session, reader.id)
        assert await live_series(session, store, reader.id, direct) == {on_it}

    await client.delete(f"{BASE}/dashboards/{dashboard['id']}/grants/{reader.id}", headers=owner.headers)
    gone = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(on_it, dashboard["id"]))
    assert gone.status_code == 404
    async with async_session_maker() as session:
        assert await live_series(session, store, reader.id, set()) == set()


async def test_an_editor_keeps_what_is_there_and_adds_only_what_they_read_themselves(
    client: AsyncClient,
    db: Any,
    superuser_token_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    owner, editor, reader = await _person(client, db), await _person(client, db), await _person(client, db)
    _, owners = await _agent_series(client, store, owner, "web")
    _, owners_other = await _agent_series(client, store, owner, "db", host="db-01")
    editor_agent, editors = await _agent_series(client, store, editor, "laptop", host="laptop")
    dashboard = await _dashboard(client, owner, [_chart([owners])])
    await _grant(client, owner, dashboard["id"], editor, "write")
    await _grant(client, owner, dashboard["id"], reader, "read")
    url = f"{BASE}/dashboards/{dashboard['id']}"

    kept = await client.put(
        url, headers=editor.headers,
        json={"name": "Hosts", "version": dashboard["version"], "widgets": [_chart([owners]), _chart([editors])]},
    )
    assert kept.status_code == 200, kept.text
    foreign = await client.put(
        url, headers=editor.headers,
        json={"name": "Hosts", "version": kept.json()["version"], "widgets": [_chart([owners_other])]},
    )
    assert foreign.status_code == 422
    foreign_table = await client.put(
        url, headers=reader.headers,
        json={"name": "Hosts", "version": kept.json()["version"], "widgets": [_table(editor_agent, "laptop")]},
    )
    assert foreign_table.status_code == 403

    # What the editor put there is read through the dashboard by the owner and
    # the reader alike, while the editor holds their level.
    for person in (owner, reader):
        read = await client.post(f"{BASE}/history", headers=person.headers, json=_history(editors, dashboard["id"]))
        assert read.status_code == 200, read.text
    await _grant(client, owner, dashboard["id"], editor, "read")
    lowered = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(editors, dashboard["id"]))
    assert lowered.status_code == 404


async def test_a_connection_taken_from_the_owner_is_taken_from_everybody_reading_through_them(
    client: AsyncClient,
    db: Any,
    superuser_token_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    await _connect(client, superuser_token_headers, store_options)
    lender, owner, reader = await _person(client, db), await _person(client, db), await _person(client, db)
    connector = await client.post(
        f"{settings.API_V1_STR}/connectors/",
        headers=lender.headers,
        json={"name": f"lent {uuid.uuid4()}", "adapter_type": "postgres", "options": working_postgres_options()},
    )
    connector_id = connector.json()["id"]
    granted = await client.put(
        f"{settings.API_V1_STR}/connectors/{connector_id}/grants",
        headers=lender.headers,
        json={"user_id": str(owner.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text
    key = SeriesKey("", "sessions", "count", "total")
    series_id = (await store.series_ids(Source("connector", uuid.UUID(connector_id)), [(key, "", NOW)]))[key]
    await store.write_points([PointRow(series_id, NOW - 60, 3.0)])
    dashboard = await _dashboard(client, owner, [_chart([series_id])])
    await _grant(client, owner, dashboard["id"], reader, "read")

    before = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(series_id, dashboard["id"]))
    assert before.status_code == 200, before.text

    await client.delete(f"{settings.API_V1_STR}/connectors/{connector_id}/grants/{owner.id}", headers=lender.headers)

    after = await client.post(f"{BASE}/history", headers=reader.headers, json=_history(series_id, dashboard["id"]))
    assert after.status_code == 404
    by_owner = await client.post(f"{BASE}/history", headers=owner.headers, json=_history(series_id, dashboard["id"]))
    assert by_owner.status_code == 404
    await client.delete(f"{settings.API_V1_STR}/connectors/{connector_id}", headers=lender.headers)
