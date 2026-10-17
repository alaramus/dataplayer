"""A pipeline run whole, as one job, link by link along its arrows (D177)."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud as job_crud
from app.jobs.models import Job
from app.main import app
from app.pipelines import handler as handler_module
from app.users import crud as user_crud
from tests.pipelines.canvas import BASE, Canvas, card, connector, link
from tests.utils.database import working_postgres_options

pytestmark = pytest.mark.usefixtures("clean")

JOBS = f"{settings.API_V1_STR}/jobs"
COLUMNS = [
    {"source": "id", "target": "id", "type_code": "text"},
    {"source": "code", "target": "code", "type_code": "text"},
]


async def _finished(started: Any) -> dict[str, Any]:
    assert started.status_code == 200, started.text
    job_id = uuid.UUID(started.json()["job_id"])
    await app.state.job_runner.wait_for(job_id)
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return {"state": job.state, "message": job.message}


async def test_a_card_written_into_is_read_after_the_link_that_writes_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    name = f"regions-{uuid.uuid4().hex}.csv"
    table = f"loaded_{uuid.uuid4().hex[:8]}"
    # Right to left: position alone would read the file before it is written.
    sales = card(database, [(f"{schema}.regions", "regions", "table")], x=800, name="Sales")
    storage = card(
        files, [("reports", "reports", "directory"), (f"reports/{name}", name, "file")], x=400, name="Files"
    )
    warehouse = card(database, [(schema, schema, "schema")], x=0, name="Warehouse")
    load = link(storage, f"reports/{name}", warehouse, schema, "rows_new_relation", name=table, columns=COLUMNS)
    save = link(sales, f"{schema}.regions", storage, "reports", "relation_csv", name=name)
    saved = await canvas.save([sales, storage, warehouse], [load, save])
    assert saved.status_code == 200, saved.text
    numbers = {one["link_id"]: one["number"] for one in saved.json()["order"]}
    assert (numbers[save["id"]], numbers[load["id"]]) == (1, 2)

    started = await canvas.run()

    assert [one["outcome"] for one in started.json()["links"]] == ["waiting", "waiting"]
    ended = await _finished(started)
    assert ended == {"state": "succeeded", "message": "All 2 links ran"}
    assert await canvas.outcomes() == {
        save["id"]: ("done", f"{name} saved in reports with 2 rows"),
        load["id"]: ("done", f"{table} created with 2 rows"),
    }
    assert (home / "reports" / name).exists()


async def test_the_first_failure_stops_the_run_and_the_rest_are_not_run(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    names = [f"{step}-{uuid.uuid4().hex}.csv" for step in ("first", "taken", "third")]
    (home / "reports" / names[1]).write_text("already here")
    folder = card(files, [("reports", "reports", "directory")], x=1000, name="Files")
    sources = [card(database, [(f"{schema}.regions", "regions", "table")], x=x) for x in (0, 100, 200)]
    links = [
        link(source, f"{schema}.regions", folder, "reports", "relation_csv", name=name)
        for source, name in zip(sources, names, strict=True)
    ]
    await canvas.save([folder, *sources], links)

    ended = await _finished(await canvas.run())

    assert ended["state"] == "failed"
    assert ended["message"].startswith("Stopped at 2 of 3, relation csv: ")
    assert ended["message"].endswith("; 1 not run")
    outcomes = await canvas.outcomes()
    assert outcomes[links[0]["id"]][0] == "done"
    assert outcomes[links[1]["id"]][0] == "failed" and names[1] in (outcomes[links[1]["id"]][1] or "")
    assert outcomes[links[2]["id"]] == ("not_run", None)
    assert not (home / "reports" / names[2]).exists()


async def test_nothing_runs_while_a_link_lacks_its_choices(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n1,EU\n")
    files = await connector(client, headers, "file", {"path": "/"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    canvas = await Canvas(client, headers).make()
    csv = card(files, [(filename, filename, "file")])
    place = card(database, [(schema, schema, "schema")], x=400)
    assert (await canvas.run()).json()["detail"]["code"] == "pipelines.no_links"
    bare = link(csv, filename, place, schema, "rows_new_relation")
    await canvas.save([csv, place], [bare])

    refused = await canvas.run()

    assert refused.status_code == 422
    assert refused.json()["detail"] == {
        "message": "Nothing ran: 1 · rows new relation needs its table named and its columns chosen",
        "link_ids": [bare["id"]],
    }
    assert await canvas.last() is None


async def test_one_run_of_a_pipeline_at_a_time_and_three_pipelines_a_person(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    headers = normal_user_token_headers
    files = await connector(client, headers, "file", {"path": "/"})
    other = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    left = card(files, [("a.csv", "a.csv", "file")])
    right = card(other, [("reports", "reports", "directory")], x=400)
    await canvas.save([left, right], [link(left, "a.csv", right, "reports", "file_copy")])
    user = await user_crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None

    async def running(subject: uuid.UUID) -> None:
        async with async_session_maker() as session:
            job = await job_crud.create(
                session, owner_id=user.id, kind="pipeline.run", subject_id=subject, step_count=2
            )
            job.state = "running"
            session.add(job)
            await session.commit()

    await running(uuid.UUID(canvas.id))
    busy = await canvas.run()
    assert (busy.status_code, busy.json()["detail"]["code"]) == (409, "pipelines.running")
    async with async_session_maker() as session:
        mine = await session.exec(select(Job).where(col(Job.subject_id) == uuid.UUID(canvas.id)))
        for job in mine.all():
            job.state = "failed"
            session.add(job)
        await session.commit()
    for _ in range(settings.PIPELINE_MAX_ACTIVE):
        await running(uuid.uuid4())
    over = await canvas.run()
    assert (over.status_code, over.json()["detail"]["code"]) == (
        429,
        "pipelines.too_many_running",
    )


async def test_stop_ends_the_link_running_and_the_rest_are_not_run(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = normal_user_token_headers
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n1,EU\n")
    files = await connector(client, headers, "file", {"path": "/"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    canvas = await Canvas(client, headers).make()
    csv = card(files, [(filename, filename, "file")])
    place = card(database, [(schema, schema, "schema")], x=400)
    tables = card(database, [(f"{schema}.regions", "regions", "table")], x=800)
    folder = card(files, [("reports", "reports", "directory")], x=1200)
    first = link(csv, filename, place, schema, "rows_new_relation", name="never_made", columns=COLUMNS)
    second = link(tables, f"{schema}.regions", folder, "reports", "relation_csv")
    await canvas.save([csv, place, tables, folder], [first, second])
    entered = asyncio.Event()

    async def held(*_: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(handler_module, "paste_now", held)
    started = await canvas.run()
    assert started.status_code == 200, started.text
    await asyncio.wait_for(entered.wait(), timeout=10)

    stopped = await client.post(f"{JOBS}/{started.json()['job_id']}/cancel", headers=headers)

    assert stopped.status_code == 200, stopped.text
    ended = await _finished(started)
    assert ended == {
        "state": "cancelled",
        "message": "Stopped on request at 1 of 2, rows new relation; 1 not run",
    }
    assert await canvas.outcomes() == {
        first["id"]: ("failed", "Stopped before it finished"),
        second["id"]: ("not_run", None),
    }


async def test_a_link_is_not_run_on_its_own_any_more(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    canvas = await Canvas(client, normal_user_token_headers).make()
    answer = await client.post(
        f"{BASE}/{canvas.id}/links/{uuid.uuid4()}/run", headers=normal_user_token_headers
    )
    assert answer.status_code in (404, 405)
