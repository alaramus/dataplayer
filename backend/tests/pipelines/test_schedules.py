"""A pipeline that runs by itself on a schedule (D179)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import col, select

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud as job_crud
from app.jobs.models import Job
from app.main import app
from app.pipelines.record import RunRecord
from app.pipelines.schedule import PipelineSchedule
from app.pipelines.scheduler import Scheduler
from app.users import crud as user_crud
from tests.pipelines.canvas import BASE, Canvas, card, connector, link

pytestmark = pytest.mark.usefixtures("clean")

EVERY_FIVE = {"enabled": True, "kind": "interval", "every_minutes": 5, "time_zone": "Europe/Riga"}


async def _schedule(canvas: Canvas, chosen: dict[str, Any]) -> Any:
    answer = await canvas.client.put(f"{BASE}/{canvas.id}/schedule", headers=canvas.headers, json=chosen)
    return answer


async def _copying(client: AsyncClient, headers: dict[str, str], home: Path) -> Canvas:
    """A pipeline whose one link copies a file, keeping both names each time."""
    name = f"scheduled-{uuid.uuid4().hex}.csv"
    (home / name).write_text("id\n1\n")
    files = await connector(client, headers, "file", {"path": "/"})
    other = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    source = card(files, [(name, name, "file")])
    folder = card(other, [("reports", "reports", "directory")], x=400)
    await canvas.save([source, folder], [link(source, name, folder, "reports", "file_copy", conflict="rename")])
    return canvas


async def _row(canvas: Canvas) -> PipelineSchedule:
    async with async_session_maker() as session:
        row = await session.get(PipelineSchedule, uuid.UUID(canvas.id))
        assert row is not None
        return row


async def _runs(canvas: Canvas) -> list[Job]:
    async with async_session_maker() as session:
        found = await session.exec(select(Job).where(col(Job.subject_id) == uuid.UUID(canvas.id)))
        return list(found.all())


async def _owner() -> uuid.UUID:
    async with async_session_maker() as session:
        user = await user_crud.get_user_by_email(session=session, email=settings.EMAIL_TEST_USER)
        assert user is not None
        return user.id


def _scheduler(moment: datetime) -> Scheduler:
    return Scheduler(app.state.job_runner, app.state.topics, now=lambda: moment)


async def test_a_schedule_is_set_read_and_switched_off_by_its_owner_only(
    client: AsyncClient, normal_user_token_headers: dict[str, str], superuser_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    before = await client.get(f"{BASE}/{canvas.id}/schedule", headers=normal_user_token_headers)
    assert before.json() == {"settings": None, "next_at": None, "note": None, "note_at": None}

    started = datetime.now(UTC)
    answer = await _schedule(canvas, EVERY_FIVE)

    assert answer.status_code == 200, answer.text
    next_at = datetime.fromisoformat(answer.json()["next_at"])
    assert timedelta(minutes=4) < next_at - started <= timedelta(minutes=5, seconds=5)
    off = await _schedule(canvas, {**EVERY_FIVE, "enabled": False})
    assert off.json()["next_at"] is None
    assert off.json()["settings"]["every_minutes"] == 5
    for refused in ({**EVERY_FIVE, "every_minutes": 4}, {**EVERY_FIVE, "time_zone": "Mars/Olympus"}):
        assert (await _schedule(canvas, refused)).status_code == 422
    elsewhere = await client.get(f"{BASE}/{canvas.id}/schedule", headers=superuser_token_headers)
    assert elsewhere.status_code == 404


async def test_a_schedule_that_comes_runs_the_pipeline_as_its_owner(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    canvas = await _copying(client, normal_user_token_headers, home)
    await _schedule(canvas, EVERY_FIVE)
    came = (await _row(canvas)).next_at
    assert came is not None

    started = await _scheduler(came + timedelta(seconds=10)).tick()

    assert started == 1
    runs = await _runs(canvas)
    assert len(runs) == 1
    await app.state.job_runner.wait_for(runs[0].id)
    async with async_session_maker() as session:
        job = await session.get(Job, runs[0].id)
        assert job is not None and job.state == "succeeded", job
        assert RunRecord.model_validate(job.parameters).scheduled_for == came
    user = await _owner()
    assert runs[0].owner_id == user
    row = await _row(canvas)
    assert row.next_at == came + timedelta(minutes=5)
    assert row.note is None
    # Not due again until then.
    assert await _scheduler(came + timedelta(minutes=1)).tick() == 0


async def test_a_time_that_comes_while_the_last_run_goes_is_skipped(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    canvas = await _copying(client, normal_user_token_headers, home)
    await _schedule(canvas, {**EVERY_FIVE, "kind": "times", "times": ["03:00"]})
    async with async_session_maker() as session:
        going = await job_crud.create(
            session, owner_id=await _owner(), kind="pipeline.run", subject_id=uuid.UUID(canvas.id), step_count=2
        )
        going.state = "running"
        session.add(going)
        await session.commit()
    came = (await _row(canvas)).next_at
    assert came is not None

    await _scheduler(came + timedelta(seconds=5)).tick()

    assert [job.id for job in await _runs(canvas)] == [going.id]
    row = await _row(canvas)
    assert (row.note, row.note_at) == ("Skipped at 03:00: the previous run was still going", came)
    assert row.next_at == came + timedelta(days=1)


async def test_a_pipeline_run_would_refuse_is_skipped_and_says_why(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    await _schedule(canvas, EVERY_FIVE)
    came = (await _row(canvas)).next_at
    assert came is not None

    await _scheduler(came).tick()

    assert await _runs(canvas) == []
    row = await _row(canvas)
    assert row.note is not None and row.note.endswith(": draw a link first")


async def test_a_time_missed_while_the_server_was_off_is_not_caught_up(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    canvas = await _copying(client, normal_user_token_headers, home)
    await _schedule(canvas, {**EVERY_FIVE, "kind": "times", "times": ["03:00"]})
    came = (await _row(canvas)).next_at
    assert came is not None
    back = came + timedelta(hours=5)

    assert await _scheduler(back).settle_missed() >= 1

    row = await _row(canvas)
    assert (row.note, row.note_at) == ("Missed at 03:00: the server was off", came)
    assert row.next_at == came + timedelta(days=1)
    assert await _scheduler(back).tick() == 0
    assert await _runs(canvas) == []
