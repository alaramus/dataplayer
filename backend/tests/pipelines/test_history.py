"""A pipeline's history of runs: listed, one shown, a hundred kept (D180)."""

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
from app.pipelines.schedule import ScheduleNote
from app.users import crud as user_crud
from tests.pipelines.canvas import BASE, Canvas, card, connector, link

pytestmark = pytest.mark.usefixtures("clean")

LONG_AGO = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)


async def _owner() -> uuid.UUID:
    async with async_session_maker() as session:
        user = await user_crud.get_user_by_email(session=session, email=settings.EMAIL_TEST_USER)
        assert user is not None
        return user.id


def _job(pipeline_id: str, owner: uuid.UUID, at: datetime, state: str = "succeeded", **fields: Any) -> Job:
    """A run of the pipeline as its job would be left, written straight in."""
    ended = state not in ("queued", "running")
    return Job(
        owner_id=owner, kind="pipeline.run", subject_id=uuid.UUID(pipeline_id), state=state, step_count=2,
        created_at=at, started_at=at, finished_at=at + timedelta(seconds=12) if ended else None, **fields,
    )


async def _written(*rows: Job | ScheduleNote) -> None:
    async with async_session_maker() as session:
        session.add_all(rows)
        await session.commit()


async def _history(canvas: Canvas, headers: dict[str, str] | None = None) -> Any:
    answer = await canvas.client.get(f"{BASE}/{canvas.id}/history", headers=headers or canvas.headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["rows"]


async def _jobs_of(pipeline_id: str) -> list[Job]:
    async with async_session_maker() as session:
        found = await session.exec(
            select(Job).where(col(Job.subject_id) == uuid.UUID(pipeline_id)).order_by(col(Job.created_at))
        )
        return list(found.all())


async def test_the_history_lists_runs_and_the_skips_among_them_newest_first(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    owner = await _owner()
    by_hand = _job(canvas.id, owner, LONG_AGO, message="All 2 links ran")
    scheduled = _job(
        canvas.id, owner, LONG_AGO + timedelta(hours=1), "failed", message="Stopped at 1 of 2, Save as CSV",
        parameters={"scheduled_for": (LONG_AGO + timedelta(hours=1)).isoformat()},
    )
    going = _job(canvas.id, owner, LONG_AGO + timedelta(hours=2), "running")
    skipped = ScheduleNote(
        pipeline_id=uuid.UUID(canvas.id), kind="skipped", at=LONG_AGO + timedelta(minutes=90),
        reason="the previous run was still going",
    )
    await _written(by_hand, scheduled, going, skipped)

    rows = await _history(canvas)

    assert [(row["kind"], row.get("job_id")) for row in rows] == [
        ("run", str(going.id)), ("skipped", None), ("run", str(scheduled.id)), ("run", str(by_hand.id)),
    ]
    assert [row.get("scheduled") for row in rows] == [False, None, True, False]
    assert (rows[3]["state"], rows[3]["message"]) == ("succeeded", "All 2 links ran")
    took = datetime.fromisoformat(rows[3]["finished_at"]) - datetime.fromisoformat(rows[3]["started_at"])
    assert took == timedelta(seconds=12)
    assert (rows[2]["state"], rows[0]["state"], rows[0]["finished_at"]) == ("failed", "running", None)
    assert rows[1]["reason"] == "the previous run was still going"
    assert datetime.fromisoformat(rows[1]["at"]) == LONG_AGO + timedelta(minutes=90)


async def test_an_older_run_is_shown_by_what_it_did_then(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    headers = normal_user_token_headers
    name = f"shown-{uuid.uuid4().hex}.csv"
    (home / name).write_text("id\n1\n")
    files = await connector(client, headers, "file", {"path": "/"})
    other = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    source = card(files, [(name, name, "file")])
    folder = card(other, [("reports", "reports", "directory")], x=400)
    copy = link(source, name, folder, "reports", "file_copy", conflict="rename")
    await canvas.save([source, folder], [copy])
    first = await canvas.run()
    await app.state.job_runner.wait_for(uuid.UUID(first.json()["job_id"]))
    (home / name).unlink()
    second = await canvas.run()
    await app.state.job_runner.wait_for(uuid.UUID(second.json()["job_id"]))

    shown = await client.get(f"{BASE}/{canvas.id}/runs/{first.json()['job_id']}", headers=headers)

    assert shown.status_code == 200, shown.text
    assert shown.json()["state"] == "succeeded"
    assert [one["outcome"] for one in shown.json()["links"]] == ["done"]
    assert [one["outcome"] for one in (await canvas.last())["links"]] == ["failed"]
    assert [row["state"] for row in await _history(canvas)] == ["failed", "succeeded"]
    # Taken off the canvas since: the run keeps it, the canvas has none to show.
    await canvas.save([source, folder], [])
    again = await client.get(f"{BASE}/{canvas.id}/runs/{first.json()['job_id']}", headers=headers)
    assert (again.json()["state"], again.json()["links"]) == ("succeeded", [])


async def test_the_hundred_and_first_run_removes_the_oldest_and_never_one_going(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    headers = normal_user_token_headers
    name = f"kept-{uuid.uuid4().hex}.csv"
    (home / name).write_text("id\n1\n")
    files = await connector(client, headers, "file", {"path": "/"})
    other = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    source = card(files, [(name, name, "file")])
    folder = card(other, [("reports", "reports", "directory")], x=400)
    await canvas.save([source, folder], [link(source, name, folder, "reports", "file_copy", conflict="rename")])
    owner = await _owner()
    old = [_job(canvas.id, owner, LONG_AGO + timedelta(minutes=index)) for index in range(100)]
    await _written(*old)

    started = await canvas.run()
    await app.state.job_runner.wait_for(uuid.UUID(started.json()["job_id"]))

    kept = await _jobs_of(canvas.id)
    assert len(kept) == 100
    assert [job.id for job in kept[:1]] == [old[1].id]
    assert kept[-1].id == uuid.UUID(started.json()["job_id"])
    assert len(await _history(canvas)) == 100
    going = _job(canvas.id, owner, LONG_AGO - timedelta(days=1), "running")
    await _written(going)
    async with async_session_maker() as session:
        assert await job_crud.forget_finished(
            session, kind="pipeline.run", subject_id=uuid.UUID(canvas.id), keep=100
        ) == 0
        assert await job_crud.forget_finished(session, kind="pipeline.run", subject_id=uuid.UUID(canvas.id)) == 100
        await session.commit()
    assert [job.id for job in await _jobs_of(canvas.id)] == [going.id]


async def test_a_pipeline_deleted_takes_its_finished_runs_and_its_notes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    other = await Canvas(client, normal_user_token_headers).make()
    owner = await _owner()
    going = _job(canvas.id, owner, LONG_AGO + timedelta(hours=1), "running")
    elsewhere = _job(other.id, owner, LONG_AGO)
    await _written(
        _job(canvas.id, owner, LONG_AGO),
        _job(canvas.id, owner, LONG_AGO + timedelta(minutes=5), "interrupted"),
        going,
        elsewhere,
        ScheduleNote(pipeline_id=uuid.UUID(canvas.id), kind="missed", at=LONG_AGO, reason="the server was off"),
    )

    removed = await client.delete(f"{BASE}/{canvas.id}", headers=normal_user_token_headers)

    assert removed.status_code == 200, removed.text
    assert [job.id for job in await _jobs_of(canvas.id)] == [going.id]
    assert [job.id for job in await _jobs_of(other.id)] == [elsewhere.id]
    async with async_session_maker() as session:
        notes = await session.exec(select(ScheduleNote).where(col(ScheduleNote.pipeline_id) == uuid.UUID(canvas.id)))
        assert notes.all() == []


async def test_another_persons_history_can_be_neither_listed_nor_shown(
    client: AsyncClient, normal_user_token_headers: dict[str, str], superuser_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    other = await Canvas(client, normal_user_token_headers).make()
    owner = await _owner()
    run = _job(canvas.id, owner, LONG_AGO)
    elsewhere = _job(other.id, owner, LONG_AGO)
    await _written(run, elsewhere)
    own = f"{BASE}/{canvas.id}"

    assert (await client.get(f"{own}/runs/{run.id}", headers=normal_user_token_headers)).status_code == 200
    assert (await client.get(f"{own}/history", headers=superuser_token_headers)).status_code == 404
    assert (await client.get(f"{own}/runs/{run.id}", headers=superuser_token_headers)).status_code == 404
    # A run of another pipeline, or none, is no run of this one.
    for job_id in (elsewhere.id, uuid.uuid4()):
        refused = await client.get(f"{own}/runs/{job_id}", headers=normal_user_token_headers)
        assert (refused.status_code, refused.json()["detail"]["code"]) == (404, "pipelines.run_not_found")
