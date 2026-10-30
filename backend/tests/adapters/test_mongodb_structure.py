"""A collection's fields changed in every document, and its indexes (D288)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from bson import Int64

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.database_ids import relation_id
from app.adapters.indexes import (
    CreateIndexRequest,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
)
from tests.adapters.mongodb_fixture import (
    DATABASE,
    adapter,
    build,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

PEOPLE = relation_id(DATABASE, "people")
NUMBERS = relation_id(DATABASE, "numbers")


@pytest.fixture
async def server() -> AsyncIterator[None]:
    """Rebuilt for every test: each one changes structure."""
    MONGODB.require()
    await build()
    yield
    await tear_down()


async def _all(collection: str) -> list[dict[str, Any]]:
    client = raw_client()
    try:
        return await client[DATABASE][collection].find().sort("_id", 1).to_list()
    finally:
        await client.close()


@pytest.mark.usefixtures("server")
async def test_a_collection_says_what_may_be_changed_and_a_view_does_not() -> None:
    model = await adapter().relation_model(PEOPLE)

    assert model.column_changes_supported
    assert model.column_operations == ["add", "drop", "rename", "type"]
    assert "long" in {option.code for option in model.column_type_options}
    assert model.index_changes_supported
    methods = {method.code: method for method in model.index_methods}
    assert methods["ascending"].unique_supported
    assert not methods["hashed"].multi_column_supported

    view = await adapter().relation_model(relation_id(DATABASE, "adults"))
    assert not view.column_changes_supported
    assert view.column_changes_reason is not None


@pytest.mark.usefixtures("server")
async def test_a_field_is_added_to_every_document_that_lacks_it() -> None:
    await adapter().add_column(AddColumnRequest(node_id=PEOPLE, name="email", type_code="string"))

    assert all(document.get("email", "missing") is None for document in await _all("people"))
    model = await adapter().relation_model(PEOPLE)
    assert "email" in {column.name for column in model.columns}
    with pytest.raises(ValueError, match="there already"):
        await adapter().add_column(AddColumnRequest(node_id=PEOPLE, name="name", type_code="string"))
    with pytest.raises(ValueError):
        await adapter().add_column(AddColumnRequest(node_id=PEOPLE, name="a.b", type_code="string"))


@pytest.mark.usefixtures("server")
async def test_a_field_is_dropped_and_renamed_in_every_document() -> None:
    await adapter().drop_column(DropColumnRequest(node_id=NUMBERS, name="label"))
    assert all("label" not in document for document in await _all("numbers"))

    await adapter().rename_column(RenameColumnRequest(node_id=NUMBERS, name="n", new_name="remainder"))
    documents = await _all("numbers")
    assert all("n" not in document and "remainder" in document for document in documents)
    assert documents[13]["remainder"] == 6

    with pytest.raises(ValueError, match="_id"):
        await adapter().drop_column(DropColumnRequest(node_id=NUMBERS, name="_id"))
    with pytest.raises(ValueError, match="cannot be changed by a query"):
        await adapter().drop_column(DropColumnRequest(node_id=NUMBERS, name="$where"))
    with pytest.raises(ValueError, match="no column"):
        await adapter().drop_column(DropColumnRequest(node_id=NUMBERS, name="nope"))


@pytest.mark.usefixtures("server")
async def test_a_type_change_converts_every_value_or_none() -> None:
    blocked = await adapter().change_column_type(
        ColumnTypeRequest(node_id=NUMBERS, name="label", type_code="int")
    )
    assert isinstance(blocked, ColumnTypeBlocked)
    assert (blocked.rows_not_convertible, blocked.exact) == (250, True)
    assert (await _all("numbers"))[0]["label"] == "row 000"

    changed = await adapter().change_column_type(
        ColumnTypeRequest(node_id=NUMBERS, name="n", type_code="long")
    )
    assert isinstance(changed, ColumnTypeChanged)
    assert changed.type_sql == "long"
    documents = await _all("numbers")
    assert isinstance(documents[3]["n"], Int64)
    assert documents[3]["n"] == 3

    text = await adapter().change_column_type(
        ColumnTypeRequest(node_id=NUMBERS, name="n", type_code="string")
    )
    assert isinstance(text, ColumnTypeChanged)
    assert (await _all("numbers"))[3]["n"] == "3"


@pytest.mark.usefixtures("server")
async def test_an_index_is_made_and_dropped() -> None:
    made = await adapter().create_index(
        CreateIndexRequest(node_id=NUMBERS, columns=["n", "label"], method="descending")
    )
    assert isinstance(made, IndexCreated)
    assert made.name == "n_-1_label_-1"
    model = await adapter().relation_model(NUMBERS)
    assert made.name in {index.name for index in model.indexes}

    dropped = await adapter().drop_index(DropIndexRequest(node_id=NUMBERS, name=made.name))
    assert dropped.name == made.name
    with pytest.raises(ValueError, match="_id"):
        await adapter().drop_index(DropIndexRequest(node_id=NUMBERS, name="_id_"))
    with pytest.raises(ValueError, match="no index"):
        await adapter().drop_index(DropIndexRequest(node_id=NUMBERS, name="nope"))


@pytest.mark.usefixtures("server")
async def test_a_unique_index_over_repeated_values_is_counted_and_not_made() -> None:
    blocked = await adapter().create_index(
        CreateIndexRequest(node_id=NUMBERS, columns=["n"], method="ascending", unique=True)
    )
    assert isinstance(blocked, IndexBlocked)
    assert blocked.duplicate_groups == 7

    made = await adapter().create_index(
        CreateIndexRequest(node_id=NUMBERS, columns=["label"], method="ascending", unique=True)
    )
    assert isinstance(made, IndexCreated)


@pytest.mark.usefixtures("server")
async def test_what_an_index_kind_cannot_do_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot be unique"):
        await adapter().create_index(
            CreateIndexRequest(node_id=NUMBERS, columns=["n"], method="hashed", unique=True)
        )
    with pytest.raises(ValueError, match="one field"):
        await adapter().create_index(
            CreateIndexRequest(node_id=NUMBERS, columns=["n", "label"], method="hashed")
        )
    with pytest.raises(ValueError, match="Unknown"):
        await adapter().create_index(
            CreateIndexRequest(node_id=NUMBERS, columns=["n"], method="btree")
        )
