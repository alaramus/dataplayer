"""What was opened from the search lately, named again only where it may be (S6)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.search.engine import _recent_key
from app.search.models import (
    MAX_NODE_NAME,
    ConnectionTarget,
    NodeTarget,
    ObjectTarget,
    RecentTarget,
    recent_target,
    target_key,
)
from tests.utils.search import SEARCH, connection, grant, hits, person, search

CONNECTORS = f"{settings.API_V1_STR}/connectors"
PIPELINES = f"{settings.API_V1_STR}/pipelines"


def _connection(connector_id: str) -> dict[str, Any]:
    return {"kind": "connection", "connector_id": connector_id}


def _node(connector_id: str, node_id: str = "public.orders") -> dict[str, Any]:
    return {
        "kind": "node",
        "connector_id": connector_id,
        "node_id": node_id,
        "name": node_id.rsplit(".", 1)[-1],
        "node_kind": "table",
    }


def _object(object_type: str, object_id: str) -> dict[str, Any]:
    return {"kind": "object", "object_type": object_type, "object_id": object_id}


async def _pipeline(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post(PIPELINES, headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _empty(client: AsyncClient, headers: dict[str, str], recent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return await search(client, headers, "", mode="typing", recent=recent)


def _keys(lines: list[dict[str, Any]]) -> list[str]:
    return [hit["key"] for hit in hits(lines)]


# --- one key for a thing, however it was kept ---------------------------------


def test_a_kept_target_has_the_key_its_hit_has() -> None:
    connector_id = uuid.uuid4()
    pairs = [
        (
            RecentTarget(kind="connection", connector_id=connector_id),
            ConnectionTarget(connector_id=connector_id),
        ),
        (
            RecentTarget(kind="node", connector_id=connector_id, node_id="public.orders"),
            NodeTarget(connector_id=connector_id, node_id="public.orders", name="orders", node_kind="table"),
        ),
        (
            RecentTarget(kind="object", object_type="pipeline", object_id="p-1"),
            ObjectTarget(object_type="pipeline", object_id="p-1"),
        ),
        (
            RecentTarget(kind="object", object_type="tab", object_id="panel-3"),
            ObjectTarget(object_type="tab", object_id="panel-3"),
        ),
    ]

    for kept, found in pairs:
        assert _recent_key(kept) == target_key(found)


@pytest.mark.parametrize(
    "kept",
    [
        RecentTarget(kind="connection"),
        RecentTarget(kind="node", connector_id=uuid.uuid4()),
        RecentTarget(kind="object", object_type="pipeline"),
    ],
)
def test_a_kept_target_that_is_not_whole_names_nothing(kept: RecentTarget) -> None:
    assert recent_target(kept) is None
    assert _recent_key(kept) is None


# --- the empty search ----------------------------------------------------------


async def test_an_empty_search_lists_what_was_opened_newest_first(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Sales {marker}")
    pipeline_id = await _pipeline(client, owner.headers, f"Load {marker}")

    lines = await _empty(
        client,
        owner.headers,
        [
            _object("pipeline", pipeline_id),
            _node(connector_id),
            _connection(connector_id),
            _object("pipeline", pipeline_id),
            _object("guide_page", "connections"),
            _object("source_type", "postgres"),
        ],
    )

    [plan] = [line for line in lines if line["type"] == "plan"]
    assert [cell["key"] for cell in plan["cells"]] == ["objects:recent/names"]
    assert _keys(lines) == [
        f"object:pipeline:{pipeline_id}",
        f"node:{connector_id}:public.orders:",
        f"connection:{connector_id}",
        "object:guide_page:connections",
        "object:source_type:postgres",
    ]
    [pipeline, node, row, page, source_type] = hits(lines)
    assert pipeline["title"] == f"Load {marker}"
    assert node["title"] == "orders"
    assert node["detail"] == f"Sales {marker}"
    assert node["open"] == "preferred"
    assert row["title"] == f"Sales {marker}"
    assert page["open"] == "guide_page"
    assert source_type["title"] == "PostgreSQL"
    # Nothing was typed, so nothing is marked and nothing is a best match.
    assert not any(part["hit"] for hit in hits(lines) for part in hit["match"]["excerpt"])
    [best] = [line for line in lines if line["type"] == "best"]
    assert best["hits"] == []


async def test_a_long_name_kept_by_the_browser_is_cut_rather_than_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    connector_id = await connection(client, owner.headers, f"Keys {uuid.uuid4().hex[:8]}")
    name = "session:" + "x" * (MAX_NODE_NAME + 500)
    kept = {**_node(connector_id, "0:" + name), "name": name, "node_kind": "key"}

    [node] = hits(await _empty(client, owner.headers, [kept]))

    assert node["title"] == name[:MAX_NODE_NAME]
    assert node["target"]["node_id"] == "0:" + name


@pytest.mark.parametrize(
    "body",
    [
        {"words": "", "mode": "typing"},
        {"words": "   ", "mode": "typing", "recent": []},
        {"words": "a", "mode": "typing", "recent": [{"kind": "connection", "connector_id": str(uuid.uuid4())}]},
    ],
)
async def test_what_an_empty_search_refuses(
    client: AsyncClient, normal_user_token_headers: dict[str, str], body: dict[str, Any]
) -> None:
    response = await client.post(SEARCH, headers=normal_user_token_headers, json=body)

    assert response.status_code == 422


async def test_after_a_grant_is_revoked_nothing_of_the_connection_is_named(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    reader = await person(client, db)
    connector_id = await connection(client, owner.headers, f"Shared {uuid.uuid4().hex[:8]}")
    await grant(client, owner.headers, connector_id, reader)
    recent = [_node(connector_id), _connection(connector_id)]
    assert _keys(await _empty(client, reader.headers, recent)) == [
        f"node:{connector_id}:public.orders:",
        f"connection:{connector_id}",
    ]

    revoked = await client.delete(
        f"{CONNECTORS}/{connector_id}/grants/{reader.id}", headers=owner.headers
    )
    assert revoked.status_code == 200, revoked.text

    assert _keys(await _empty(client, reader.headers, recent)) == []


async def test_after_a_connection_is_switched_off_nothing_inside_it_is_named(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    connector_id = await connection(client, owner.headers, f"Paused {uuid.uuid4().hex[:8]}")
    switched = await client.patch(
        f"{CONNECTORS}/{connector_id}", headers=owner.headers, json={"enabled": False}
    )
    assert switched.status_code == 200, switched.text

    lines = await _empty(client, owner.headers, [_node(connector_id), _connection(connector_id)])

    # The connection is found by its name, switched off (D20); its nodes are not.
    [row] = hits(lines)
    assert row["key"] == f"connection:{connector_id}"
    assert row["facts"]["switched_off"] is True


async def test_a_hint_naming_another_person_s_things_changes_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    theirs = await connection(client, owner.headers, f"Vault {marker}")
    their_pipeline = await _pipeline(client, owner.headers, f"Vault {marker} load")
    unknown = str(uuid.uuid4())

    hinted = [_connection(theirs), _node(theirs), _object("pipeline", their_pipeline)]
    unhinted = [_connection(unknown), _node(unknown), _object("pipeline", unknown)]

    assert _answer(await _empty(client, stranger.headers, hinted)) == _answer(
        await _empty(client, stranger.headers, unhinted)
    )
    assert _answer(
        await search(client, stranger.headers, f"vault {marker}", recent=hinted)
    ) == _answer(await search(client, stranger.headers, f"vault {marker}", recent=unhinted))
    assert _keys(await _empty(client, stranger.headers, hinted)) == []


def _answer(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """An answer as what it says, apart from the order its cells finished in."""
    return {
        "lines": [line for line in lines if line["type"] != "cell"],
        "cells": {line["key"]: line for line in lines if line["type"] == "cell"},
    }


# --- recency orders the best matches ------------------------------------------


async def test_what_was_opened_comes_back_first_among_the_best_matches(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    first = await connection(client, owner.headers, f"{marker} alpha")
    second = await connection(client, owner.headers, f"{marker} beta")

    plain = await search(client, owner.headers, marker, mode="typing")
    opened = await search(
        client, owner.headers, marker, mode="typing", recent=[_connection(second)]
    )

    def best(lines: list[dict[str, Any]]) -> list[str]:
        [line] = [one for one in lines if one["type"] == "best"]
        return [hit["key"] for hit in line["hits"]]

    assert best(plain)[:2] == [f"connection:{first}", f"connection:{second}"]
    assert best(opened)[:2] == [f"connection:{second}", f"connection:{first}"]
