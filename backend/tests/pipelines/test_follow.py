"""A pipeline following its topics (D315)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from confluent_kafka import KafkaError, KafkaException, Producer
from httpx import AsyncClient
from sqlmodel import select

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from app.pipelines import follow as follow_module
from app.pipelines.follow import FollowedLink, FollowPipeline, ensure_followers
from app.pipelines.handler import StepFailed
from app.pipelines.models import Link, PipelineContent, PipelineFollow
from tests.adapters.kafka_fixture import (
    ORDERS,
    admin,
    bootstrap,
    make,
    names,
    on_server,
    remove,
)
from tests.pipelines.canvas import BASE, Canvas, card, connector, link
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import conninfo, run

pytestmark = pytest.mark.usefixtures("clean")

SENT = ORDERS + 1
COLUMNS = [{"source": "value.id", "target": "id"}]


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """A follower that looks every fifth of a second, so a test waits little."""
    monkeypatch.setattr(settings, "PIPELINE_FOLLOW_SECONDS", 0.2)


@pytest.fixture
async def topic() -> AsyncIterator[str]:
    name, group = names()
    await on_server(lambda: make(name, group))
    yield name
    await on_server(lambda: remove(name, group))


@pytest.fixture
async def table(schema: str) -> str:
    await run(f"CREATE TABLE {schema}.followed (id text)")  # noqa: S608 -- the fixture's own schema
    return f"{schema}.followed"


async def _count(table: str) -> int:
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        found = await (await conn.execute(f"SELECT count(*) FROM {table}")).fetchone()  # noqa: S608 -- a test's own table
        return int(found[0]) if found else 0


async def _reaches(table: str, count: int, seconds: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while await _count(table) < count:
        assert asyncio.get_running_loop().time() < deadline, (
            f"{table} has {await _count(table)} rows, not {count}"
        )
        await asyncio.sleep(0.2)


def _send(topic: str, count: int) -> None:
    producer = Producer({"bootstrap.servers": bootstrap()})
    for index in range(count):
        producer.produce(topic, value=json.dumps({"id": 9000 + index}), partition=0)
    producer.flush(10)


async def _forget(group: str) -> None:
    def drop() -> None:
        client = admin()
        for future in client.delete_consumer_groups([group]).values():
            try:
                future.result()
            except KafkaException as failure:
                if failure.args[0].code() != KafkaError.GROUP_ID_NOT_FOUND:
                    raise

    await on_server(drop)


async def _drawn(
    client: AsyncClient,
    headers: dict[str, str],
    topic: str,
    table: str,
    *,
    follow: bool = True,
) -> tuple[Canvas, dict[str, Any], str]:
    kafka = await connector(
        client,
        headers,
        "kafka",
        {"bootstrap_servers": bootstrap(), "auth_method": "none"},
    )
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(kafka, [(f"topic:{topic}", topic, "topic")], name="Kafka")
    target = card(database, [(table, "followed", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = link(
        source,
        f"topic:{topic}",
        target,
        table,
        "rows_since_last",
        columns=COLUMNS,
        follow=follow,
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    return canvas, drawn, saved.json()["readers"][0]["name"]


async def _switch(canvas: Canvas, on: bool) -> Any:
    answer = await canvas.client.put(
        f"{BASE}/{canvas.id}/follow", headers=canvas.headers, json={"on": on}
    )
    return answer


async def _stopped(canvas: Canvas) -> None:
    """Following switched off, and its job ended."""
    answer = await _switch(canvas, False)
    assert answer.status_code == 200, answer.text
    job_id = answer.json()["job_id"]
    if job_id is not None:
        await app.state.job_runner.wait_for(uuid.UUID(job_id))


async def test_a_followed_link_carries_what_arrives_without_a_run(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, drawn, group = await _drawn(client, normal_user_token_headers, topic, table)
    try:
        answer = await _switch(canvas, True)
        assert answer.status_code == 200, answer.text
        assert answer.json()["on"] is True and answer.json()["running"] is True
        await _reaches(table, SENT)

        await on_server(lambda: _send(topic, 3))
        await _reaches(table, SENT + 3)
        await asyncio.sleep(1.5)  # the record is written at most once a second
        state = (
            await client.get(
                f"{BASE}/{canvas.id}/follow", headers=normal_user_token_headers
            )
        ).json()
        [followed] = state["links"]
        assert followed["link_id"] == drawn["id"]
        assert followed["carried"] == SENT + 3
        assert followed["failures"] == 0

        await _stopped(canvas)
        # One row of the history for the following, with what it carried.
        rows = (
            await client.get(
                f"{BASE}/{canvas.id}/history", headers=normal_user_token_headers
            )
        ).json()["rows"]
        [following] = [row for row in rows if row.get("following")]
        assert following["state"] == "cancelled"
        assert following["message"] == f"Followed; {SENT + 3} messages carried"
    finally:
        await _stopped(canvas)
        await _forget(group)


async def test_run_leaves_a_followed_link_out_while_the_pipeline_follows(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, drawn, group = await _drawn(client, normal_user_token_headers, topic, table)
    try:
        assert (await _switch(canvas, True)).status_code == 200
        started = await canvas.run()
        assert started.status_code == 200, started.text
        await app.state.job_runner.wait_for(uuid.UUID(started.json()["job_id"]))
        assert (await canvas.outcomes())[drawn["id"]] == (
            "not_run",
            "Followed; not run",
        )
    finally:
        await _stopped(canvas)
        await _forget(group)


async def test_following_needs_a_marked_link_and_marks_only_links_reading_on(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, drawn, _ = await _drawn(
        client, normal_user_token_headers, topic, table, follow=False
    )
    refused = await _switch(canvas, True)
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "pipelines.nothing_followed"

    with pytest.raises(ValueError, match="Only a link reading a topic on"):
        Link.model_validate({**drawn, "kind": "rows_into_relation", "follow": True})


async def test_a_person_follows_with_so_many_pipelines(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PIPELINE_FOLLOW_MAX", 0)
    canvas, _, _ = await _drawn(client, normal_user_token_headers, topic, table)
    refused = await _switch(canvas, True)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "pipelines.too_many_following"


async def test_the_switch_starts_a_new_follower_and_a_stop_switches_it_off(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, _, group = await _drawn(client, normal_user_token_headers, topic, table)
    pipeline_id = uuid.UUID(canvas.id)
    try:
        started = (await _switch(canvas, True)).json()
        first = uuid.UUID(started["job_id"])
        # A restart: the process's job is interrupted, the switch stays on.
        await app.state.job_runner.cancel(first)
        await app.state.job_runner.wait_for(first)
        async with async_session_maker() as session:
            job = await session.get(Job, first)
            assert job is not None
            job.state = "interrupted"
            session.add(job)
            await session.commit()
        assert await ensure_followers(app.state.job_runner, app.state.topics) == 1
        state = (
            await client.get(
                f"{BASE}/{canvas.id}/follow", headers=normal_user_token_headers
            )
        ).json()
        assert state["running"] is True and state["job_id"] != str(first)

        # Stopped from the footer: the job is cancelled, and that switches it off.
        await app.state.job_runner.cancel(uuid.UUID(state["job_id"]))
        await app.state.job_runner.wait_for(uuid.UUID(state["job_id"]))
        assert await ensure_followers(app.state.job_runner, app.state.topics) == 0
        async with async_session_maker() as session:
            row = (
                await session.exec(
                    select(PipelineFollow).where(
                        PipelineFollow.pipeline_id == pipeline_id
                    )
                )
            ).one()
            assert row.on is False
    finally:
        await _stopped(canvas)
        await _forget(group)


async def test_a_failing_link_is_tried_again_later_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    follower = FollowPipeline(app.state.data_cache, None, now=lambda: now)
    entry = FollowedLink(link_id=uuid.uuid4(), title="1")
    job = Job(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), kind="pipeline.follow", state="running"
    )
    answers: list[int | Exception] = [StepFailed("The broker is away"), 4]

    async def carried(owner_id: uuid.UUID, content: PipelineContent, link: Link) -> int:
        del owner_id, content, link
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(follower, "carried", carried)
    link_ = Link.model_validate(
        {
            "id": str(entry.link_id),
            "source": {"card_id": str(uuid.uuid4()), "node_id": "topic:t"},
            "target": {"card_id": str(uuid.uuid4()), "node_id": "public.t"},
            "kind": "rows_since_last",
            "title": "1",
            "follow": True,
        }
    )

    assert await follower._turn(job, PipelineContent(), link_, entry) is True
    assert (entry.failures, entry.state, entry.last_error) == (
        1,
        "retrying",
        "The broker is away",
    )
    assert entry.retry_at == now + timedelta(seconds=follow_module.RETRY_SECONDS[0])
    # Not before its time.
    assert await follower._turn(job, PipelineContent(), link_, entry) is False
    now = now + timedelta(seconds=10)
    assert await follower._turn(job, PipelineContent(), link_, entry) is True
    assert (entry.failures, entry.state, entry.carried, entry.last_error) == (
        0,
        "carrying",
        4,
        None,
    )
