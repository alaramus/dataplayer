"""Catalog actions, the table designer, reports, search and export (D347–D350)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, JsonAction
from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.catalog import ReportNode
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.protocol import (
    EnumeratesNames,
    SearchesColumns,
    SupportsExport,
    SupportsNodeSearch,
    SupportsTableDesign,
)
from app.adapters.search import NodeSearchRequest, SearchBounds
from app.adapters.table_design import TableDefinition, TablePlanRequest
from tests.adapters.cassandra_fixture import (
    KEYSPACE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

NEW_KEYSPACE = "dp_test_cql_made"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    await run(chosen, f"DROP KEYSPACE IF EXISTS {NEW_KEYSPACE}")
    yield chosen
    await run(chosen, f"DROP KEYSPACE IF EXISTS {NEW_KEYSPACE}")
    await tear_down(chosen)


async def _act(
    adapter: CassandraAdapter, name: str, node_id: str | None, raw: dict[str, Any]
) -> Any:
    action = adapter.action(name)
    assert isinstance(action, JsonAction)
    return await action.perform(node_id, raw)


def _definition(name: str, **extra: Any) -> TableDefinition:
    return TableDefinition.model_validate(
        {
            "name": name,
            "comment": "Made by the designer",
            "columns": [
                {"id": "c1", "name": "tenant", "type": {"code": "text"}},
                {"id": "c2", "name": "day", "type": {"code": "date"}},
                {"id": "c3", "name": "seq", "type": {"code": "int"}},
                {"id": "c4", "name": "tags", "type": {"code": "text", "dimensions": 1}},
            ],
            "primary_key": {"column_ids": ["c1", "c2", "c3"]},
            "engine": {
                "code": "table",
                "arguments": [{"code": "partition", "column_ids": ["c1", "c2"]}],
            },
            **extra,
        }
    )


# --- What is offered ---------------------------------------------------------


async def test_actions_are_offered_where_they_belong(target: Target) -> None:
    adapter = target.adapter()
    for capability in (
        SupportsTableDesign,
        SupportsNodeSearch,
        SearchesColumns,
        EnumeratesNames,
        SupportsExport,
    ):
        assert isinstance(adapter, capability)

    top = {action.name for action in await adapter.available(None)}
    keyspace = {action.name for action in await adapter.available(KEYSPACE)}
    table = {action.name for action in await adapter.available(f"{KEYSPACE}.many")}
    view = {
        action.name for action in await adapter.available(f"{KEYSPACE}.items_by_ok")
    }
    system = await adapter.available("system_schema")

    assert top == {"create_keyspace"}
    assert keyspace == {"create_table", "drop_keyspace"}
    assert table == {"truncate_table", "drop_relation"}
    assert view == {"drop_relation"}
    assert system == []


# --- Keyspaces -----------------------------------------------------------------


async def test_a_keyspace_is_made_and_dropped(target: Target) -> None:
    adapter = target.adapter()

    await _act(adapter, "create_keyspace", None, {"name": NEW_KEYSPACE})
    with pytest.raises(ActionRefused):
        await _act(adapter, "create_keyspace", None, {"name": NEW_KEYSPACE})
    roots = [node.name for node in await adapter.list_children(None)]
    await _act(adapter, "drop_keyspace", NEW_KEYSPACE, {})
    after = [node.name for node in await adapter.list_children(None)]

    assert NEW_KEYSPACE in roots and NEW_KEYSPACE not in after


async def test_a_keyspace_name_is_checked(target: Target) -> None:
    with pytest.raises(ValueError):
        await _act(target.adapter(), "create_keyspace", None, {"name": "bad name"})


async def test_a_keyspace_that_holds_tables_needs_the_cascade(target: Target) -> None:
    adapter = target.adapter()
    action = adapter.action("drop_keyspace")

    preview = await action.preview(KEYSPACE, {})  # type: ignore[attr-defined]  # the drop previews

    assert preview.blocked
    assert any("tables" in item for item in preview.items)
    with pytest.raises(ActionRefused):
        await _act(adapter, "drop_keyspace", KEYSPACE, {})


# --- Tables --------------------------------------------------------------------


async def test_a_table_is_truncated(target: Target) -> None:
    adapter = target.adapter()
    await run(target, f"CREATE TABLE {KEYSPACE}.scratch (a int PRIMARY KEY)")
    await run(target, f"INSERT INTO {KEYSPACE}.scratch (a) VALUES (1)")

    await _act(adapter, "truncate_table", f"{KEYSPACE}.scratch", {})

    assert (await adapter.fetch(FetchRequest(node_id=f"{KEYSPACE}.scratch"))).rows == []


async def test_dropping_a_table_drops_the_views_over_it_and_says_so(
    target: Target,
) -> None:
    adapter = target.adapter()
    await run(target, f"CREATE TABLE {KEYSPACE}.base (a int PRIMARY KEY, b int)")
    await run(
        target,
        f"CREATE MATERIALIZED VIEW {KEYSPACE}.base_by_b AS SELECT a, b FROM {KEYSPACE}.base "
        "WHERE b IS NOT NULL AND a IS NOT NULL PRIMARY KEY (b, a)",
    )
    action = adapter.action("drop_relation")

    preview = await action.preview(f"{KEYSPACE}.base", {})  # type: ignore[attr-defined]  # the drop previews
    await _act(adapter, "drop_relation", f"{KEYSPACE}.base", {})
    left = {node.name for node in await adapter.list_children(KEYSPACE)}

    assert any("base_by_b" in item for item in preview.items)
    assert "base" not in left and "base_by_b" not in left


# --- The designer --------------------------------------------------------------


async def test_the_designer_plans_the_key_from_the_partition_parameter(
    target: Target,
) -> None:
    adapter = target.adapter()
    options = await adapter.table_design_options(KEYSPACE)

    plan = await adapter.plan_table(
        TablePlanRequest(node_id=KEYSPACE, definition=_definition("designed"))
    )

    assert options.supported and [engine.code for engine in options.engines] == [
        "table"
    ]
    assert plan.problems == []
    assert 'PRIMARY KEY (("tenant", "day"), "seq")' in plan.statements[0].sql
    assert '"tags" list<text>' in plan.statements[0].sql
    assert "WITH comment = 'Made by the designer'" in plan.statements[0].sql


async def test_the_designer_names_what_cql_has_not_got(target: Target) -> None:
    adapter = target.adapter()

    no_key = await adapter.plan_table(
        TablePlanRequest(
            node_id=KEYSPACE, definition=_definition("x", primary_key=None)
        )
    )
    unique = await adapter.plan_table(
        TablePlanRequest(
            node_id=KEYSPACE,
            definition=_definition(
                "x", unique_constraints=[{"id": "u1", "column_ids": ["c3"]}]
            ),
        )
    )
    not_leading = await adapter.plan_table(
        TablePlanRequest(
            node_id=KEYSPACE,
            definition=_definition(
                "x",
                engine={
                    "code": "table",
                    "arguments": [{"code": "partition", "column_ids": ["c2"]}],
                },
            ),
        )
    )
    taken = await adapter.plan_table(
        TablePlanRequest(node_id=KEYSPACE, definition=_definition("many"))
    )

    assert no_key.problems and no_key.statements == []
    assert [problem.object_id for problem in unique.problems] == ["u1"]
    assert not_leading.problems
    assert taken.problems[0].kind == "conflict"


async def test_a_designed_table_is_created_with_its_index(target: Target) -> None:
    adapter = target.adapter()
    method = "global" if target.scylla else "sai"
    definition = _definition(
        "designed_here",
        indexes=[
            {
                "id": "i1",
                "method": method,
                "keys": [{"kind": "column", "column_id": "c4"}],
            }
        ],
    )
    plan = await adapter.plan_table(
        TablePlanRequest(node_id=KEYSPACE, definition=definition)
    )
    assert plan.problems == [], plan.problems

    result = await _act(
        adapter,
        "create_table",
        KEYSPACE,
        {"definition": definition.model_dump(), "fingerprint": plan.fingerprint},
    )
    model = await adapter.relation_model(f"{KEYSPACE}.designed_here")

    assert result.created_node_id == f"{KEYSPACE}.designed_here"
    assert [column.name for column in model.columns[:3]] == ["tenant", "day", "seq"]
    assert (
        model.columns[0].comment == "Partition key"
        and model.columns[1].comment == "Partition key"
    )
    assert [index.name for index in model.indexes] == ["designed_here_tags_idx"]


async def test_a_stale_plan_is_refused(target: Target) -> None:
    with pytest.raises(ActionRefused):
        await _act(
            target.adapter(),
            "create_table",
            KEYSPACE,
            {"definition": _definition("never").model_dump(), "fingerprint": "0" * 64},
        )


# --- Reports -------------------------------------------------------------------


async def test_the_cluster_section_lists_its_reports(target: Target) -> None:
    adapter = target.adapter()

    roots = await adapter.list_children(None)
    reports = await adapter.list_children("\\cluster")

    assert isinstance(roots[-1], ReportNode)
    assert [node.id for node in reports] == [
        "\\cluster/nodes",
        "\\cluster/clients",
        "\\cluster/sizes",
        "\\cluster/settings",
        "\\cluster/roles",
    ]


@pytest.mark.parametrize("key", ["nodes", "clients", "sizes", "settings", "roles"])
async def test_every_report_reads(target: Target, key: str) -> None:
    page = await target.adapter().fetch(
        FetchRequest(node_id=f"\\cluster/{key}", limit=1000)
    )

    assert page.columns
    assert not page.update_supported and not page.record_supported
    if key in ("nodes", "settings", "roles", "clients"):
        assert page.rows


async def test_a_report_says_what_it_reads_and_refuses_a_filter(target: Target) -> None:
    adapter = target.adapter()

    content = await adapter.read_content(
        ContentRequest(node_id="\\cluster/nodes", representation="sql")
    )
    with pytest.raises(ValueError):
        await adapter.fetch(
            FetchRequest(
                node_id="\\cluster/nodes",
                filters=[ScalarFilter(column="address", op="eq", value="x")],
            )
        )

    assert isinstance(content, SqlContent) and "system.peers" in content.text


# --- Search and export ---------------------------------------------------------


async def test_names_are_found_by_their_words(target: Target) -> None:
    adapter = target.adapter()

    everywhere = await adapter.search_nodes(NodeSearchRequest(query="items"))
    inside = await adapter.search_nodes(
        NodeSearchRequest(node_id=KEYSPACE, query="many")
    )
    reports = await adapter.search_nodes(
        NodeSearchRequest(node_id="\\cluster", query="roles")
    )

    assert f"{KEYSPACE}.items" in [match.node.id for match in everywhere.matches]
    assert [match.node.id for match in inside.matches] == [f"{KEYSPACE}.many"]
    assert [match.node.id for match in reports.matches] == ["\\cluster/roles"]


async def test_relations_are_found_by_a_column_or_their_comment(target: Target) -> None:
    adapter = target.adapter()

    by_column = await adapter.search_columns(
        NodeSearchRequest(node_id=KEYSPACE, query="word")
    )
    by_comment = await adapter.search_columns(
        NodeSearchRequest(node_id=KEYSPACE, query="things")
    )

    assert [(match.node.id, match.excerpt) for match in by_column.matches] == [
        (f"{KEYSPACE}.many", "word")
    ]
    assert [match.node.id for match in by_comment.matches] == [f"{KEYSPACE}.items"]


async def test_every_name_is_enumerated(target: Target) -> None:
    import time

    names = [
        kept.node.id
        async for batch in target.adapter().enumerate_names(
            100_000, SearchBounds(deadline=time.monotonic() + 30)
        )
        for kept in batch.names
    ]

    assert KEYSPACE in names and f"{KEYSPACE}.many" in names


async def test_every_matching_row_is_exported(target: Target) -> None:
    rows = [
        row
        async for batch in target.adapter().export_rows(
            ExportRequest(
                node_id=f"{KEYSPACE}.many",
                columns=["word", "p"],
                filters=[ScalarFilter(column="v", op="eq", value="4")],
            )
        )
        for row in batch.rows
    ]

    assert len(rows) == 25
    assert all(word == f"w{p}" for word, p in rows)
