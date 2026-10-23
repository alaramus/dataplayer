"""MySQL tables copied with their structure, between connections (D182, D239).

The fixture's `items` holds a value of nearly every kind MySQL has, a key, a
check, a prefix index, a generated column and a link into another database:
what arrives must read back exactly as the original does.
"""

from collections.abc import AsyncIterator

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.protocol import SupportsTableCopy
from app.adapters.table_copy import CopyLoad, TableCopyRequest, TableCopyTarget
from tests.adapters.mysql_fixture import (
    DATABASE,
    OTHER,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

COPIES = "dp_copies"
ITEMS = ids.relation_id(DATABASE, "items")
OWNERS = ids.relation_id(OTHER, "owners")


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour)
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    await run(chosen, f"DROP DATABASE IF EXISTS `{COPIES}`", f"CREATE DATABASE `{COPIES}`")
    yield chosen
    await run(chosen, f"DROP DATABASE IF EXISTS `{COPIES}`")
    await tear_down(chosen)


async def _request(
    source: MysqlAdapter, place: str, names: dict[str, str], links: str, *, same: bool = False
) -> TableCopyRequest:
    described = await source.describe_for_copy(list(names))
    return TableCopyRequest(
        dialect="mysql",
        place_node_id=ids.database_id(place),
        same_database=same,
        tables=[
            TableCopyTarget(
                table=table,
                name=names[table.node_id],
                links={link.name: links for link in table.links},  # type: ignore[misc]  # a literal decision
            )
            for table in described
        ],
    )


async def _carry(source: MysqlAdapter, destination: MysqlAdapter, request: TableCopyRequest) -> dict[str, int]:
    counted: dict[str, int] = {}

    async def arrived(load: CopyLoad, rows: int, _size: int) -> None:
        counted[load.name] = rows

    async with source.reading_tables() as tables:
        await destination.carry_table_copy(
            request, lambda load: tables.rows(load.node_id, load.columns), arrived
        )
    return counted


async def _rows(adapter: MysqlAdapter, node_id: str) -> list[list[str | None]]:
    page = await adapter.fetch(FetchRequest(node_id=node_id, limit=50))
    return page.rows


async def test_a_table_is_described_in_the_lines_the_server_prints(target: Target) -> None:
    source = target.adapter()
    assert isinstance(source, SupportsTableCopy)

    [items] = await source.describe_for_copy([ITEMS])

    by_name = {column.name: column for column in items.columns}
    assert by_name["id"].identity == "by_default"
    assert by_name["doubled"].generated is not None
    assert by_name["label"].definition is not None
    assert "DEFAULT 'it''s'" in by_name["label"].definition
    assert [constraint.kind for constraint in items.constraints] == ["primary_key", "check"]
    assert {index.name for index in items.indexes} >= {"items_label", "items_prefix", "items_owner"}
    assert [(link.name, link.target_node_id) for link in items.links] == [("items_owner", OWNERS)]
    assert items.options is not None and "ENGINE=" in items.options
    assert "AUTO_INCREMENT=" not in items.options


async def test_what_is_not_a_table_is_refused_with_a_reason(target: Target) -> None:
    source = target.adapter()

    view, system = await source.describe_for_copy(
        [ids.relation_id(DATABASE, "item_labels"), ids.relation_id("mysql", "db")]
    )

    assert view.refusal == "only tables are copied with their structure"
    assert system.refusal is not None


async def test_tables_arrive_in_another_database_exactly_as_they_were(target: Target) -> None:
    source = target.adapter()
    request = await _request(source, COPIES, {ITEMS: "items", OWNERS: "owners"}, "copy")

    plan = await source.plan_table_copy(request)
    counted = await _carry(source, source, request)

    assert plan.problems == []
    assert [statement.stage for statement in plan.statements] == ["before", "before", "after"]
    assert "REFERENCES `dp_copies`.`owners`" in plan.statements[-1].sql
    assert counted == {"items": 3, "owners": 1}
    assert await _rows(source, ids.relation_id(COPIES, "items")) == await _rows(source, ITEMS)
    model = await source.relation_model(ids.relation_id(COPIES, "items"))
    assert {constraint.kind for constraint in model.constraints} >= {
        "primary_key",
        "unique",
        "check",
        "foreign_key",
    }


async def test_a_copy_in_the_same_database_keeps_its_link_and_its_names_free(
    target: Target,
) -> None:
    source = target.adapter()
    names = await source.free_table_names(ids.database_id(DATABASE), ["items"])
    request = await _request(source, DATABASE, {ITEMS: names[0]}, "original", same=True)

    plan = await source.plan_table_copy(request)
    await _carry(source, source, request)

    assert names == ["items_copy"]
    assert "CONSTRAINT `items_copy_amount` CHECK" in plan.statements[0].sql
    assert "REFERENCES `dp_test_other`.`owners`" in plan.statements[-1].sql
    assert len(await _rows(source, ids.relation_id(DATABASE, "items_copy"))) == 3


async def test_structure_alone_makes_empty_tables(target: Target) -> None:
    source = target.adapter()
    request = (await _request(source, COPIES, {ITEMS: "items", OWNERS: "owners"}, "copy")).model_copy(
        update={"rows": False}
    )

    plan = await source.plan_table_copy(request)
    await _carry(source, source, request)

    assert plan.loads == []
    assert await _rows(source, ids.relation_id(COPIES, "items")) == []


async def test_a_taken_name_is_a_conflict_before_anything_runs(target: Target) -> None:
    source = target.adapter()
    request = await _request(source, DATABASE, {ITEMS: "keyless"}, "drop", same=True)

    plan = await source.plan_table_copy(request)

    assert [problem.kind for problem in plan.problems] == ["conflict"]
    with pytest.raises(ValueError):
        await _carry(source, source, request)


async def test_a_copy_that_fails_half_way_leaves_nothing_behind(target: Target) -> None:
    source = target.adapter()
    request = await _request(source, COPIES, {ITEMS: "items", OWNERS: "owners"}, "copy")

    async def broken(load: CopyLoad) -> AsyncIterator[bytes]:
        yield b'["1"]\n' if load.name == "owners" else b"not json\n"

    with pytest.raises(Exception):  # noqa: B017 — whatever the rows fail with
        await source.carry_table_copy(request, broken, _ignored)

    assert [node.name for node in await source.list_children(ids.database_id(COPIES))] == []


async def _ignored(_load: CopyLoad, _rows: int, _size: int) -> None:
    return None


async def test_between_mysql_and_mariadb_a_copy_arrives_or_is_undone(target: Target) -> None:
    """One dialect covers both servers, which do not know all of each other's
    words. MariaDB knows MySQL's default collation; MySQL does not know
    MariaDB's, and says so, and nothing is left at the destination."""
    other = TARGETS[1] if target is TARGETS[0] else TARGETS[0]
    other.server.require()
    await run(other, f"DROP DATABASE IF EXISTS `{COPIES}`", f"CREATE DATABASE `{COPIES}`")
    try:
        source, destination = target.adapter(), other.adapter()
        request = await _request(source, COPIES, {OWNERS: "owners"}, "drop")
        if target.flavour == "mysql":
            await _carry(source, destination, request)
            assert await _rows(destination, ids.relation_id(COPIES, "owners")) == [["1", "Ann"]]
        else:
            with pytest.raises(ValueError, match="collation"):
                await _carry(source, destination, request)
            assert await destination.list_children(ids.database_id(COPIES)) == []
    finally:
        await run(other, f"DROP DATABASE IF EXISTS `{COPIES}`")
