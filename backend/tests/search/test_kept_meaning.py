"""Search by meaning over what connections keep (D220–D222).

The model is a stand-in that reduces a text to the concepts its words name, so
"клиенты" and "customers" are one thing to it and the tests can say what a real
model would find without running one. A pass is the worker's own function.
"""

import json
import math
import re
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.search import embedder as embedders
from app.search import keeper
from app.search.embedder import EmbedderInfo, LocalEmbedder, Vector
from app.search.keep import SearchPassage, SearchVector
from app.search.kept_meaning import prune, waiting_for_vectors
from app.search.kept_text import PASSAGE_CHARACTERS, passages_of
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
KEPT = f"{settings.API_V1_STR}/search/kept"
CONNECTORS = f"{settings.API_V1_STR}/connectors"

_CONCEPTS = {
    "customers": 0, "клиенты": 0, "client": 0,
    "invoices": 1, "счета": 1, "bill": 1,
    "march": 2, "март": 2,
}


class Concepts:
    """A model that knows eight words in two languages and nothing else."""

    def __init__(self, model: str = "test/concepts", sends_out: bool = False) -> None:
        self.model = model
        self._sends_out = sends_out
        self.embedded: list[str] = []

    @property
    def sends_out(self) -> bool:
        return self._sends_out

    async def info(self) -> EmbedderInfo | None:
        return EmbedderInfo(model=self.model, max_tokens=512)

    async def queries(self, texts: Sequence[str]) -> list[Vector]:
        return [self._vector(text) for text in texts]

    async def passages(self, texts: Sequence[str]) -> list[Vector]:
        self.embedded.extend(texts)
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> Vector:
        vector = [0.0] * 4
        for word in re.findall(r"\w+", text.casefold()):
            vector[_CONCEPTS.get(word, 3)] += 1.0 if word in _CONCEPTS else 0.1
        norm = math.sqrt(sum(one * one for one in vector)) or 1.0
        return [one / norm for one in vector]


@pytest.fixture
def model() -> Iterator[Concepts]:
    concepts = Concepts()
    previous = embedders.use(concepts)
    yield concepts
    embedders.use(previous)


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _home(client: AsyncClient, headers: dict[str, str]) -> Path:
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    home = settings.USER_STORAGE_ROOT / me.json()["id"]
    home.mkdir(parents=True, exist_ok=True)
    return home


async def _pass(connector_id: str) -> None:
    async with async_session_maker() as session:
        connector = await session.get(Connector, uuid.UUID(connector_id))
    assert connector is not None
    await keeper.run_pass(connector)


async def _kept_files(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    text: bool = True,
    extra: str | None = None,
) -> str:
    home = await _home(client, headers)
    (home / "billing").mkdir()
    (home / "customers.csv").write_text("id\n1\n", encoding="utf-8")
    if extra is not None:
        (home / extra).write_text("x\n", encoding="utf-8")
    (home / "billing" / "notes.txt").write_text(
        "nothing to see\nthe invoices for march are late\n", encoding="utf-8"
    )
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={"name": f"files {uuid.uuid4().hex[:8]}", "adapter_type": "file", "options": {"path": "/"}},
    )
    connector_id = str(response.json()["id"])
    await client.put(f"{KEPT}/{connector_id}", headers=headers, json={"keep": True})
    await _pass(connector_id)
    if text:
        await client.post(f"{KEPT}/{connector_id}/contents", headers=headers, json={"node_id": "billing"})
        await _pass(connector_id)
    return connector_id


async def _cell(
    client: AsyncClient, headers: dict[str, str], words: str, connector_id: str, field: str,
    mode: str = "search",
) -> dict[str, Any]:
    response = await client.post(SEARCH, headers=headers, json={"words": words, "mode": mode})
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    [plan] = [line for line in lines if line["type"] == "plan"]
    [planned] = [
        cell for cell in plan["cells"]
        if cell["connector_id"] == connector_id and cell["cell"]["field"] == field
    ]
    finished = {line["key"]: line for line in lines if line["type"] == "cell"}
    return {**planned, **finished.get(planned["key"], {})}


# --- what is found -------------------------------------------------------------


@pytest.mark.usefixtures("model")
async def test_a_word_in_another_language_finds_a_name_by_meaning(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person, text=False)

    cell = await _cell(client, person, "клиенты", connector_id, "names")

    assert cell["way"] == "kept"
    [hit] = [one for one in cell["hits"] if one["target"]["node_id"] == "customers.csv"]
    assert hit["match"]["match_class"] == "meaning"
    assert hit["match"]["field"] == "name"
    assert hit["via"] == "kept"


@pytest.mark.usefixtures("model")
async def test_a_line_is_found_by_meaning_inside_a_kept_folder(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person)

    cell = await _cell(client, person, "счета март", connector_id, "contents")

    [hit] = cell["hits"]
    assert hit["target"]["node_id"] == "billing/notes.txt"
    assert hit["match"]["match_class"] == "meaning"
    # The run of lines the model found, opened at its first.
    assert hit["match"]["line"] == 1
    assert "invoices" in "".join(segment["text"] for segment in hit["match"]["excerpt"])


@pytest.mark.usefixtures("model")
async def test_the_words_come_first_and_meaning_adds_only_what_they_missed(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person, text=False)

    cell = await _cell(client, person, "customers", connector_id, "names")

    keys = [hit["target"]["node_id"] for hit in cell["hits"]]
    assert keys.count("customers.csv") == 1
    assert cell["hits"][0]["match"]["match_class"] == "prefix"


@pytest.mark.usefixtures("model")
async def test_nothing_is_found_by_meaning_while_typing(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person, text=False)

    cell = await _cell(client, person, "клиенты", connector_id, "names", "typing")

    assert cell["hits"] == []


async def test_without_a_model_the_words_answer_alone(
    client: AsyncClient, person: dict[str, str]
) -> None:
    previous = embedders.use(None)
    try:
        connector_id = await _kept_files(client, person, text=False)
        cell = await _cell(client, person, "клиенты", connector_id, "names")
        state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()
    finally:
        embedders.use(previous)

    assert cell["way"] == "kept"
    assert cell["hits"] == []
    assert state["meaning"] is None


async def test_a_model_that_sends_text_out_is_not_used(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Sending a connection's names out is its owner's decision (D135), not built."""
    outside = Concepts(sends_out=True)
    previous = embedders.use(outside)
    try:
        connector_id = await _kept_files(client, person, text=False)
        cell = await _cell(client, person, "клиенты", connector_id, "names")
    finally:
        embedders.use(previous)

    assert outside.embedded == []
    assert cell["hits"] == []


# --- what is kept ------------------------------------------------------------


async def _vectors(model: str) -> int:
    async with async_session_maker() as session:
        return (
            await session.exec(
                select(func.count()).select_from(SearchVector).where(col(SearchVector.model) == model)
            )
        ).one()


@pytest.mark.usefixtures("model")
async def test_the_state_says_how_much_the_model_has_read(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person)

    state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()

    assert state["meaning"]["model"] == "test/concepts"
    assert state["meaning"]["passages"] > 0
    assert state["meaning"]["vectors"] == state["meaning"]["passages"]


async def test_a_text_is_embedded_once_however_many_passages_hold_it(
    client: AsyncClient, person: dict[str, str], model: Concepts, db: AsyncSession
) -> None:
    shared = f"client-{uuid.uuid4().hex[:8]}.csv"
    await _kept_files(client, person, text=False, extra=shared)
    first = list(model.embedded)
    model.embedded.clear()
    other = await authentication_token_from_email(client=client, email=random_email(), db=db)
    await _kept_files(client, other, text=False, extra=shared)

    assert shared in first
    assert shared not in model.embedded


async def test_a_list_read_before_the_model_started_is_read_by_it_later(
    client: AsyncClient, person: dict[str, str]
) -> None:
    previous = embedders.use(None)
    try:
        connector_id = await _kept_files(client, person, text=False)
    finally:
        embedders.use(previous)
    late = Concepts(model="test/late")
    previous = embedders.use(late)
    try:
        waiting = await waiting_for_vectors("test/late", limit=100_000)
        await keeper._embed_only(uuid.UUID(connector_id), late, "test/late")
        state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()
    finally:
        embedders.use(previous)

    assert uuid.UUID(connector_id) in waiting
    assert state["meaning"]["vectors"] == state["meaning"]["passages"] > 0


@pytest.mark.usefixtures("model")
async def test_a_new_model_replaces_the_old_once_its_vectors_are_whole(
    client: AsyncClient, person: dict[str, str]
) -> None:
    await _kept_files(client, person, text=False)
    newer = Concepts(model="test/newer")
    previous = embedders.use(newer)
    try:
        await prune("test/newer")
        before = await _vectors("test/concepts")
        await prune("test/newer")
        while_partial = await _vectors("test/concepts")
        for connector_id in await waiting_for_vectors("test/newer", limit=100_000):
            await keeper._embed_only(connector_id, newer, "test/newer")
        await prune("test/newer")
        after = await _vectors("test/concepts")
    finally:
        embedders.use(previous)

    assert before > 0
    assert while_partial == before
    assert after == 0


@pytest.mark.usefixtures("model")
async def test_passages_follow_the_kept_names(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_files(client, person, text=False)
    home = await _home(client, person)
    (home / "customers.csv").rename(home / "clients.csv")
    await _pass(connector_id)

    async with async_session_maker() as session:
        names = set(
            (
                await session.exec(
                    select(SearchPassage.node_id).where(
                        col(SearchPassage.connector_id) == uuid.UUID(connector_id),
                        col(SearchPassage.kind) == "name",
                    )
                )
            ).all()
        )

    assert "clients.csv" in names
    assert "customers.csv" not in names


# --- the pieces ----------------------------------------------------------------


def test_passages_are_short_runs_of_lines_with_their_first_number() -> None:
    lines = ["", "first", "x" * (PASSAGE_CHARACTERS - 10), "third", "", "fourth"]

    passages = passages_of(lines)

    assert [number for number, _ in passages] == [2, 4]
    assert passages[1][1] == "third\nfourth"


async def test_the_local_embedder_sends_each_form_its_prefix_and_remembers_queries() -> None:
    sent: list[list[str]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json={"model_id": "intfloat/x", "max_input_length": 512})
        inputs = json.loads(request.content)["inputs"]
        sent.append(inputs)
        return httpx.Response(200, json=[[1.0, 0.0] for _ in inputs])

    local = LocalEmbedder(
        "http://model", query_prefix="query: ", passage_prefix="passage: ",
        transport=httpx.MockTransport(answer),
    )

    info = await local.info()
    await local.queries(["клиенты"])
    await local.queries(["клиенты"])
    await local.passages(["customers"])

    assert info == EmbedderInfo(model="intfloat/x", max_tokens=512)
    assert sent == [["query: клиенты"], ["passage: customers"]]


async def test_a_local_embedder_that_does_not_answer_is_no_model() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    local = LocalEmbedder("http://model", transport=httpx.MockTransport(down))

    assert await local.info() is None
