"""Changing a Cassandra table's columns and secondary indexes (D346)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.column_changes import (
    AddColumnRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.indexes import CreateIndexRequest, DropIndexRequest, IndexCreated
from app.adapters.protocol import (
    SupportsAddColumn,
    SupportsDropColumn,
    SupportsIndexes,
    SupportsRenameColumn,
)
from tests.adapters.cassandra_fixture import (
    KEYSPACE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

TABLE = f"{KEYSPACE}.shapes"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    await run(
        chosen,
        "CREATE TABLE dp_test_cql.shapes (k int, c int, v text, PRIMARY KEY (k, c))",
    )
    yield chosen
    await tear_down(chosen)


async def test_the_model_offers_what_cql_can_change(target: Target) -> None:
    adapter = target.adapter()
    for capability in (
        SupportsAddColumn,
        SupportsDropColumn,
        SupportsRenameColumn,
        SupportsIndexes,
    ):
        assert isinstance(adapter, capability)

    model = await adapter.relation_model(TABLE)
    view = await adapter.relation_model(f"{KEYSPACE}.items_by_ok")

    assert model.column_changes_supported
    assert model.column_operations == ["add", "drop", "rename"]
    assert "list<text>" in [option.sql for option in model.column_type_options]
    methods = [option.code for option in model.index_methods]
    assert methods == (["global"] if target.scylla else ["sai", "legacy"])
    assert not view.column_changes_supported and view.column_changes_reason


async def test_a_column_is_added_and_dropped(target: Target) -> None:
    adapter = target.adapter()

    await adapter.add_column(
        AddColumnRequest(node_id=TABLE, name="tags", type_code="text_set")
    )
    added = await adapter.relation_model(TABLE)
    await adapter.drop_column(DropColumnRequest(node_id=TABLE, name="tags"))
    dropped = await adapter.relation_model(TABLE)

    assert "set<text>" in [
        column.type.sql for column in added.columns if column.name == "tags"
    ]
    assert "tags" not in [column.name for column in dropped.columns]


async def test_a_required_column_or_an_unknown_type_is_refused(target: Target) -> None:
    adapter = target.adapter()

    with pytest.raises(ValueError):
        await adapter.add_column(
            AddColumnRequest(node_id=TABLE, name="x", type_code="int", nullable=False)
        )
    with pytest.raises(ValueError):
        await adapter.add_column(
            AddColumnRequest(node_id=TABLE, name="x", type_code="money")
        )


async def test_a_key_column_is_neither_dropped_nor_a_regular_one_renamed(
    target: Target,
) -> None:
    adapter = target.adapter()

    with pytest.raises(ValueError):
        await adapter.drop_column(DropColumnRequest(node_id=TABLE, name="k"))
    with pytest.raises(ValueError, match="primary key"):
        await adapter.rename_column(
            RenameColumnRequest(node_id=TABLE, name="v", new_name="w")
        )


async def test_a_clustering_column_is_renamed(target: Target) -> None:
    adapter = target.adapter()

    await adapter.rename_column(
        RenameColumnRequest(node_id=TABLE, name="c", new_name="seq")
    )
    model = await adapter.relation_model(TABLE)
    await adapter.rename_column(
        RenameColumnRequest(node_id=TABLE, name="seq", new_name="c")
    )

    assert [column.name for column in model.columns[:2]] == ["k", "seq"]


async def test_an_index_is_made_on_one_column_and_dropped(target: Target) -> None:
    adapter = target.adapter()
    method = "global" if target.scylla else "sai"

    made = await adapter.create_index(
        CreateIndexRequest(node_id=TABLE, columns=["v"], method=method)
    )
    with_index = await adapter.relation_model(TABLE)
    assert isinstance(made, IndexCreated)
    await adapter.drop_index(DropIndexRequest(node_id=TABLE, name=made.name))
    without = await adapter.relation_model(TABLE)

    assert made.name == "shapes_v_idx"
    assert [index.name for index in with_index.indexes] == ["shapes_v_idx"]
    assert without.indexes == []


async def test_an_index_of_two_columns_or_a_unique_one_is_refused(
    target: Target,
) -> None:
    adapter = target.adapter()

    with pytest.raises(ValueError):
        await adapter.create_index(
            CreateIndexRequest(node_id=TABLE, columns=["v", "c"], method="legacy")
        )
    with pytest.raises(ValueError):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=TABLE, columns=["v"], method="legacy", unique=True
            )
        )
    with pytest.raises(ValueError):
        await adapter.create_index(
            CreateIndexRequest(node_id=TABLE, columns=["v"], method="hash")
        )


async def test_a_column_a_view_reads_is_refused_in_the_servers_words(
    target: Target,
) -> None:
    with pytest.raises(ValueError):
        await target.adapter().drop_column(
            DropColumnRequest(node_id=f"{KEYSPACE}.items", name="ok")
        )
