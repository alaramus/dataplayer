"""What a ClickHouse catalog can be asked to do (D276)."""

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.adapters.actions import Action, ActionRefused, Previews, PreviewsSet, TakesFile
from app.adapters.clickhouse.reports import PROCESSES_REPORT_ID
from app.adapters.database_ids import database_id, relation_id
from app.adapters.fetch import FetchRequest
from tests.adapters.clickhouse_fixture import adapter, run
from tests.utils.services import CLICKHOUSE

SHOP = "dp_actions_shop"
OTHER = "dp_actions_other"
MADE = "dp_actions_made"


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await run(*(f"DROP DATABASE IF EXISTS {name}" for name in (SHOP, OTHER, MADE)))
    await run(
        f"CREATE DATABASE {SHOP}",
        f"CREATE DATABASE {OTHER}",
        f"CREATE TABLE {SHOP}.items (id UInt32, label String) ENGINE = MergeTree ORDER BY id",
        f"INSERT INTO {SHOP}.items VALUES (1, 'a'), (2, 'b')",
        f"CREATE TABLE {SHOP}.loose (id UInt32) ENGINE = MergeTree ORDER BY id",
        f"CREATE VIEW {SHOP}.labels AS SELECT label FROM {SHOP}.items",
        f"CREATE MATERIALIZED VIEW {OTHER}.counted ENGINE = SummingMergeTree ORDER BY id "
        f"AS SELECT id, count() AS n FROM {SHOP}.items GROUP BY id",
    )
    yield
    await run(*(f"DROP DATABASE IF EXISTS {name}" for name in (SHOP, OTHER, MADE)))


def _id(name: str, database: str = SHOP) -> str:
    return relation_id(database, name)


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "prices.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


@pytest.mark.usefixtures("server")
async def test_each_node_offers_what_applies_to_it() -> None:
    source = adapter()

    def named(actions: Sequence[Action[Any]]) -> set[str]:
        return {action.name for action in actions}

    assert named(await source.available(None)) == {"create_database"}
    assert named(await source.available(database_id(SHOP))) == {
        "create_table",
        "load_csv",
        "drop_database",
        "describe_model",
    }
    assert named(await source.available(_id("items"))) == {
        "rename_relation",
        "move_relation",
        "drop_relation",
        "describe_model",
    }
    assert named(await source.available(database_id("system"))) == {"describe_model"}
    assert named(await source.available(PROCESSES_REPORT_ID)) == set()


@pytest.mark.usefixtures("server")
async def test_a_database_is_created_once_and_never_with_the_server_s_name() -> None:
    action = adapter().action("create_database")

    result = await action.perform(None, {"name": MADE})

    assert result.reload_node_ids == [None, database_id(MADE)]
    with pytest.raises(ActionRefused):
        await action.perform(None, {"name": MADE})
    with pytest.raises(ActionRefused):
        await action.perform(None, {"name": "system"})


@pytest.mark.usefixtures("server")
async def test_a_relation_is_renamed_and_moved() -> None:
    source = adapter()

    renamed = await source.action("rename_relation").perform(_id("loose"), {"new_name": "kept"})
    moved = await source.action("move_relation").perform(
        _id("kept"), {"target_schema": database_id(MADE)}
    )

    assert renamed.replacement is not None and renamed.replacement.new_node_id == _id("kept")
    assert moved.replacement is not None and moved.replacement.new_node_id == _id("kept", MADE)
    assert "kept" in {node.name for node in await source.list_children(database_id(MADE))}
    with pytest.raises(ActionRefused):
        await source.action("rename_relation").perform(_id("labels"), {"new_name": "items"})


@pytest.mark.usefixtures("server")
async def test_a_drop_names_the_materialized_views_it_would_break() -> None:
    source = adapter()
    action = source.action("drop_relation")
    assert isinstance(action, Previews) and isinstance(action, PreviewsSet)

    preview = await action.preview(_id("items"), {})
    together = await action.preview_on_set([_id("items"), _id("counted", OTHER)], {})

    assert preview.items == [
        f"Materialized view {OTHER}.counted reads items and will stop working"
    ]
    assert together.items == []


@pytest.mark.usefixtures("server")
async def test_a_database_is_dropped_only_when_said_what_it_holds() -> None:
    source = adapter()
    action = source.action("drop_database")
    assert isinstance(action, Previews)

    refused = await action.preview(database_id(MADE), {})
    told = await action.preview(database_id(MADE), {"cascade": True})
    with pytest.raises(ActionRefused):
        await action.perform(database_id(MADE), {})
    await action.perform(database_id(MADE), {"cascade": True})

    assert refused.blocked
    assert told.items == ["Drop 1 tables and their rows"]
    assert MADE not in {node.name for node in await source.list_children(None)}
    with pytest.raises(ActionRefused):
        await action.perform(database_id("system"), {"cascade": True})


@pytest.mark.usefixtures("server")
async def test_a_file_becomes_a_table_of_text() -> None:
    source = adapter()
    action = source.action("load_csv")
    assert isinstance(action, TakesFile)

    result = await action.perform_with_file(
        database_id(SHOP), {}, Upload(b"sku,note\nA1,it's\nB2,\n")
    )

    assert result.created_node_id == _id("prices")
    page = await source.fetch(FetchRequest(node_id=_id("prices")))
    assert sorted(page.rows, key=lambda row: row[0] or "") == [["A1", "it's"], ["B2", ""]]
    model = await source.relation_model(_id("prices"))
    assert [column.type.sql for column in model.columns] == ["Nullable(String)", "Nullable(String)"]
    with pytest.raises(ActionRefused):
        await action.perform_with_file(database_id(SHOP), {}, Upload(b"sku\nA\n"))


@pytest.mark.usefixtures("server")
async def test_a_database_is_written_out_as_a_model() -> None:
    download = await adapter().action("describe_model").download(  # type: ignore[attr-defined]  # DescribeModel downloads
        [database_id(SHOP)], {"dialect": "dbml"}
    )

    text = b"".join([chunk async for chunk in download.body]).decode()
    assert download.metadata.filename == f"{SHOP}.dbml"
    assert "items" in text
