"""Links of a pipeline: kept with its cards, and hinted (D176)."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.pipelines import hint as hint_module
from tests.pipelines.canvas import Canvas, card, connector, link
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


def _hinted(answer: dict[str, Any]) -> set[tuple[str | None, str | None, tuple[str, ...]]]:
    return {
        (one["source"]["node_id"], one["target"]["node_id"], tuple(one["titles"]))
        for one in answer["links"]
    }


async def test_the_hint_draws_every_link_the_rows_can_make(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path, schema: str
) -> None:
    headers = normal_user_token_headers
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n7,AS\n")
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = card(database, [(schema, schema, "schema"), (f"{schema}.regions", "regions", "table")])
    storage_card = card(files, [("reports", "reports", "directory"), (filename, filename, "file")], x=400)
    drawn = link(storage_card, filename, tables, f"{schema}.regions", "rows_into_relation")
    await canvas.save([tables, storage_card], [drawn])

    answer = await canvas.hint()

    assert answer["notice"] is None
    assert _hinted(answer) == {
        (f"{schema}.regions", "reports", ("Save as CSV",)),
        (filename, schema, ("Create a table",)),
    }


@pytest.mark.usefixtures("home")
async def test_a_canvas_too_large_to_hint_whole_hints_the_selectedcard(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    files = await connector(client, headers, "file", {"path": "/"})
    canvas = await Canvas(client, headers).make()
    tables = card(database, [(f"{schema}.regions", "regions", "table")])
    first = card(files, [("reports", "reports", "directory")], x=400)
    second = card(files, [("reports", "reports", "directory")], x=800)
    await canvas.save([tables, first, second], [])
    # Four pairs of rows in all, two of them the first card's.
    monkeypatch.setattr(hint_module, "MAX_HINT_PAIRS", 2)

    whole = await canvas.hint()
    assert whole == {
        "links": [],
        "notice": "This canvas holds too many rows to hint at once: select a card first",
    }

    selected = await canvas.hint(first["id"])
    assert selected["notice"] == "Only the links of the selected card are hinted"
    assert [(one["source"]["card_id"], one["target"]["card_id"]) for one in selected["links"]] == [
        (tables["id"], first["id"]),
    ]
