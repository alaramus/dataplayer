"""Links of a pipeline: kept with its cards (D176), the rows a drag can reach
(D363), and drawn ready (D364)."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.fetch import FetchColumn
from app.adapters.relation import ColumnType
from app.pipelines import targets as targets_module
from app.pipelines.offers import key_column, key_values, table_name
from tests.pipelines.canvas import Canvas, card, connector, end, link
from tests.utils.database import working_postgres_options

pytestmark = pytest.mark.usefixtures("clean")


async def test_links_are_kept_with_the_rows_they_join(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    files = await connector(client, headers, "file", {"path": "/"})
    other_files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    left = card(files, [("a.csv", "a.csv", "file"), (None, "Files", None)])
    right = card(other_files, [("reports", "reports", "directory"), (None, "Files", None)], x=400)
    same = card(files, [("reports", "reports", "directory")], x=800)
    joined = link(left, "a.csv", right, "reports", "file_copy", conflict="rename")
    into_top = link(left, "a.csv", right, None, "file_move")

    saved = await canvas.save([left, right, same], [joined, into_top])

    assert saved.status_code == 200, saved.text
    kept = saved.json()["links"]
    assert [one["id"] for one in kept] == [joined["id"], into_top["id"]]
    assert kept[0]["conflict"] == "rename" and kept[1]["conflict"] == "refuse"
    for broken in (
        [link(left, "a.csv", {"id": str(uuid.uuid4())}, "reports", "file_copy")],
        [link(left, "b.csv", right, "reports", "file_copy")],
        [link(left, None, right, "reports", "file_copy")],
        [link(left, "a.csv", same, "reports", "file_copy")],
        [joined, {**joined, "id": str(uuid.uuid4())}],
        [{**joined, "kind": "teleport"}],
    ):
        refused = await canvas.save([left, right, same], broken)
        assert refused.status_code == 422, broken


def _answered(found: dict[str, Any]) -> dict[tuple[str, str | None], tuple[str | None, str | None]]:
    return {
        (one["end"]["card_id"], one["end"]["node_id"]): (one["kind"], one["reason"])
        for one in found["targets"]
    }


async def _people(client: AsyncClient, headers: dict[str, str], home: Path, schema: str) -> tuple[
    Canvas, dict[str, Any], dict[str, Any], dict[str, Any], str
]:
    """A CSV of people in storage, and a database with its regions table."""
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n7,AS\n")
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = card(database, [(schema, schema, "schema"), (f"{schema}.regions", "regions", "table")])
    storage = card(files, [("reports", "reports", "directory"), (filename, filename, "file")], x=400)
    more_tables = card(database, [(schema, schema, "schema")], x=800)
    return canvas, tables, storage, more_tables, filename


async def test_a_drag_is_answered_row_by_row_with_what_a_drop_draws_or_why_not(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    canvas, tables, storage, more_tables, filename = await _people(
        client, normal_user_token_headers, home, schema
    )
    drawn = link(storage, filename, tables, f"{schema}.regions", "rows_into_relation")
    await canvas.save([tables, storage, more_tables], [drawn])

    from_file = _answered(await canvas.targets(end(storage, filename)))
    assert from_file[(tables["id"], schema)][0] == "rows_new_relation"
    assert from_file[(tables["id"], f"{schema}.regions")] == (None, "Already linked")
    assert from_file[(more_tables["id"], schema)][0] == "rows_new_relation"

    from_table = _answered(await canvas.targets(end(tables, f"{schema}.regions")))
    assert from_table[(storage["id"], "reports")][0] == "relation_csv"
    assert from_table[(more_tables["id"], schema)] == (None, "Same connection")
    # Its own card is not a target.
    assert not any(card_id == tables["id"] for card_id, _ in from_table)


async def test_a_canvas_too_large_to_answer_whole_is_answered_card_by_card(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas, tables, storage, more_tables, filename = await _people(
        client, normal_user_token_headers, home, schema
    )
    await canvas.save([tables, storage, more_tables], [])
    monkeypatch.setattr(targets_module, "MAX_TARGET_ROWS", 1)

    # Three rows to ask of, past a ceiling of one: none is asked.
    assert await canvas.targets(end(storage, filename)) == {"targets": [], "partial": True}

    one_card = _answered(await canvas.targets(end(storage, filename), more_tables["id"]))
    assert list(one_card) == [(more_tables["id"], schema)]
    assert one_card[(more_tables["id"], schema)][0] == "rows_new_relation"


async def test_an_offer_brings_what_a_link_is_drawn_ready_with(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    canvas, tables, storage, more_tables, filename = await _people(
        client, normal_user_token_headers, home, schema
    )
    await canvas.save([tables, storage, more_tables], [])

    into_schema = await canvas.offers(end(storage, filename), end(tables, schema))
    made = into_schema["rows_new_relation"]["defaults"]
    assert made["runs"] == "scheduled"
    assert made["name"] == table_name(filename)
    assert [(column["source"], column["target"]) for column in made["columns"]] == [("id", "id"), ("code", "code")]
    assert all(column["type_code"] for column in made["columns"])
    into_table = await canvas.offers(end(storage, filename), end(tables, f"{schema}.regions"))
    paired = into_table["rows_into_relation"]["defaults"]["columns"]
    assert {(column["source"], column["target"]) for column in paired} == {("id", "id"), ("code", "code")}

    bare = link(storage, filename, tables, schema, "rows_new_relation")
    lacking = (await canvas.save([tables, storage, more_tables], [bare])).json()["lacking"]
    assert [(one["link_id"], one["needs"]) for one in lacking] == [(bare["id"], "table")]
    refused = await canvas.switch(True)
    assert refused.status_code == 422
    assert refused.json()["detail"]["link_ids"] == [bare["id"]]

    ready = {**bare, "name": made["name"], "columns": made["columns"]}
    saved = await canvas.save([tables, storage, more_tables], [ready])
    assert saved.json()["lacking"] == []


def test_a_table_is_named_after_what_it_is_made_from() -> None:
    assert table_name("btc-trades") == "btc_trades"
    assert table_name("People 2026.csv") == "people_2026"
    assert table_name("...") == "rows"


def _columns(*names: str) -> list[FetchColumn]:
    return [FetchColumn(name=name, type=ColumnType(sql="text", category="string")) for name in names]


def test_the_latest_per_key_starts_from_a_topics_key_and_its_fields() -> None:
    topic = _columns("partition", "offset", "timestamp", "key", "value", "headers", "value.price", "value.side")
    assert key_column(topic) == "key"
    assert [(one.source, one.target) for one in key_values(topic, "key")] == [
        ("value.price", "price"),
        ("value.side", "side"),
    ]
    plain = _columns("partition", "offset", "key", "value")
    assert [(one.source, one.target) for one in key_values(plain, "key")] == [("value", "value")]
    table = _columns("symbol", "price")
    assert key_column(table) == "symbol"
    assert [(one.source, one.target) for one in key_values(table, "symbol")] == [("price", "price")]
