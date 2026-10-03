"""Words inside files, looked for as a job (S7).

The words and the matches live in the process's memory; the job's row, the
listing of jobs and the log never see the words.
"""

import asyncio
import io
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from anyio import to_thread
from httpx import AsyncClient
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.search import NodeSearchRequest, NodeSearchResult, SearchBounds
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.runner import JobRunner, recover_interrupted
from app.main import app
from app.search import contents
from app.search.contents import ContentsMemory
from tests.utils import services
from tests.utils.ssh import pinned_key
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

API = settings.API_V1_STR
CONTENTS = f"{API}/search/contents"
MARKER = f"wombat{uuid.uuid4().hex[:8]}"


def _runner() -> JobRunner:
    runner: JobRunner = app.state.job_runner
    return runner


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _home(client: AsyncClient, headers: dict[str, str]) -> Path:
    me = await client.get(f"{API}/users/me", headers=headers)
    home = settings.USER_STORAGE_ROOT / me.json()["id"]
    home.mkdir(parents=True, exist_ok=True)
    return home


async def _connector(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]
) -> str:
    response = await client.post(
        f"{API}/connectors/",
        headers=headers,
        json={
            "name": f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _files(client: AsyncClient, headers: dict[str, str]) -> str:
    """A connection to the person's files, one of which holds the marker on line 3."""
    home = await _home(client, headers)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "diary.txt").write_bytes(
        f"first line\nsecond line\nalpha {MARKER} omega\n".encode()
    )
    (home / "notes" / "other.txt").write_bytes(b"nothing here\n")
    return await _connector(client, headers, "file", {"path": "/"})


async def _start(
    client: AsyncClient, headers: dict[str, str], *connector_ids: str, words: str = MARKER
) -> dict[str, Any]:
    response = await client.post(
        CONTENTS, headers=headers, json={"words": words, "connector_ids": list(connector_ids)}
    )
    assert response.status_code == 200, response.text
    job: dict[str, Any] = response.json()
    return job


async def _finished(client: AsyncClient, headers: dict[str, str], job_id: str) -> dict[str, Any]:
    await _runner().wait_for(uuid.UUID(job_id))
    response = await client.get(f"{API}/jobs/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    job: dict[str, Any] = response.json()
    return job


async def _answer(client: AsyncClient, headers: dict[str, str], job_id: str) -> dict[str, Any]:
    response = await client.get(f"{CONTENTS}/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    answer: dict[str, Any] = response.json()
    return answer


async def test_a_word_inside_a_local_file_is_found_with_its_line_and_written_nowhere(
    client: AsyncClient, person: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    connector_id = await _files(client, person)

    started = await _start(client, person, connector_id)
    job = await _finished(client, person, started["id"])
    answer = await _answer(client, person, started["id"])
    listed = await client.get(f"{API}/jobs/", headers=person)

    assert started["kind"] == "search.contents"
    assert job["state"] == "succeeded", job
    assert job["message"] == "1 match found in 1 connection"
    assert job["parameters"]["found"] == 1
    assert answer["held"] and answer["finished"]
    [hit] = answer["hits"]
    assert hit["target"]["name"] == "diary.txt"
    assert hit["target"]["parent_id"] == "notes"
    assert hit["match"]["field"] == "contents"
    assert hit["match"]["line"] == 3
    assert [one["text"] for one in hit["match"]["excerpt"] if one["hit"]] == [MARKER]
    assert answer["places"][0]["status"] == "complete"
    # The row, the listing and the log: never the words.
    async with async_session_maker() as session:
        row = await session.get(Job, uuid.UUID(started["id"]))
    assert row is not None
    assert MARKER not in json.dumps(row.model_dump(mode="json"))
    assert MARKER not in listed.text
    logged = [record.getMessage() for record in caplog.records if record.name != "httpx"]
    assert not [line for line in logged if MARKER in line]


class _Payload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._data.read(size)


@pytest.fixture
async def ssh_folder() -> AsyncGenerator[dict[str, Any]]:
    """A folder of this test's own on the development SSH server, holding a
    file with the marker on its second line."""
    parts = urlsplit(services.SSH.require())
    server: dict[str, Any] = {
        "auth_method": "password",
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }
    server["host_key"] = await pinned_key(str(server["host"]), int(server["port"]))
    name = f"test-{uuid.uuid4().hex[:12]}"
    options = SshPassword.model_validate({**server, "path": name})
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    context = registry.AdapterContext(
        home_dir=Path("."), pooling=Pooling(store=store, connector_id=uuid.uuid4())
    )
    home = SshAdapter(options.model_copy(update={"path": ""}), context)
    await home.action("create_folder").perform(None, {"name": name})
    try:
        await SshAdapter(options, context).action("upload").perform_with_file(
            None, {"conflict": "refuse"}, _Payload("remote.log", f"start\nsaw {MARKER} here\n".encode())
        )
        yield {**server, "path": name}
    finally:
        await home.action("delete").perform(name, {})
        await store.aclose()


async def test_a_word_inside_a_file_over_ssh_is_found_with_its_line(
    client: AsyncClient, person: dict[str, str], ssh_folder: dict[str, Any]
) -> None:
    remote = await _connector(client, person, "ssh", ssh_folder)
    local = await _files(client, person)

    started = await _start(client, person, local, remote)
    job = await _finished(client, person, started["id"])
    answer = await _answer(client, person, started["id"])

    assert job["state"] == "succeeded", job
    found = {(hit["target"]["connector_id"], hit["target"]["name"], hit["match"]["line"]) for hit in answer["hits"]}
    assert found == {(local, "diary.txt", 3), (remote, "remote.log", 2)}
    assert job["parameters"]["searched"] == 2


class _Lingering:
    """A real source that, having found what it found, waits to be stopped."""

    def __init__(self, inner: Any, found: asyncio.Event) -> None:
        self._inner = inner
        self._found = found

    async def search_contents(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        result: NodeSearchResult = await self._inner.search_contents(request)
        self._found.set()
        limit = time.monotonic() + 30

        def wait() -> None:
            while bounds is not None and not bounds.stopped() and time.monotonic() < limit:
                time.sleep(0.01)

        await to_thread.run_sync(wait)
        return result


@pytest.fixture
def lingering(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    found = asyncio.Event()
    real: Callable[..., Any] = contents.adapter_of
    monkeypatch.setattr(
        contents, "adapter_of", lambda connection, store: _Lingering(real(connection, store), found)
    )
    return found


async def test_stop_ends_the_job_with_what_was_found_and_one_runs_at_a_time(
    client: AsyncClient, person: dict[str, str], lingering: asyncio.Event
) -> None:
    connector_id = await _files(client, person)
    started = await _start(client, person, connector_id)
    await asyncio.wait_for(lingering.wait(), timeout=10)

    working = await client.get(f"{API}/jobs/", headers=person)
    second = await client.post(
        CONTENTS, headers=person, json={"words": MARKER, "connector_ids": [connector_id]}
    )
    cancel = await client.post(f"{API}/jobs/{started['id']}/cancel", headers=person)
    job = await _finished(client, person, started["id"])
    answer = await _answer(client, person, started["id"])

    assert working.json()["active_count"] == 1
    assert second.status_code == 409
    assert cancel.status_code == 200
    assert job["state"] == "cancelled"
    assert job["message"] == "Stopped after 1 of 1 connection; 1 match found"
    assert [hit["target"]["name"] for hit in answer["hits"]] == ["diary.txt"]
    assert answer["places"][0]["status"] == "stopped"


async def test_after_a_restart_the_job_is_interrupted_and_its_matches_are_gone(
    client: AsyncClient,
    person: dict[str, str],
    lingering: asyncio.Event,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_id = await _files(client, person)
    started = await _start(client, person, connector_id)
    job_id = uuid.UUID(started["id"])
    await asyncio.wait_for(lingering.wait(), timeout=10)

    # What a new process starts with: no matches, and the startup sweep.
    monkeypatch.setattr(app.state, "contents_memory", ContentsMemory(1800))
    async with async_session_maker() as session:
        await recover_interrupted(session)
    job = (await client.get(f"{API}/jobs/{job_id}", headers=person)).json()
    answer = await _answer(client, person, str(job_id))
    await _runner().cancel(job_id)
    await _runner().wait_for(job_id)

    assert job["state"] == "interrupted"
    assert answer == {
        "job_id": str(job_id), "held": False, "finished": True,
        "words": None, "places": [], "hits": [],
    }


async def test_the_matches_are_the_owners_only_and_a_connection_without_standing_is_unknown(
    client: AsyncClient, person: dict[str, str], db: AsyncSession
) -> None:
    other = await authentication_token_from_email(client=client, email=random_email(), db=db)
    connector_id = await _files(client, person)
    started = await _start(client, person, connector_id)
    await _finished(client, person, started["id"])

    theirs = await client.get(f"{CONTENTS}/{started['id']}", headers=other)
    unknown = await client.get(f"{CONTENTS}/{uuid.uuid4()}", headers=person)
    borrowed = await client.post(
        CONTENTS, headers=other, json={"words": MARKER, "connector_ids": [connector_id]}
    )

    assert theirs.status_code == 404
    assert unknown.status_code == 404
    assert borrowed.status_code == 404


async def test_matches_from_a_connection_no_longer_readable_are_dropped(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person)
    started = await _start(client, person, connector_id)
    await _finished(client, person, started["id"])

    await client.patch(f"{API}/connectors/{connector_id}", headers=person, json={"enabled": False})
    answer = await _answer(client, person, started["id"])

    assert answer["held"]
    assert answer["hits"] == []
    assert answer["places"] == []


async def test_finished_searches_are_pruned_to_the_newest_twenty(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person)
    me = (await client.get(f"{API}/users/me", headers=person)).json()
    owner_id = uuid.UUID(me["id"])
    old = datetime.now(UTC) - timedelta(days=1)
    async with async_session_maker() as session:
        for minute in range(22):
            session.add(Job(
                owner_id=owner_id, kind="search.contents", state="succeeded",
                created_at=old + timedelta(minutes=minute), finished_at=old,
            ))
        await session.commit()

    started = await _start(client, person, connector_id)
    await _finished(client, person, started["id"])

    async with async_session_maker() as session:
        count = (await session.exec(
            select(func.count()).select_from(Job).where(
                col(Job.owner_id) == owner_id, col(Job.kind) == "search.contents"
            )
        )).one()
        kept = await session.get(Job, uuid.UUID(started["id"]))
    assert count == 20
    assert kept is not None


async def test_words_too_short_or_no_connection_are_refused(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _files(client, person)

    short = await client.post(CONTENTS, headers=person, json={"words": "a", "connector_ids": [connector_id]})
    none = await client.post(CONTENTS, headers=person, json={"words": "words", "connector_ids": []})

    assert short.status_code == 422
    assert none.status_code == 422


def test_held_matches_expire_a_while_after_the_job_ends() -> None:
    memory = ContentsMemory(0.05)
    job_id = uuid.uuid4()
    memory.hold(job_id, uuid.uuid4(), "some words", [])

    time.sleep(0.1)
    running = memory.get(job_id)
    memory.ended(job_id)
    just_ended = memory.get(job_id)
    time.sleep(0.1)

    assert running is not None
    assert just_ended is not None
    assert memory.get(job_id) is None


async def test_the_plan_says_which_connections_can_be_searched_inside(
    client: AsyncClient, person: dict[str, str]
) -> None:
    files = await _files(client, person)
    response = await client.post(
        f"{API}/search", headers=person, json={"words": "anything", "mode": "search", "context": [files]}
    )
    [plan] = [line for line in map(json.loads, response.text.splitlines()) if line["type"] == "plan"]

    mine = [cell for cell in plan["cells"] if cell["connector_id"] == files]
    others = [cell for cell in plan["cells"] if cell["connector_id"] is None]
    assert mine and all(cell["contents"] for cell in mine)
    assert others and not any(cell["contents"] for cell in others)
