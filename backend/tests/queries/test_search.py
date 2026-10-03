"""Saved queries found by the search: titles while typing, bodies on Enter (S5, D204)."""

import asyncio
import json
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from anyio import CapacityLimiter
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.search import MatchClass, SearchBounds, words_of
from app.ai import conversations
from app.core.config import settings
from app.core.db import async_session_maker
from app.main import app
from app.queries import crud
from app.queries import search as saved_queries
from app.queries.content import body_of
from app.queries.models import EditorLayout, QueryDocument
from app.search.models import ObjectTarget
from app.search.providers import Asked
from app.users.models import User
from tests.utils.search import (
    SEARCH,
    Person,
    connection,
    grant,
    hits,
    object_ids,
    outcome,
    person,
    search,
)
from tests.utils.word_cases import CASES

BODIES = "objects:saved_queries/contents"
ONLY = [{"kind": "objects", "provider": "saved_queries"}]


async def _documents(
    owner: Person, connector_id: str, bodies: list[str], title: str | None = None
) -> list[str]:
    async with async_session_maker() as session:
        user = await session.get(User, owner.id)
        assert user is not None
        made = [
            await crud.create(
                session,
                owner=user,
                connector_id=uuid.UUID(connector_id),
                title=title,
                body=body,
                search_path=[],
                layout=EditorLayout(),
            )
            for body in bodies
        ]
    return [str(document.id) for document in made]


async def test_a_title_is_found_while_typing(client: AsyncClient, db: AsyncSession) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Orders {marker}")
    [document_id] = await _documents(
        owner, connector_id, ["select 1"], title=f"Monthly {marker} totals"
    )

    lines = await search(client, owner.headers, f"monthly {marker}", mode="typing")

    [found] = [hit for hit in hits(lines, "objects:saved_queries") if hit["target"]["object_id"] == document_id]
    assert found["match"]["field"] == "name"
    assert found["open"] == "saved_query"
    # The connection the person may see is named on the second line.
    assert found["detail"] == f"Saved query · Orders {marker}"


async def test_a_word_in_a_body_is_found_only_after_enter(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Shop {marker}")
    [document_id] = await _documents(
        owner, connector_id, [f"-- weekly report\nselect *\n  from orders_{marker}\n"]
    )

    typing = await search(client, owner.headers, f"orders_{marker}", mode="typing")
    entered = await search(client, owner.headers, f"orders_{marker}")

    assert document_id not in object_ids(typing, "saved_query")
    assert outcome(typing, BODIES)["reason"] == "too_costly"
    [found] = [hit for hit in hits(entered, "objects:saved_queries") if hit["target"]["object_id"] == document_id]
    assert outcome(entered, BODIES)["status"] == "complete"
    # A draft is named by its first line, as the library names it.
    assert found["title"] == "-- weekly report"
    assert found["match"]["field"] == "body"
    assert found["match"]["match_class"] == "text"
    assert found["match"]["line"] == 3
    assert [part["text"] for part in found["match"]["excerpt"] if part["hit"]] == [
        f"orders_{marker}"
    ]


async def test_somebody_else_s_saved_query_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Books {marker}")
    [document_id] = await _documents(
        owner, connector_id, [f"select '{marker}'"], title=f"Audit {marker}"
    )

    assert document_id in object_ids(await search(client, owner.headers, marker), "saved_query")
    assert object_ids(await search(client, stranger.headers, marker), "saved_query") == []


async def test_a_grant_on_the_connection_finds_none_of_its_owner_s_queries(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await person(client, db)
    grantee = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Ledger {marker}")
    titled = await _documents(owner, connector_id, ["select 1"], title=f"Audit {marker}")
    drafts = await _documents(owner, connector_id, [f"select '{marker}'"])
    await grant(client, owner.headers, connector_id, grantee)

    found = object_ids(await search(client, owner.headers, marker), "saved_query")
    assert sorted(found) == sorted(titled + drafts)
    # The grant is on the connection, never on what its owner saved against it;
    # the grantee finds the connection itself and nothing of the library.
    for headers in (grantee.headers, superuser_token_headers):
        lines = await search(client, headers, marker)
        assert outcome(lines, BODIES)["status"] == "complete"
        assert object_ids(lines, "saved_query") == []
    assert [
        hit["target"]["connector_id"] for hit in hits(await search(client, grantee.headers, marker), "connections")
    ] == [connector_id]


# Names the database folds otherwise than the one rule does: `lower` keeps a
# `ß` and a final `ς`, and under the C locale folds nothing past ASCII.
_FOLDED_ELSEWHERE: list[tuple[str, str, MatchClass | None]] = [
    ("strasse", "Straße", "exact"),
    ("straße umsatz", "Straße Umsatz", "exact"),
    ("οδός", "ΟΔΌΣ", "exact"),
    ("οδός", "Οδός", "exact"),
    ("отчёт", "Отчёт за май", "prefix"),
]


async def test_titles_are_classed_by_the_one_table(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    connector_id = await connection(client, owner.headers, f"Table {uuid.uuid4().hex[:8]}")
    cases = CASES + _FOLDED_ELSEWHERE
    ids = [
        (await _documents(owner, connector_id, ["select 1"], title=name))[0]
        for _, name, _ in cases
    ]
    provider = saved_queries.SavedQueries()

    async with async_session_maker() as session:
        user = await session.get(User, owner.id)
        assert user is not None
        for (typed, name, expected), document_id in zip(cases, ids, strict=True):
            found = await provider.search(
                Asked(
                    user=user,
                    typed=typed,
                    words=words_of(typed),
                    field="names",
                    mode="search",
                    limit=len(cases),
                    bounds=SearchBounds.within(10),
                    session=session,
                )
            )
            classes = [
                hit.match.match_class
                for hit in found.hits
                if isinstance(hit.target, ObjectTarget) and hit.target.object_id == document_id
            ]
            assert classes == ([] if expected is None else [expected]), (typed, name)


async def test_a_title_holding_the_words_as_words_is_not_lost_behind_newer_substrings(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    connector_id = await connection(client, owner.headers, f"Sales {uuid.uuid4().hex[:8]}")
    [older] = await _documents(owner, connector_id, ["select 1"], title="Q3 sales")
    for index in range(6):
        await _documents(owner, connector_id, ["select 1"], title=f"Wholesales report {index}")

    lines = await search(client, owner.headers, "sales", mode="typing")

    found = hits(lines, "objects:saved_queries")
    assert len(found) == 5
    assert found[0]["target"]["object_id"] == older
    assert found[0]["match"]["match_class"] == "word"
    assert outcome(lines, "objects:saved_queries/names")["more"] is True


async def test_titles_beyond_their_bound_are_said_to_be_left_out(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Many {marker}")
    for index in range(4):
        await _documents(owner, connector_id, ["select 1"], title=f"Report {marker} {index}")
    monkeypatch.setattr(saved_queries, "MAX_TITLES", 3)

    lines = await search(client, owner.headers, marker, mode="typing")

    said = outcome(lines, "objects:saved_queries/names")
    assert said["status"] == "stopped"
    assert "newest 3" in said["notice"]
    assert len(object_ids(lines, "saved_query")) == 3


async def test_insisting_while_typing_decrypts_no_body(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Insist {marker}")
    [document_id] = await _documents(owner, connector_id, [f"select '{marker}'"])
    counted = _Counted(monkeypatch)

    lines = await search(
        client, owner.headers, marker, mode="typing", only=ONLY, insist=True
    )

    assert outcome(lines, BODIES)["reason"] == "too_costly"
    assert counted.decrypted == 0
    assert document_id not in object_ids(lines, "saved_query")


async def test_bodies_beyond_the_library_s_bound_are_said_to_be_left_out(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Bound {marker}")
    await _documents(owner, connector_id, [f"select '{marker}', {index}" for index in range(4)])
    monkeypatch.setattr(settings, "QUERY_SEARCH_MAX_DOCUMENTS", 3)

    lines = await search(client, owner.headers, marker, only=ONLY)

    said = outcome(lines, BODIES)
    assert said["status"] == "stopped"
    assert "newest 3" in said["notice"]
    assert len(object_ids(lines, "saved_query")) == 3


# --- one decryption at a time ------------------------------------------------


class _Counted:
    """The body search's blocking work, counted while it runs, and slowed down
    so that a newer search has the time to overlap it."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, pause: float = 0.01) -> None:
        self._guard = threading.Lock()
        self.running = 0
        self.peak = 0
        self.started = 0
        self.decrypted = 0
        # Set on a worker thread, so a thread's event rather than the loop's.
        self.begun = threading.Event()
        holding = saved_queries._holding

        def counted(*args: Any) -> Any:
            with self._guard:
                self.running += 1
                self.started += 1
                self.begun.set()
                self.peak = max(self.peak, self.running)
            try:
                return holding(*args)
            finally:
                with self._guard:
                    self.running -= 1

        def slow(document: QueryDocument) -> str:
            time.sleep(pause)
            with self._guard:
                self.decrypted += 1
            return body_of(document)

        monkeypatch.setattr(saved_queries, "_holding", counted)
        monkeypatch.setattr(saved_queries, "body_of", slow)


def _enter(
    client: AsyncClient, owner: Person, words: str, lane: str = "tab"
) -> Callable[[], Any]:
    async def press() -> list[dict[str, Any]]:
        response = await client.post(
            SEARCH,
            headers=owner.headers,
            json={"words": words, "mode": "search", "lane": lane, "only": ONLY},
        )
        assert response.status_code == 200, response.text
        return [json.loads(line) for line in response.text.splitlines() if line]

    return press


@pytest.mark.parametrize("same_words", [True, False])
async def test_ten_rapid_enters_leave_at_most_one_decryption_running(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    same_words: bool,
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Busy {marker}")
    ids = await _documents(
        owner, connector_id, [f"select '{marker}' as found, {index}" for index in range(40)]
    )
    counted = _Counted(monkeypatch)
    typed = [
        "se",
        "sel",
        "sele",
        "selec",
        "select",
        f"select {marker[:2]}",
        f"select {marker[:4]}",
        f"select {marker[:6]}",
        f"select {marker[:7]}",
        f"select {marker}",
    ]

    # Each press is answered after the one before it has taken its lane: two
    # requests are not handled in the order they were sent, and the one
    # handled last is the one that stays.
    engine = app.state.search_engine
    claimed = asyncio.Event()
    claim = engine.claim

    def claiming(answer: Any) -> None:
        claim(answer)
        claimed.set()

    monkeypatch.setattr(engine, "claim", claiming)

    presses = []
    for words in typed:
        claimed.clear()
        presses.append(asyncio.create_task(_enter(client, owner, typed[-1] if same_words else words)()))
        await asyncio.wait_for(claimed.wait(), 5)
        await asyncio.sleep(0.03)
    answers = await asyncio.gather(*presses)

    assert counted.started > 1
    assert counted.peak == 1
    for older in answers[:-1]:
        assert older[-1]["type"] == "end" and older[-1]["superseded"] is True
    last = answers[-1]
    assert outcome(last, BODIES)["status"] == "complete"
    assert sorted(object_ids(last, "saved_query")) == sorted(ids)


async def test_the_same_words_from_two_places_decrypt_once(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Twice {marker}")
    ids = await _documents(owner, connector_id, [f"select '{marker}', {index}" for index in range(20)])
    counted = _Counted(monkeypatch)

    # The Search tab and a gesture in it are two lanes: neither ends the other.
    tab, gesture = await asyncio.gather(
        _enter(client, owner, marker, lane="tab")(),
        _enter(client, owner, marker, lane="follow")(),
    )

    # Each body once, though the walk hands its turn back between slices.
    assert counted.decrypted == len(ids)
    assert sorted(object_ids(tab, "saved_query")) == sorted(ids)
    assert sorted(object_ids(gesture, "saved_query")) == sorted(ids)


async def test_a_body_walk_leaves_somebody_typing_their_turn(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await person(client, db)
    typist = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Long {marker}")
    await _documents(owner, connector_id, [f"select '{marker}', {index}" for index in range(60)])
    async with async_session_maker() as session:
        chat = await conversations.create(session, typist.id, f"Notes {marker}")
    counted = _Counted(monkeypatch, pause=0.025)
    # One token: the walk and the typist's instant cell take turns at it.
    monkeypatch.setattr(app.state.search_engine, "limiter", CapacityLimiter(1))

    walk = asyncio.create_task(_enter(client, owner, marker)())
    assert await asyncio.to_thread(counted.begun.wait, 5)
    typed = await search(
        client,
        typist.headers,
        f"notes {marker}",
        mode="typing",
        only=[{"kind": "objects", "provider": "conversations"}],
    )
    entered = await walk

    assert outcome(typed, "objects:conversations/names")["status"] == "complete"
    assert object_ids(typed, "conversation") == [str(chat.id)]
    assert outcome(entered, BODIES)["status"] == "complete"
    assert len(object_ids(entered, "saved_query")) == 60
