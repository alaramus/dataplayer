"""What a MySQL catalog can be asked to do: databases and relations (D238).

Against both servers, because the subject is where they differ: MySQL drops a
set of tables whole or not at all, MariaDB drops what it can before it
refuses, and only MySQL says which views read a table.
"""

from collections.abc import AsyncIterator

import pytest

from app.adapters.actions import ActionRefused, Previews, PreviewsSet, TakesFile
from app.adapters.catalog import SchemaNode
from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.reports import PROCESSES_REPORT_ID
from app.adapters.relation import ForeignKey
from tests.adapters.mysql_fixture import TARGETS, Target, run

SHOP = "dp_act_shop"
OTHER = "dp_act_other"
MADE = "dp_act_made"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour)
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    """A database of two tables, one referring to the other, a view and a
    trigger; and an empty one to move into. Built again for every test,
    since most of them drop part of it."""
    chosen: Target = request.param
    chosen.server.require()
    await run(
        chosen,
        *(f"DROP DATABASE IF EXISTS `{name}`" for name in (OTHER, MADE, SHOP)),
        f"CREATE DATABASE `{SHOP}`",
        f"CREATE DATABASE `{OTHER}`",
        f"CREATE TABLE `{SHOP}`.makers (id INT PRIMARY KEY, name VARCHAR(20))",
        f"CREATE TABLE `{SHOP}`.items (id INT PRIMARY KEY, maker_id INT, "
        f"FOREIGN KEY (maker_id) REFERENCES `{SHOP}`.makers (id))",
        f"CREATE TABLE `{SHOP}`.loose (id INT)",
        f"CREATE VIEW `{SHOP}`.maker_names AS SELECT name FROM `{SHOP}`.makers",
        f"CREATE TRIGGER `{SHOP}`.items_check BEFORE INSERT ON `{SHOP}`.items "
        "FOR EACH ROW SET NEW.id = NEW.id",
        f"INSERT INTO `{SHOP}`.makers VALUES (1, 'Ann')",
    )
    yield chosen
    await run(chosen, *(f"DROP DATABASE IF EXISTS `{name}`" for name in (OTHER, MADE, SHOP)))


def _id(relation: str, database: str = SHOP) -> str:
    return ids.relation_id(database, relation)


async def _names(source: MysqlAdapter, database: str) -> set[str]:
    return {node.name for node in await source.list_children(ids.database_id(database))}


async def _databases(source: MysqlAdapter) -> set[str]:
    return {node.name for node in await source.list_children(None) if isinstance(node, SchemaNode)}


async def test_what_is_offered_where(target: Target) -> None:
    source = target.adapter()

    def named(actions: list) -> set[str]:  # type: ignore[type-arg]  # a list of actions
        return {action.name for action in actions}

    assert named(await source.available(None)) == {"create_database"}
    assert named(await source.available(ids.database_id(SHOP))) == {
        "create_table",
        "load_csv",
        "drop_database",
        "describe_model",
    }
    assert named(await source.available(_id("makers"))) == {
        "rename_relation",
        "move_relation",
        "drop_relation",
        "describe_model",
    }
    assert named(await source.available(_id("maker_names"))) == {
        "rename_relation",
        "drop_relation",
        "describe_model",
    }
    assert named(await source.available(ids.database_id("mysql"))) == {"describe_model"}
    assert named(await source.available(PROCESSES_REPORT_ID)) == set()


async def test_a_database_is_created_once_and_never_with_the_server_s_name(target: Target) -> None:
    source = target.adapter()

    result = await source.action("create_database").perform(None, {"name": MADE})

    assert MADE in await _databases(source)
    assert ids.database_id(MADE) in result.reload_node_ids
    with pytest.raises(ActionRefused, match="already exists"):
        await source.action("create_database").perform(None, {"name": MADE})
    with pytest.raises(ActionRefused, match="belongs to the server"):
        await source.action("create_database").perform(None, {"name": "mysql"})
    with pytest.raises(ValueError):
        await source.action("create_database").perform(None, {"name": " padded"})


async def test_an_empty_database_is_said_to_be_empty_and_dropped(target: Target) -> None:
    source = target.adapter()
    action = source.action("drop_database")
    assert isinstance(action, Previews)

    preview = await action.preview(ids.database_id(OTHER), {})
    await action.perform(ids.database_id(OTHER), {})

    assert preview.summary == f"Database {OTHER} is empty"
    assert not preview.blocked
    assert OTHER not in await _databases(source)


async def test_a_database_with_anything_in_it_needs_the_box_ticked(target: Target) -> None:
    source = target.adapter()
    action = source.action("drop_database")
    assert isinstance(action, Previews)

    refused = await action.preview(ids.database_id(SHOP), {})
    with pytest.raises(ActionRefused, match="not empty"):
        await action.perform(ids.database_id(SHOP), {})
    told = await action.preview(ids.database_id(SHOP), {"cascade": True})
    await action.perform(ids.database_id(SHOP), {"cascade": True})

    assert refused.blocked
    assert refused.items == ["3 tables and their rows", "1 views", "1 triggers"]
    assert not told.blocked
    assert told.items[0] == "Drop 3 tables and their rows"
    assert SHOP not in await _databases(source)


async def test_a_database_another_one_refers_into_is_not_dropped(target: Target) -> None:
    await run(
        target,
        f"CREATE TABLE `{OTHER}`.orders (maker_id INT, "
        f"CONSTRAINT orders_maker FOREIGN KEY (maker_id) REFERENCES `{SHOP}`.makers (id))",
    )
    source = target.adapter()
    action = source.action("drop_database")
    assert isinstance(action, Previews)

    preview = await action.preview(ids.database_id(SHOP), {"cascade": True})

    assert preview.blocked
    assert preview.items == [f"{OTHER}.orders refers to {SHOP}.makers through orders_maker"]
    with pytest.raises(ActionRefused):
        await action.perform(ids.database_id(SHOP), {"cascade": True})
    assert await _names(source, SHOP) == {"makers", "items", "loose", "maker_names"}


async def test_a_server_database_is_neither_dropped_nor_made(target: Target) -> None:
    with pytest.raises(ActionRefused):
        await target.adapter().action("drop_database").perform(ids.database_id("sys"), {"cascade": True})


async def test_a_table_and_a_view_are_renamed_and_keys_follow(target: Target) -> None:
    source = target.adapter()
    rename = source.action("rename_relation")

    result = await rename.perform(_id("makers"), {"new_name": "brands"})
    await rename.perform(_id("maker_names"), {"new_name": "brand_names"})

    assert result.replacement is not None
    assert result.replacement.new_node_id == _id("brands")
    assert {"brands", "brand_names"} <= await _names(source, SHOP)
    model = await source.relation_model(_id("items"))
    assert [
        key.target_node_id for key in model.constraints if isinstance(key, ForeignKey)
    ] == [_id("brands")]
    with pytest.raises(ActionRefused, match="already has a relation"):
        await rename.perform(_id("loose"), {"new_name": "items"})
    with pytest.raises(ActionRefused, match="already has that name"):
        await rename.perform(_id("loose"), {"new_name": "loose"})


async def test_a_table_moves_to_another_database(target: Target) -> None:
    source = target.adapter()
    move = source.action("move_relation")

    result = await move.perform(_id("loose"), {"target_schema": ids.database_id(OTHER)})

    assert result.replacement is not None
    assert result.replacement.new_node_id == _id("loose", OTHER)
    assert await _names(source, OTHER) == {"loose"}


async def test_what_cannot_move_is_said_before_the_server_says_it(target: Target) -> None:
    move = target.adapter().action("move_relation")

    with pytest.raises(ActionRefused, match="triggers"):
        await move.perform(_id("items"), {"target_schema": ids.database_id(OTHER)})
    with pytest.raises(ActionRefused, match="view cannot leave"):
        await move.perform(_id("maker_names"), {"target_schema": ids.database_id(OTHER)})
    with pytest.raises(ActionRefused, match="does not exist"):
        await move.perform(_id("loose"), {"target_schema": ids.database_id("dp_act_nowhere")})
    with pytest.raises(ActionRefused, match="server's own"):
        await move.perform(_id("loose"), {"target_schema": ids.database_id("mysql")})


async def test_a_table_others_refer_to_is_not_dropped_alone(target: Target) -> None:
    source = target.adapter()
    action = source.action("drop_relation")
    assert isinstance(action, Previews)

    preview = await action.preview(_id("makers"), {})

    assert preview.blocked
    assert len(preview.items) == 1
    assert preview.items[0].startswith(f"{SHOP}.items refers to {SHOP}.makers")
    with pytest.raises(ActionRefused):
        await action.perform(_id("makers"), {})
    assert "makers" in await _names(source, SHOP)


async def test_a_table_and_the_one_referring_to_it_go_together(target: Target) -> None:
    """In an order MariaDB refuses on its own, with a table before it that
    MariaDB would already have dropped."""
    source = target.adapter()
    action = source.action("drop_relation")
    assert isinstance(action, PreviewsSet)
    chosen = [_id("loose"), _id("makers"), _id("items"), _id("maker_names")]

    preview = await action.preview_on_set(chosen, {})
    result = await action.perform_on_set(chosen, {})

    assert not preview.blocked
    assert preview.items == ["Trigger items_check goes with it"]
    assert result.message == "4 relations dropped"
    assert await _names(source, SHOP) == set()


async def test_a_view_reading_a_dropped_table_is_named_where_the_server_knows(
    target: Target,
) -> None:
    await run(target, f"ALTER TABLE `{SHOP}`.items DROP FOREIGN KEY items_ibfk_1")
    action = target.adapter().action("drop_relation")
    assert isinstance(action, Previews)

    preview = await action.preview(_id("makers"), {})

    readers = [f"View {SHOP}.maker_names reads makers and will stop working"]
    assert preview.items == ([] if target.flavour == "mariadb" else readers)


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "prices.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


async def test_a_file_becomes_a_table_of_text(target: Target) -> None:
    source = target.adapter()
    action = source.action("load_csv")
    assert isinstance(action, TakesFile)
    long = "x" * 300

    result = await action.perform_with_file(
        ids.database_id(SHOP), {}, Upload(f"sku,note\nA1,{long}\nB2,\n".encode())
    )

    assert result.message == "prices created with 2 rows"
    model = await source.relation_model(_id("prices"))
    assert [(column.name, column.type.sql) for column in model.columns] == [
        ("sku", "text"),
        ("note", "text"),
    ]
    with pytest.raises(ActionRefused, match="already there"):
        await action.perform_with_file(ids.database_id(SHOP), {}, Upload(b"sku\nA\n"))


async def test_a_file_can_make_its_database_and_choose_its_columns(target: Target) -> None:
    source = target.adapter()
    action = source.action("load_csv")
    assert isinstance(action, TakesFile)

    await action.perform_with_file(
        ids.database_id(SHOP),
        {
            "name": "picked",
            "schema_name": MADE,
            "create_schema": True,
            "columns": [{"source": "b", "target": "bee"}],
        },
        Upload(b"a,b\n1,2\n"),
    )

    assert await _names(source, MADE) == {"picked"}
    page = await source.fetch(FetchRequest(node_id=_id("picked", MADE), limit=5))
    assert [column.name for column in page.columns] == ["bee"]
    assert page.rows == [["2"]]


async def test_a_database_is_written_out_as_a_model(target: Target) -> None:
    download = await target.adapter().action("describe_model").download(  # type: ignore[attr-defined]  # DescribeModel downloads
        [ids.database_id(SHOP)], {"dialect": "dbml"}
    )

    text = b"".join([chunk async for chunk in download.body]).decode()
    assert download.metadata.filename == f"{SHOP}.dbml"
    assert "makers" in text and "items" in text
