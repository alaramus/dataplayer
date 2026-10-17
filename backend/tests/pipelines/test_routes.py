"""A person's pipelines: kept whole, private, bounded, and checked (D175)."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.pipelines.models import MAX_CARDS, MAX_PIPELINES, MAX_ROWS, Pipeline
from app.users import crud as user_crud
from app.users import storage
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/pipelines"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Pipeline))
        await session.commit()


@dataclass
class Person:
    id: uuid.UUID
    headers: dict[str, str]


async def _person(client: AsyncClient, db: AsyncSession) -> Person:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await user_crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return Person(id=user.id, headers=headers)


async def _files(client: AsyncClient, person: Person) -> str:
    """The person's own storage, as a connection."""
    response = await client.post(
        f"{CONNECTORS}/",
        headers=person.headers,
        json={"name": f"files {uuid.uuid4()}", "adapter_type": "file", "options": {"path": "/"}},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _node_ids(client: AsyncClient, person: Person, connector_id: str) -> dict[str, str]:
    """The ids of the top of a connection, by name, as its catalog gives them."""
    response = await client.get(f"{CONNECTORS}/{connector_id}/catalog", headers=person.headers)
    assert response.status_code == 200, response.text
    return {node["name"]: node["id"] for node in response.json()}


async def _create(client: AsyncClient, person: Person, name: str = "Nightly") -> dict[str, Any]:
    response = await client.post(BASE, headers=person.headers, json={"name": name})
    assert response.status_code == 200, response.text
    return dict(response.json())


def _card(connector_id: str, rows: list[dict[str, Any]], x: float = 0) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "connector_name": "Files",
        "x": x,
        "y": 40,
        "rows": rows,
    }


def _row(node_id: str | None, label: str = "orders.csv", kind: str | None = "file") -> dict[str, Any]:
    return {"node_id": node_id, "label": label, "kind": kind, "trail": []}


async def _save(
    client: AsyncClient, person: Person, pipeline: dict[str, Any], cards: list[dict[str, Any]],
    name: str | None = None,
) -> Any:
    return await client.put(
        f"{BASE}/{pipeline['id']}",
        headers=person.headers,
        json={"name": name or pipeline["name"], "version": pipeline["version"], "cards": cards},
    )


async def test_a_pipeline_is_made_listed_by_name_saved_and_removed(
    client: AsyncClient, db: AsyncSession
) -> None:
    person = await _person(client, db)
    files = await _files(client, person)
    second = await _create(client, person, "weekly")
    first = await _create(client, person, "Archive")
    assert first["cards"] == [] and first["version"] == 1

    listed = await client.get(BASE, headers=person.headers)
    assert [one["name"] for one in listed.json()] == ["Archive", "weekly"]

    card = _card(files, [_row(None, "Files", None), _row("orders.csv")], x=120.5)
    saved = await _save(client, person, second, [card], name="Weekly")
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["name"] == "Weekly" and body["version"] == 2
    assert body["cards"][0]["x"] == 120.5
    assert [row["node_id"] for row in body["cards"][0]["rows"]] == [None, "orders.csv"]

    again = await client.get(f"{BASE}/{second['id']}", headers=person.headers)
    assert again.json()["cards"] == body["cards"]

    removed = await client.delete(f"{BASE}/{second['id']}", headers=person.headers)
    assert removed.json() == {"message": "Weekly was removed"}
    assert (await client.get(f"{BASE}/{second['id']}", headers=person.headers)).status_code == 404


async def test_a_save_from_an_older_version_is_refused(client: AsyncClient, db: AsyncSession) -> None:
    person = await _person(client, db)
    pipeline = await _create(client, person)
    assert (await _save(client, person, pipeline, [])).status_code == 200

    stale = await _save(client, person, pipeline, [])

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "pipelines.changed"


async def test_somebody_else_is_told_there_is_no_such_pipeline(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await _person(client, db)
    stranger = await _person(client, db)
    pipeline = await _create(client, owner)
    address = f"{BASE}/{pipeline['id']}"

    assert (await client.get(BASE, headers=stranger.headers)).json() == []
    assert (await client.get(address, headers=stranger.headers)).status_code == 404
    assert (await _save(client, stranger, pipeline, [])).status_code == 404
    assert (await client.delete(address, headers=stranger.headers)).status_code == 404
    refused = await client.get(f"{address}/cards/{uuid.uuid4()}/state", headers=stranger.headers)
    assert refused.status_code == 404


async def test_a_person_keeps_a_bounded_number_of_pipelines(
    client: AsyncClient, db: AsyncSession
) -> None:
    person = await _person(client, db)
    async with async_session_maker() as session:
        for number in range(MAX_PIPELINES):
            session.add(Pipeline(owner_id=person.id, name=f"p{number}", content={"cards": []}))
        await session.commit()

    refused = await client.post(BASE, headers=person.headers, json={"name": "one more"})

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "pipelines.too_many"
    assert refused.json()["detail"]["params"] == {"limit": MAX_PIPELINES}


async def test_a_pipeline_is_bounded_and_says_nothing_twice(
    client: AsyncClient, db: AsyncSession
) -> None:
    person = await _person(client, db)
    files = await _files(client, person)
    pipeline = await _create(client, person)

    too_many_cards = [_card(files, [_row("a.csv")]) for _ in range(MAX_CARDS + 1)]
    too_many_rows = [_card(files, [_row(f"{n}.csv", f"{n}.csv") for n in range(MAX_ROWS + 1)])]
    twice = [_card(files, [_row("a.csv"), _row("a.csv")])]
    empty = [_card(files, [])]
    same_id = _card(files, [_row("a.csv")])
    stranger_field = {**_card(files, [_row("a.csv")]), "colour": "red"}

    for cards in (too_many_cards, too_many_rows, twice, empty, [same_id, same_id], [stranger_field]):
        answer = await _save(client, person, pipeline, cards)
        assert answer.status_code == 422, cards[0]


async def test_a_card_is_added_only_for_a_connection_the_person_can_read(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await _person(client, db)
    stranger = await _person(client, db)
    theirs = await _files(client, owner)
    pipeline = await _create(client, stranger)

    refused = await _save(client, stranger, pipeline, [_card(theirs, [_row("a.csv")])])

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "pipelines.card_unreadable"


async def test_a_card_kept_stays_when_its_connection_goes(client: AsyncClient, db: AsyncSession) -> None:
    person = await _person(client, db)
    files = await _files(client, person)
    pipeline = await _create(client, person)
    card = _card(files, [_row("a.csv")])
    kept = (await _save(client, person, pipeline, [card])).json()
    assert (await client.delete(f"{CONNECTORS}/{files}", headers=person.headers)).status_code == 200

    moved = await _save(client, person, kept, [{**card, "x": 300}])
    assert moved.status_code == 200, moved.text

    state = await client.get(f"{BASE}/{pipeline['id']}/cards/{card['id']}/state", headers=person.headers)
    assert state.json() == {
        "problem": "This connection is gone, or no longer shared with you",
        "missing": [],
        "checked": False,
    }


async def test_a_card_says_which_of_its_rows_are_gone(client: AsyncClient, db: AsyncSession) -> None:
    person = await _person(client, db)
    home = storage.home_dir(person.id)
    (home / "orders.csv").write_text("id\n1\n")
    (home / "reports").mkdir()
    files = await _files(client, person)
    ids = await _node_ids(client, person, files)
    pipeline = await _create(client, person)
    card = _card(files, [
        _row(None, "Files", None),
        _row(ids["orders.csv"]),
        _row(ids["reports"], "reports", "directory"),
        _row("gone.csv", "gone.csv"),
    ])
    await _save(client, person, pipeline, [card])
    address = f"{BASE}/{pipeline['id']}/cards/{card['id']}/state"

    state = await client.get(address, headers=person.headers)

    assert state.status_code == 200, state.text
    assert state.json() == {"problem": None, "missing": ["gone.csv"], "checked": True}
    (home / "orders.csv").unlink()
    assert (await client.get(address, headers=person.headers)).json()["missing"] == [
        ids["orders.csv"], "gone.csv",
    ]
    assert (await client.get(
        f"{BASE}/{pipeline['id']}/cards/{uuid.uuid4()}/state", headers=person.headers
    )).status_code == 404


async def test_a_card_of_a_connection_switched_off_says_so(client: AsyncClient, db: AsyncSession) -> None:
    person = await _person(client, db)
    files = await _files(client, person)
    pipeline = await _create(client, person)
    card = _card(files, [_row("a.csv")])
    await _save(client, person, pipeline, [card])
    switched = await client.patch(f"{CONNECTORS}/{files}", headers=person.headers, json={"enabled": False})
    assert switched.status_code == 200, switched.text

    state = await client.get(f"{BASE}/{pipeline['id']}/cards/{card['id']}/state", headers=person.headers)

    assert state.json()["problem"] == "This connection is switched off"


async def test_a_pipeline_that_no_longer_reads_is_shown_empty_and_broken(
    client: AsyncClient, db: AsyncSession
) -> None:
    person = await _person(client, db)
    async with async_session_maker() as session:
        broken = Pipeline(owner_id=person.id, name="Old", content={"cards": [{"what": "is this"}]})
        session.add(broken)
        await session.commit()
        await session.refresh(broken)

    answer = await client.get(f"{BASE}/{broken.id}", headers=person.headers)

    assert answer.status_code == 200
    assert answer.json()["broken"] is True and answer.json()["cards"] == []
