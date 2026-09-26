"""Links of a pipeline: kept with its cards, run as Paste runs, hinted (D176)."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.main import app
from app.pipelines import hint as hint_module
from app.pipelines.models import Pipeline, PipelineRun
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/pipelines"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Pipeline))
        await session.commit()


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "reports").mkdir(exist_ok=True)
    return home


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(f"INSERT INTO {name}.regions VALUES (1, 'EU'), (2, 'US')")  # noqa: S608 -- a fixture's own schema name
        yield name


async def _connector(client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={"name": f"{adapter_type} {uuid.uuid4()}", "adapter_type": adapter_type, "options": options},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _card(connector_id: str, rows: list[tuple[str | None, str, str | None]], x: float = 0) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "connector_name": "a connection",
        "x": x,
        "y": 0,
        "rows": [{"node_id": node, "label": label, "kind": kind, "trail": []} for node, label, kind in rows],
    }


def _link(source: dict[str, Any], source_node: str | None, target: dict[str, Any], target_node: str | None, kind: str, **choices: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source": {"card_id": source["id"], "node_id": source_node},
        "target": {"card_id": target["id"], "node_id": target_node},
        "kind": kind,
        "title": kind.replace("_", " "),
        **choices,
    }


class Canvas:
    """One pipeline of the test user, saved whole as the screen saves it."""

    def __init__(self, client: AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.id = ""
        self.version = 0

    async def make(self) -> Canvas:
        made = await self.client.post(BASE, headers=self.headers, json={"name": "Nightly"})
        assert made.status_code == 200, made.text
        self.id, self.version = made.json()["id"], made.json()["version"]
        return self

    async def save(self, cards: list[dict[str, Any]], links: list[dict[str, Any]]) -> Any:
        answer = await self.client.put(
            f"{BASE}/{self.id}",
            headers=self.headers,
            json={"name": "Nightly", "version": self.version, "cards": cards, "links": links},
        )
        if answer.status_code == 200:
            self.version = answer.json()["version"]
        return answer

    async def run(self, link: dict[str, Any]) -> dict[str, Any]:
        answer = await self.client.post(f"{BASE}/{self.id}/links/{link['id']}/run", headers=self.headers)
        assert answer.status_code == 200, answer.text
        result: dict[str, Any] = answer.json()
        return result

    async def runs(self) -> dict[str, dict[str, Any]]:
        answer = await self.client.get(f"{BASE}/{self.id}/runs", headers=self.headers)
        assert answer.status_code == 200, answer.text
        return {one["link_id"]: one for one in answer.json()}

    async def hint(self, card_id: str | None = None) -> dict[str, Any]:
        answer = await self.client.post(f"{BASE}/{self.id}/hint", headers=self.headers, json={"card_id": card_id})
        assert answer.status_code == 200, answer.text
        result: dict[str, Any] = answer.json()
        return result


async def test_links_are_kept_with_the_rows_they_join(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    files = await _connector(client, headers, "file", {"path": "/"})
    other_files = await _connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    left = _card(files, [("a.csv", "a.csv", "file"), (None, "Files", None)])
    right = _card(other_files, [("reports", "reports", "directory"), (None, "Files", None)], x=400)
    same = _card(files, [("reports", "reports", "directory")], x=800)
    link = _link(left, "a.csv", right, "reports", "file_copy", conflict="rename")
    into_top = _link(left, "a.csv", right, None, "file_move")

    saved = await canvas.save([left, right, same], [link, into_top])

    assert saved.status_code == 200, saved.text
    kept = saved.json()["links"]
    assert [one["id"] for one in kept] == [link["id"], into_top["id"]]
    assert kept[0]["conflict"] == "rename" and kept[1]["conflict"] == "refuse"
    for broken in (
        [_link(left, "a.csv", {"id": str(uuid.uuid4())}, "reports", "file_copy")],
        [_link(left, "b.csv", right, "reports", "file_copy")],
        [_link(left, None, right, "reports", "file_copy")],
        [_link(left, "a.csv", same, "reports", "file_copy")],
        [link, {**link, "id": str(uuid.uuid4())}],
        [{**link, "kind": "teleport"}],
    ):
        refused = await canvas.save([left, right, same], broken)
        assert refused.status_code == 422, broken


async def test_a_link_runs_as_its_paste_and_keeps_what_became_of_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    database = await _connector(client, headers, "postgres", working_postgres_options())
    files = await _connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = _card(database, [(f"{schema}.regions", "regions", "table")])
    folder = _card(files, [("reports", "reports", "directory")], x=400)
    name = f"regions-{uuid.uuid4().hex}.csv"
    link = _link(tables, f"{schema}.regions", folder, "reports", "relation_csv", name=name)
    await canvas.save([tables, folder], [link])

    started = await canvas.run(link)

    assert started["run"]["outcome"] == "running"
    job_id = started["job"]["id"]
    assert started["run"]["job_id"] == job_id
    await app.state.job_runner.wait_for(uuid.UUID(job_id))
    done = (await canvas.runs())[link["id"]]
    assert (done["outcome"], done["message"]) == ("done", f"{name} saved in reports with 2 rows")
    assert done["finished_at"] is not None
    assert (home / "reports" / name).read_bytes().startswith(b'\xef\xbb\xbf"id","code"')

    # Run again by the same choices: the name is taken now, and that is what
    # the link says rather than what the route answers.
    again = await canvas.run(link)
    assert again["job"] is None
    assert again["run"]["outcome"] == "failed"
    assert name in again["run"]["message"]
    assert (await canvas.runs())[link["id"]]["outcome"] == "failed"

    # A choice kept with the link is what the next run goes by.
    await canvas.save([tables, folder], [{**link, "conflict": "rename"}])
    renamed = await canvas.run(link)
    await app.state.job_runner.wait_for(uuid.UUID(renamed["job"]["id"]))
    assert (await canvas.runs())[link["id"]]["outcome"] == "done"


async def test_rows_run_in_the_request_and_ask_for_their_columns(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,name\n1,Ada\n2,Grace\n")
    files = await _connector(client, headers, "file", {"path": "/"})
    database = await _connector(client, headers, "postgres", working_postgres_options())
    canvas = await Canvas(client, headers).make()
    csv = _card(files, [(filename, filename, "file")])
    place = _card(database, [(schema, schema, "schema")], x=400)
    bare = _link(csv, filename, place, schema, "rows_new_relation")
    await canvas.save([csv, place], [bare])

    unset = await canvas.run(bare)
    assert unset["run"] == {**unset["run"], "outcome": "failed", "message": "Name the table and choose its columns"}

    chosen = {
        **bare,
        "name": "linked_people",
        "columns": [
            {"source": "id", "target": "id", "type_code": "text"},
            {"source": "name", "target": "who", "type_code": "text"},
        ],
    }
    await canvas.save([csv, place], [chosen])
    made = await canvas.run(chosen)
    assert made["job"] is None
    assert (made["run"]["outcome"], made["run"]["message"]) == ("done", "linked_people created with 2 rows")


async def test_the_runs_of_links_taken_away_are_forgotten(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    files = await _connector(client, headers, "file", {"path": "/"})
    gone = await _connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    left = _card(files, [("a.csv", "a.csv", "file")])
    right = _card(gone, [("reports", "reports", "directory")], x=400)
    link = _link(left, "a.csv", right, "reports", "file_copy")
    await canvas.save([left, right], [link])
    assert (await client.delete(f"{CONNECTORS}/{gone}", headers=headers)).status_code == 200

    failed = await canvas.run(link)

    assert failed["run"]["outcome"] == "failed"
    assert failed["run"]["message"] == "A connection of this link is gone, or no longer shared with you"
    await canvas.save([left, right], [])
    assert await canvas.runs() == {}
    async with async_session_maker() as session:
        left_over = await session.exec(select(PipelineRun).where(PipelineRun.link_id == uuid.UUID(link["id"])))
        assert left_over.all() == []


def _hinted(answer: dict[str, Any]) -> set[tuple[str | None, str | None, tuple[str, ...]]]:
    return {
        (one["source"]["node_id"], one["target"]["node_id"], tuple(one["titles"]))
        for one in answer["links"]
    }


async def test_the_hint_draws_every_link_the_rows_can_make(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n7,AS\n")
    database = await _connector(client, headers, "postgres", working_postgres_options())
    files = await _connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = _card(database, [(schema, schema, "schema"), (f"{schema}.regions", "regions", "table")])
    storage_card = _card(files, [("reports", "reports", "directory"), (filename, filename, "file")], x=400)
    drawn = _link(storage_card, filename, tables, f"{schema}.regions", "rows_into_relation")
    await canvas.save([tables, storage_card], [drawn])

    answer = await canvas.hint()

    assert answer["notice"] is None
    assert _hinted(answer) == {
        (f"{schema}.regions", "reports", ("Save as CSV",)),
        (filename, schema, ("Create a table",)),
    }


@pytest.mark.usefixtures("home")
async def test_a_canvas_too_large_to_hint_whole_hints_the_selected_card(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = normal_user_token_headers
    database = await _connector(client, headers, "postgres", working_postgres_options())
    files = await _connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = _card(database, [(f"{schema}.regions", "regions", "table")])
    first = _card(files, [("reports", "reports", "directory")], x=400)
    second = _card(files, [("reports", "reports", "directory")], x=800)
    await canvas.save([tables, first, second], [])
    # Four pairs of rows in all, two of them the first card's.
    monkeypatch.setattr(hint_module, "MAX_HINT_PAIRS", 2)

    whole = await canvas.hint()
    assert whole == {
        "links": [],
        "notice": "This canvas holds too many rows to hint at once: select a card first",
    }

    selected = await canvas.hint(first["id"])
    assert selected["notice"] == "Only the links of the selected card are hinted"
    assert [(one["source"]["card_id"], one["target"]["card_id"]) for one in selected["links"]] == [
        (tables["id"], first["id"]),
    ]
