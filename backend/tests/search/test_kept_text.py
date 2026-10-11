"""The text kept below the folders an owner chose, and the cell it answers
(D217–D219). A pass is run by calling the worker's own function.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.explorer.search import ExplorerSearch
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.search import keeper
from app.search.keep import SearchChunk, SearchContentFile
from app.search.kept_text import CHUNK_LINES, chunks_of
from app.users import crud
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
KEPT = f"{settings.API_V1_STR}/search/kept"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _home(client: AsyncClient, headers: dict[str, str]) -> Path:
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    home = settings.USER_STORAGE_ROOT / me.json()["id"]
    home.mkdir(parents=True, exist_ok=True)
    return home


async def _connector(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _pass(connector_id: str) -> None:
    async with async_session_maker() as session:
        connector = await session.get(Connector, uuid.UUID(connector_id))
    assert connector is not None
    await keeper.run_pass(connector)


async def _contents(
    client: AsyncClient, headers: dict[str, str], connector_id: str, node_id: str | None
) -> Response:
    return await client.post(
        f"{KEPT}/{connector_id}/contents", headers=headers, json={"node_id": node_id}
    )


async def _files(client: AsyncClient, headers: dict[str, str], home: Path) -> str:
    """A tree with text in docs/ and outside it, kept for names and docs/ for text."""
    (home / "docs" / "deep").mkdir(parents=True)
    (home / "other").mkdir()
    (home / "docs" / "notes.txt").write_text(
        "the quick brown fox\nwhere the auth token lives\n", encoding="utf-8"
    )
    (home / "docs" / "deep" / "split.txt").write_text("auth\ntoken\n", encoding="utf-8")
    (home / "docs" / "picture.bin").write_bytes(b"auth token\x00\x01")
    (home / "other" / "outside.txt").write_text("auth token outside\n", encoding="utf-8")
    connector_id = await _connector(client, headers, "file", {"path": "/"})
    kept = await client.put(
        f"{KEPT}/{connector_id}", headers=headers, json={"keep": True, "window_seconds": 3600}
    )
    assert kept.status_code == 200, kept.text
    await _pass(connector_id)
    added = await _contents(client, headers, connector_id, "docs")
    assert added.status_code == 200, added.text
    await _pass(connector_id)
    return connector_id


async def _search(
    client: AsyncClient, headers: dict[str, str], words: str, mode: str = "search"
) -> list[dict[str, Any]]:
    response = await client.post(SEARCH, headers=headers, json={"words": words, "mode": mode})
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def _cell(lines: list[dict[str, Any]], connector_id: str, field: str) -> dict[str, Any] | None:
    [plan] = [line for line in lines if line["type"] == "plan"]
    found = [
        cell
        for cell in plan["cells"]
        if cell["connector_id"] == connector_id and cell["cell"]["field"] == field
    ]
    if not found:
        return None
    [planned] = found
    finished = {line["key"]: line for line in lines if line["type"] == "cell"}
    return {**planned, **finished.get(planned["key"], {})}


async def _texts(connector_id: str) -> set[str]:
    async with async_session_maker() as session:
        rows = await session.exec(
            select(SearchChunk.node_id).where(
                col(SearchChunk.connector_id) == uuid.UUID(connector_id)
            )
        )
        return set(rows.all())


# --- what is kept, and how it is found -------------------------------------------


def test_chunks_carry_the_number_of_their_first_line() -> None:
    lines = [f"line {index}" for index in range(CHUNK_LINES + 5)]

    chunks = chunks_of(lines)

    assert [line for line, _ in chunks] == [1, CHUNK_LINES + 1]
    assert chunks[1][1].split("\n")[0] == f"line {CHUNK_LINES}"


async def test_words_inside_a_kept_folder_are_found_on_enter_with_their_line(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))

    lines = await _search(client, person, "token auth")
    cell = _cell(lines, connector_id, "contents")
    state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()

    assert cell is not None
    assert cell["way"] == "kept"
    assert cell["outcome"]["status"] == "complete"
    [hit] = cell["hits"]
    # Not split.txt, whose words are on two lines; not outside.txt, outside the
    # folder; not picture.bin, which is binary.
    assert hit["target"]["node_id"] == "docs/notes.txt"
    assert hit["match"]["field"] == "contents"
    assert hit["match"]["line"] == 2
    assert hit["via"] == "kept"
    assert [one["node_id"] for one in state["contents"]] == ["docs"]
    assert state["contents"][0]["files"] == 2
    assert state["contents"][0]["unread"] == 1
    assert await _texts(connector_id) == {"docs/notes.txt", "docs/deep/split.txt"}


async def test_kept_text_is_not_asked_while_typing(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))

    lines = await _search(client, person, "token auth", "typing")

    assert _cell(lines, connector_id, "contents") is None


async def test_an_unchanged_file_is_not_read_again_and_a_changed_one_is(
    client: AsyncClient, person: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await _home(client, person)
    connector_id = await _files(client, person, home)
    read: list[str] = []
    original = ExplorerSearch.extract_text

    async def counted(self: ExplorerSearch, node_id: str, bounds: Any) -> Any:
        read.append(node_id)
        return await original(self, node_id, bounds)

    monkeypatch.setattr(ExplorerSearch, "extract_text", counted)
    await _pass(connector_id)
    unchanged = list(read)
    (home / "docs" / "notes.txt").write_text("a different line entirely\n", encoding="utf-8")
    await _pass(connector_id)

    assert unchanged == []
    assert read == ["docs/notes.txt"]
    cell = _cell(await _search(client, person, "different entirely"), connector_id, "contents")
    assert cell is not None and len(cell["hits"]) == 1


async def test_a_file_whose_time_changed_and_text_did_not_keeps_its_chunks(
    client: AsyncClient, person: dict[str, str]
) -> None:
    home = await _home(client, person)
    connector_id = await _files(client, person, home)
    async with async_session_maker() as session:
        before = await session.get(SearchContentFile, (uuid.UUID(connector_id), "docs/notes.txt"))
    assert before is not None
    notes = home / "docs" / "notes.txt"
    stat = notes.stat()
    os.utime(notes, (stat.st_atime + 120, stat.st_mtime + 120))
    await _pass(connector_id)

    async with async_session_maker() as session:
        after = await session.get(SearchContentFile, (uuid.UUID(connector_id), "docs/notes.txt"))
    assert after is not None
    assert after.version != before.version
    assert after.digest == before.digest


async def test_a_deleted_file_s_text_goes_with_the_next_pass(
    client: AsyncClient, person: dict[str, str]
) -> None:
    home = await _home(client, person)
    connector_id = await _files(client, person, home)

    (home / "docs" / "notes.txt").unlink()
    await _pass(connector_id)

    assert await _texts(connector_id) == {"docs/deep/split.txt"}


async def test_a_folder_given_up_takes_its_text_and_keeps_what_another_covers(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))
    await _contents(client, person, connector_id, "docs/deep")
    await _pass(connector_id)

    after = await client.delete(
        f"{KEPT}/{connector_id}/contents", headers=person, params={"node_id": "docs"}
    )

    assert [one["node_id"] for one in after.json()["contents"]] == ["docs/deep"]
    assert await _texts(connector_id) == {"docs/deep/split.txt"}


async def test_stopping_the_names_takes_the_text_too(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))

    off = await client.put(f"{KEPT}/{connector_id}", headers=person, json={"keep": False})

    assert off.json()["contents"] == []
    assert await _texts(connector_id) == set()


async def test_the_whole_connection_can_be_its_scope(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))
    await _contents(client, person, connector_id, None)
    await _pass(connector_id)

    cell = _cell(await _search(client, person, "auth token"), connector_id, "contents")

    assert cell is not None
    assert {hit["target"]["node_id"] for hit in cell["hits"]} == {
        "docs/notes.txt",
        "other/outside.txt",
    }


async def test_editing_a_file_in_place_marks_the_list_stale(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person, await _home(client, person))
    opened = await client.post(
        f"{CONNECTORS}/{connector_id}/content/editor",
        headers=person,
        json={"node_id": "docs/notes.txt"},
    )

    saved = await client.patch(
        f"{CONNECTORS}/{connector_id}/content/editor",
        headers=person,
        json={"node_id": "docs/notes.txt", "text": "new\n", "version": opened.json()["version"]},
    )
    state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()

    assert saved.status_code == 200, saved.text
    assert state["stale"] is True


# --- who may, and what may be chosen ---------------------------------------------


async def test_choosing_what_is_kept_is_refused_where_it_cannot_be(
    client: AsyncClient, person: dict[str, str], db: AsyncSession
) -> None:
    home = await _home(client, person)
    (home / "docs").mkdir()
    (home / "docs" / "a.txt").write_text("x\n", encoding="utf-8")
    files = await _connector(client, person, "file", {"path": "/"})
    postgres = await _connector(client, person, "postgres", working_postgres_options())

    before_names = await _contents(client, person, files, "docs")
    await client.put(f"{KEPT}/{files}", headers=person, json={"keep": True})
    await _pass(files)
    not_a_folder = await _contents(client, person, files, "docs/a.txt")
    no_text = await _contents(client, person, postgres, None)

    email = random_email()
    theirs = await authentication_token_from_email(client=client, email=email, db=db)
    colleague = await crud.get_user_by_email(session=db, email=email)
    assert colleague is not None
    await client.put(
        f"{CONNECTORS}/{files}/grants",
        headers=person,
        json={"user_id": str(colleague.id), "access": "structure"},
    )
    grantee = await _contents(client, theirs, files, "docs")

    assert before_names.status_code == 409
    assert not_a_folder.status_code == 422
    assert no_text.status_code == 501
    assert grantee.status_code == 403
