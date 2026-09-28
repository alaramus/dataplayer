"""Dashboards: stored whole, versioned, validated, and read through their owner (D129)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.metrics.dashboards import Dashboard, DashboardContent, public
from app.metrics.models import MetricsAgent, MetricsStoreSetting
from app.metrics.store import MetricsStore, SeriesKey, Source
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/metrics"


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Dashboard))
        await session.exec(delete(MetricsStoreSetting))
        await session.exec(delete(MetricsAgent))
        await session.commit()


@pytest.fixture
async def stranger_headers(client: AsyncClient, db: Any) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


def _widget(series_ids: list[int], **layout: int) -> dict[str, Any]:
    return {
        "type": "timeseries",
        "id": str(uuid.uuid4()),
        "title": "CPU",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 5, **layout},
        "series_ids": series_ids,
    }


async def _create(client: AsyncClient, headers: dict[str, str], name: str = "Hosts") -> dict[str, Any]:
    response = await client.post(f"{BASE}/dashboards", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_new_dashboard_is_empty_and_its_owner_s(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    created = await _create(client, normal_user_token_headers)

    assert created["widgets"] == []
    assert created["options"] == {"range_seconds": 900, "refresh_seconds": 30}
    assert created["version"] == 1
    listed = await client.get(f"{BASE}/dashboards", headers=normal_user_token_headers)
    assert [one["id"] for one in listed.json()] == [created["id"]]
    assert (await client.get(f"{BASE}/dashboards", headers=stranger_headers)).json() == []
    foreign = await client.get(f"{BASE}/dashboards/{created['id']}", headers=stranger_headers)
    assert foreign.status_code == 404


async def test_a_new_dashboard_is_not_made_while_the_owner_has_an_empty_one(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    first = await _create(client, normal_user_token_headers, "First")

    again = await _create(client, normal_user_token_headers, "Second")
    theirs = await _create(client, stranger_headers, "Theirs")

    assert again["id"] == first["id"]
    assert again["name"] == "First"
    assert theirs["id"] != first["id"]

    # Written past the route: a widget needs a store to name a series.
    async with async_session_maker() as session:
        row = await session.get(Dashboard, uuid.UUID(first["id"]))
        assert row is not None
        row.content = {**row.content, "widgets": [_widget([1])]}
        session.add(row)
        await session.commit()
    third = await _create(client, normal_user_token_headers, "Third")

    assert third["id"] != first["id"]
    listed = (await client.get(f"{BASE}/dashboards", headers=normal_user_token_headers)).json()
    assert [one["name"] for one in listed] == ["First", "Third"]


async def test_saving_replaces_the_whole_and_raises_the_version(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _create(client, normal_user_token_headers)
    body = {
        "name": "Renamed",
        "version": 1,
        "options": {"range_seconds": 3600, "refresh_seconds": 0},
        "widgets": [],
    }

    saved = await client.put(
        f"{BASE}/dashboards/{created['id']}", headers=normal_user_token_headers, json=body
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["name"] == "Renamed"
    assert saved.json()["options"]["range_seconds"] == 3600
    assert saved.json()["version"] == 2
    stale = await client.put(
        f"{BASE}/dashboards/{created['id']}", headers=normal_user_token_headers, json=body
    )
    assert stale.status_code == 409


async def test_a_colour_is_saved_with_the_rest_and_taken_away_by_a_save_without_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _create(client, normal_user_token_headers)
    url = f"{BASE}/dashboards/{created['id']}"
    body = {"name": "Hosts", "version": 1, "widgets": []}

    assert created["color"] is None
    coloured = await client.put(url, headers=normal_user_token_headers, json={**body, "color": "#1E88E5"})
    assert coloured.status_code == 200, coloured.text
    assert coloured.json()["color"] == "#1E88E5"
    listed = (await client.get(f"{BASE}/dashboards", headers=normal_user_token_headers)).json()
    assert [one["color"] for one in listed] == ["#1E88E5"]

    for wrong in ("blue", "#12345", "#1234567", "#GGGGGG"):
        refused = await client.put(url, headers=normal_user_token_headers, json={**body, "version": 2, "color": wrong})
        assert refused.status_code == 422, wrong

    cleared = await client.put(url, headers=normal_user_token_headers, json={**body, "version": 2})
    assert cleared.json()["color"] is None


async def test_what_the_grid_cannot_hold_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _create(client, normal_user_token_headers)
    url = f"{BASE}/dashboards/{created['id']}"
    base = {"name": "x", "version": 1, "options": {"range_seconds": 900, "refresh_seconds": 30}}

    too_wide = await client.put(url, headers=normal_user_token_headers, json={**base, "widgets": [_widget([1], x=8, w=6)]})
    odd_range = await client.put(
        url,
        headers=normal_user_token_headers,
        json={**base, "options": {"range_seconds": 1234, "refresh_seconds": 30}, "widgets": []},
    )
    unknown = await client.put(
        url, headers=normal_user_token_headers, json={**base, "widgets": [{**_widget([1]), "type": "pie"}]}
    )
    twenty_one = await client.put(
        url, headers=normal_user_token_headers, json={**base, "widgets": [_widget([1]) for _ in range(21)]}
    )

    assert {too_wide.status_code, odd_range.status_code, unknown.status_code, twenty_one.status_code} == {422}


async def test_a_widget_needs_a_store_to_name_a_series(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await _create(client, normal_user_token_headers)

    response = await client.put(
        f"{BASE}/dashboards/{created['id']}",
        headers=normal_user_token_headers,
        json={"name": "x", "version": 1, "widgets": [_widget([1])]},
    )

    assert response.status_code == 409


async def test_a_dashboard_is_removed_by_its_owner(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    created = await _create(client, normal_user_token_headers)

    refused = await client.delete(f"{BASE}/dashboards/{created['id']}", headers=stranger_headers)
    removed = await client.delete(f"{BASE}/dashboards/{created['id']}", headers=normal_user_token_headers)

    assert refused.status_code == 404
    assert removed.status_code == 200
    assert (await client.get(f"{BASE}/dashboards", headers=normal_user_token_headers)).json() == []


def test_content_that_no_longer_reads_is_shown_empty_and_marked() -> None:
    row = Dashboard(owner_id=uuid.uuid4(), name="old", content={"widgets": [{"type": "gauge"}]})

    shown = public(row)

    assert shown.broken is True
    assert shown.widgets == []
    assert public(Dashboard(owner_id=uuid.uuid4(), name="new", content=DashboardContent().model_dump(mode="json"))).broken is False


async def test_a_widget_may_name_only_series_its_saver_can_read(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
    store_options: dict[str, Any],
    store: MetricsStore,
) -> None:
    connected = await client.post(
        f"{BASE}/store/connect", headers=superuser_token_headers, json={"options": store_options}
    )
    assert connected.status_code == 200, connected.text
    agent = await client.post(f"{BASE}/agents", headers=normal_user_token_headers, json={"name": "web"})
    agent_id = uuid.UUID(agent.json()["agent"]["id"])
    key = SeriesKey("web-01", "cpu", "cpu", "total")
    series_id = (await store.series_ids(Source("agent", agent_id), [(key, "%", 1_789_000_000)]))[key]

    mine = await _create(client, normal_user_token_headers)
    saved = await client.put(
        f"{BASE}/dashboards/{mine['id']}",
        headers=normal_user_token_headers,
        json={"name": "x", "version": 1, "widgets": [_widget([series_id])]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["widgets"][0]["series_ids"] == [series_id]

    theirs = await _create(client, stranger_headers)
    refused = await client.put(
        f"{BASE}/dashboards/{theirs['id']}",
        headers=stranger_headers,
        json={"name": "x", "version": 1, "widgets": [_widget([series_id])]},
    )
    assert refused.status_code == 422


async def test_a_process_table_may_name_only_an_agent_its_saver_owns(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    agent = await client.post(f"{BASE}/agents", headers=normal_user_token_headers, json={"name": "web"})
    table = {
        "type": "processes",
        "id": str(uuid.uuid4()),
        "title": "Top processes",
        "layout": {"x": 0, "y": 0, "w": 12, "h": 8},
        "agent_id": agent.json()["agent"]["id"],
        "host": "web-01",
        "sort": "pmem",
        "limit": 50,
    }

    mine = await _create(client, normal_user_token_headers)
    saved = await client.put(
        f"{BASE}/dashboards/{mine['id']}",
        headers=normal_user_token_headers,
        json={"name": "x", "version": 1, "widgets": [table]},
    )
    theirs = await _create(client, stranger_headers)
    refused = await client.put(
        f"{BASE}/dashboards/{theirs['id']}",
        headers=stranger_headers,
        json={"name": "x", "version": 1, "widgets": [table]},
    )
    odd = await client.put(
        f"{BASE}/dashboards/{mine['id']}",
        headers=normal_user_token_headers,
        json={"name": "x", "version": 2, "widgets": [{**table, "limit": 7}]},
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["widgets"][0]["sort"] == "pmem"
    assert refused.status_code == 422
    assert odd.status_code == 422
