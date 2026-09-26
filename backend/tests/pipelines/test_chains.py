"""Chains: what one link makes, read by the next (D178)."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.pipelines.canvas import Canvas, card, connector, end, joined
from tests.utils.database import working_postgres_options

pytestmark = pytest.mark.usefixtures("clean")

COLUMNS = [
    {"source": "id", "target": "id", "type_code": "text"},
    {"source": "code", "target": "code", "type_code": "text"},
]


async def _ran(started: Any) -> dict[str, Any]:
    assert started.status_code == 200, started.text
    job_id = uuid.UUID(started.json()["job_id"])
    await app.state.job_runner.wait_for(job_id)
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return {"state": job.state, "message": job.message}


async def _links(canvas: Canvas) -> dict[str, dict[str, Any]]:
    last = await canvas.last()
    return {one["link_id"]: one for one in last["links"]}


@pytest.mark.usefixtures("home")
async def test_what_a_link_makes_is_a_row_asked_of_as_it_will_be_made(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = card(database, [(f"{schema}.regions", "regions", "table"), (schema, schema, "schema")])
    folder = card(files, [("reports", "reports", "directory")], x=400)
    save = joined(end(tables, f"{schema}.regions"), end(folder, "reports"), "relation_csv", name="monthly")

    saved = await canvas.save([tables, folder], [save])

    assert saved.status_code == 200, saved.text
    assert saved.json()["results"] == [
        {"link_id": save["id"], "card_id": folder["id"], "name": "monthly.csv", "kind": "file"}
    ]
    # Before any run, the file is asked of as a CSV of the table's columns.
    offers = await canvas.offers(end(folder, made_by=save), end(tables, schema))
    assert offers["rows_new_relation"]["available"] is True
    assert [column["name"] for column in offers["rows_new_relation"]["source_columns"]] == ["id", "code"]
    # Two ticked rows are asked as the pair window asks them.
    plain = await canvas.offers(end(tables, f"{schema}.regions"), end(folder, "reports"))
    assert plain["relation_csv"]["suggested_name"] == "regions.csv"
    # And the hint draws a link from the result as from any row.
    hinted = await canvas.hint()
    assert {
        (one["source"]["made_by"], one["target"]["node_id"], tuple(one["titles"])) for one in hinted["links"]
    } >= {(save["id"], schema, ("Create a table",))}


async def test_a_chain_reads_what_was_made_in_this_run_under_the_name_it_was_made_with(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    stem = f"regions-{uuid.uuid4().hex[:8]}"
    # An earlier file under the name, of one row: Keep both names the new one
    # "(1)", and the chain must read that one, of two rows.
    (home / "reports" / f"{stem}.csv").write_text("id,code\n9,ZZ\n")
    table = f"chained_{uuid.uuid4().hex[:8]}"
    tables = card(database, [(f"{schema}.regions", "regions", "table"), (schema, schema, "schema")])
    folder = card(files, [("reports", "reports", "directory")], x=400)
    save = joined(
        end(tables, f"{schema}.regions"), end(folder, "reports"), "relation_csv", name=stem, conflict="rename"
    )
    load = joined(end(folder, made_by=save), end(tables, schema), "rows_new_relation", name=table, columns=COLUMNS)
    await canvas.save([tables, folder], [load, save])

    ended = await _ran(await canvas.run())

    assert ended == {"state": "succeeded", "message": "All 2 links ran"}
    links = await _links(canvas)
    assert links[save["id"]]["made"] == f"{stem} (1).csv"
    assert (links[load["id"]]["read"], links[load["id"]]["message"]) == (
        f"{stem} (1).csv",
        f"{table} created with 2 rows",
    )


async def test_rows_go_into_a_table_another_link_makes_in_the_same_run(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    first, second = (f"{part}-{uuid.uuid4().hex}.csv" for part in ("first", "second"))
    (home / first).write_text("id,code\n1,EU\n")
    (home / second).write_text("id,code\n2,US\n3,AS\n")
    files = await connector(client, headers, "file", {"path": "/"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    canvas = await Canvas(client, headers).make()
    table = f"filled_{uuid.uuid4().hex[:8]}"
    csv = card(files, [(first, first, "file"), (second, second, "file")])
    place = card(database, [(schema, schema, "schema")], x=400)
    create = joined(end(csv, first), end(place, schema), "rows_new_relation", name=table, columns=COLUMNS)
    # Drawn first and lying higher: only the result it writes into orders it.
    fill = joined(end(csv, second), end(place, made_by=create), "rows_into_relation", columns=COLUMNS)
    saved = await canvas.save([csv, place], [fill, create])
    numbers = {one["link_id"]: one["number"] for one in saved.json()["order"]}
    assert (numbers[create["id"]], numbers[fill["id"]]) == (1, 2)

    offers = await canvas.offers(end(csv, second), end(place, made_by=create))
    assert [column["name"] for column in offers["rows_into_relation"]["target_columns"]] == ["id", "code"]

    ended = await _ran(await canvas.run())

    assert ended["state"] == "succeeded", ended
    links = await _links(canvas)
    assert links[create["id"]]["message"] == f"{table} created with 1 row"
    assert links[fill["id"]]["message"] == "2 rows added"


async def test_the_link_making_a_result_failing_leaves_the_one_reading_it_not_run(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    name = f"taken-{uuid.uuid4().hex}.csv"
    (home / "reports" / name).write_text("id,code\n9,ZZ\n")
    tables = card(database, [(f"{schema}.regions", "regions", "table"), (schema, schema, "schema")])
    folder = card(files, [("reports", "reports", "directory")], x=400)
    save = joined(end(tables, f"{schema}.regions"), end(folder, "reports"), "relation_csv", name=name)
    load = joined(end(folder, made_by=save), end(tables, schema), "rows_new_relation", name="never", columns=COLUMNS)
    await canvas.save([tables, folder], [save, load])

    ended = await _ran(await canvas.run())

    assert ended["state"] == "failed"
    links = await _links(canvas)
    assert links[save["id"]]["outcome"] == "failed"
    assert (links[load["id"]]["outcome"], links[load["id"]]["read"]) == ("not_run", None)


async def test_a_link_reading_what_it_makes_itself_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    files = await connector(client, headers, "file", {"path": "/"})
    other = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    left = card(files, [("a.csv", "a.csv", "file")])
    right = card(other, [("reports", "reports", "directory")], x=400)
    first = joined(end(left, "a.csv"), end(right, "reports"), "file_copy")
    second = joined(end(right, made_by=first), end(left, "a.csv"), "file_copy")
    loop = {**first, "source": end(left, made_by=second)}

    refused = await canvas.save([left, right], [loop, second])

    assert refused.status_code == 422
    assert "what it makes itself" in refused.text
