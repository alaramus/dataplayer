"""Changing the documents of a MongoDB collection from the grid (D287)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from bson import Decimal128, Int64, ObjectId

from app.adapters.content import ContentRequest, JsonLinesContent, JsonObject
from app.adapters.database_ids import relation_id
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.mongodb.rows import (
    canonical,
    digest,
    from_canonical,
    handle_of,
    written_value,
)
from app.adapters.update import (
    CellEdit,
    CellsRejected,
    CellsUpdated,
    DeleteRowsRequest,
    InsertRowRequest,
    InsertRowsRequest,
    InsertValue,
    RowConflict,
    RowEdit,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellsRequest,
    ValuesRejected,
)
from tests.adapters.mongodb_fixture import (
    DATABASE,
    PEOPLE_IDS,
    adapter,
    build,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

PEOPLE = relation_id(DATABASE, "people")
NUMBERS = relation_id(DATABASE, "numbers")
BOOKS = relation_id(DATABASE, "books")


@pytest.fixture
async def server() -> AsyncIterator[None]:
    """Rebuilt for every test: each one writes."""
    MONGODB.require()
    await build()
    yield
    await tear_down()


async def _page(node_id: str, **filters: str) -> tuple[list[str], list[list[str | None]], list[str | None]]:
    page = await adapter().fetch(
        FetchRequest(
            node_id=node_id,
            filters=[ScalarFilter(column=name, op="eq", value=value) for name, value in filters.items()],
        )
    )
    return [column.name for column in page.columns], page.rows, page.row_handles


async def _stored(collection: str, key: object) -> dict[str, object] | None:
    client = raw_client()
    try:
        return await client[DATABASE][collection].find_one({"_id": key})
    finally:
        await client.close()


# --- Without a server ------------------------------------------------------


def test_an_id_of_any_type_survives_its_handle() -> None:
    for key in (ObjectId("650000000000000000000001"), 7, Int64(7), "seven", {"a": 1}):
        assert from_canonical(canonical(key)) == key
        assert type(from_canonical(canonical(key))) is type(key)
    assert handle_of({"x": 1}) is None
    assert digest({"_id": 1, "a": 1}) != digest({"_id": 1, "a": 2})


def test_a_typed_in_value_is_stored_as_its_field_holds_it() -> None:
    assert written_value("5", "int") == 5
    assert written_value("1.10", "decimal") == Decimal128("1.10")
    assert written_value("2026-01-02", "date") == datetime(2026, 1, 2, tzinfo=UTC)
    assert written_value('{"city": "Oslo", "n": {"$numberLong": "5"}}', "object") == {
        "city": "Oslo",
        "n": Int64(5),
    }
    assert written_value("[1, 2]", "array") == [1, 2]
    assert written_value("0x01FF", "binData") == b"\x01\xff"
    # A mixed field takes JSON when it is JSON, and text when it is not.
    assert written_value("42", "mixed") == 42
    assert written_value("hello", "mixed") == "hello"
    assert written_value(None, "string") is None
    for text, tag in [("[1]", "object"), ("{}", "array"), ("x", "int"), ("01FF", "binData")]:
        with pytest.raises(ValueError):
            written_value(text, tag)  # type: ignore[arg-type]  # each tag is a Tag


# --- What a page offers ------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_collection_s_page_is_editable_and_a_view_s_is_not() -> None:
    page = await adapter().fetch(FetchRequest(node_id=PEOPLE))
    columns = {column.name: column for column in page.columns}

    assert page.update_supported and page.insert_supported and page.delete_supported
    assert all(handle is not None for handle in page.row_handles)
    assert not columns["_id"].editable
    assert columns["_id"].insertable
    assert columns["name"].editable
    assert not columns["odd.field"].editable

    view = await adapter().fetch(FetchRequest(node_id=relation_id(DATABASE, "adults")))
    assert not view.update_supported
    assert view.update_reason is not None
    system = await adapter().fetch(FetchRequest(node_id=relation_id("admin", "system.version")))
    assert not system.insert_supported


# --- Changing a cell ----------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_cell_is_changed_as_its_field_s_type() -> None:
    names, rows, handles = await _page(PEOPLE, name="Ann")

    answer = await adapter().update_cell(
        UpdateCellRequest(node_id=PEOPLE, row_handle=handles[0] or "", column="age", value="32")
    )

    assert answer.values[names.index("age")] == "32"
    assert answer.row_handle != handles[0]
    stored = await _stored("people", PEOPLE_IDS[0])
    assert stored is not None
    assert stored["age"] == 32
    # Everything else in the document is as it was.
    assert stored["price"] == Decimal128("1.10")


@pytest.mark.usefixtures("server")
async def test_a_nested_value_is_written_from_json() -> None:
    _, _, handles = await _page(PEOPLE, name="Bob")

    await adapter().update_cell(
        UpdateCellRequest(
            node_id=PEOPLE,
            row_handle=handles[0] or "",
            column="address",
            value='{"city": "Oslo", "since": {"$date": "2020-01-01T00:00:00Z"}}',
        )
    )

    stored = await _stored("people", PEOPLE_IDS[1])
    assert stored is not None
    assert stored["address"] == {"city": "Oslo", "since": datetime(2020, 1, 1, tzinfo=UTC)}


@pytest.mark.usefixtures("server")
async def test_a_document_changed_since_it_was_read_is_not_written() -> None:
    _, _, handles = await _page(PEOPLE, name="Ann")
    client = raw_client()
    try:
        await client[DATABASE]["people"].update_one({"_id": PEOPLE_IDS[0]}, {"$set": {"age": 99}})
    finally:
        await client.close()

    with pytest.raises(RowConflict):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle=handles[0] or "", column="age", value="1")
        )
    stored = await _stored("people", PEOPLE_IDS[0])
    assert stored is not None
    assert stored["age"] == 99


@pytest.mark.usefixtures("server")
async def test_what_a_cell_cannot_be_is_refused_before_anything_is_written() -> None:
    _, _, handles = await _page(PEOPLE, name="Ann")
    handle = handles[0] or ""

    with pytest.raises(ValueError, match="cannot be read"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle=handle, column="born", value="yesterday")
        )
    with pytest.raises(ValueError, match="cannot be edited"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle=handle, column="_id", value="x")
        )
    with pytest.raises(ValueError, match="no column"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle=handle, column="$set", value="x")
        )
    with pytest.raises(ValueError, match="not valid"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle="nonsense", column="age", value="1")
        )


@pytest.mark.usefixtures("server")
async def test_a_unique_index_s_refusal_is_said_in_its_own_words() -> None:
    _, _, handles = await _page(PEOPLE, name="Bob")

    with pytest.raises(ValueError, match="unique index"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=PEOPLE, row_handle=handles[0] or "", column="name", value="Ann")
        )


@pytest.mark.usefixtures("server")
async def test_a_pasted_block_is_checked_whole_then_written() -> None:
    _, rows, handles = await _page(NUMBERS)
    first, second = handles[0] or "", handles[1] or ""

    refused = await adapter().update_cells(
        UpdateCellsRequest(
            node_id=NUMBERS,
            rows=[
                RowEdit(row_handle=first, cells=[CellEdit(column="n", value="100")]),
                RowEdit(row_handle=second, cells=[CellEdit(column="n", value="many")]),
            ],
        )
    )
    assert isinstance(refused, CellsRejected)
    assert [(cell.row, cell.column) for cell in refused.cells] == [(1, "n")]
    assert (await _stored("numbers", 0) or {})["n"] == 0

    done = await adapter().update_cells(
        UpdateCellsRequest(
            node_id=NUMBERS,
            rows=[
                RowEdit(row_handle=first, cells=[CellEdit(column="n", value="100")]),
                RowEdit(row_handle=second, cells=[CellEdit(column="label", value="two")]),
            ],
        )
    )
    assert isinstance(done, CellsUpdated)
    assert (await _stored("numbers", 0) or {})["n"] == 100
    assert (await _stored("numbers", 1) or {})["label"] == "two"
    assert rows[0][0] == "0"


# --- Adding and deleting ------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_document_is_added_with_the_fields_given() -> None:
    answer = await adapter().insert_row(
        InsertRowRequest(
            node_id=PEOPLE,
            values=[
                InsertValue(column="name", value="Dee"),
                InsertValue(column="age", value="40"),
                InsertValue(column="tags", value=None),
            ],
        )
    )

    assert answer.row_handle is not None
    client = raw_client()
    try:
        stored = await client[DATABASE]["people"].find_one({"name": "Dee"})
    finally:
        await client.close()
    assert stored is not None
    assert isinstance(stored["_id"], ObjectId)
    # An empty value is no field at all.
    assert set(stored) == {"_id", "name", "age"}
    assert stored["age"] == 40


@pytest.mark.usefixtures("server")
async def test_a_validator_s_refusal_is_said() -> None:
    with pytest.raises(ValueError, match="validator"):
        await adapter().insert_row(
            InsertRowRequest(node_id=BOOKS, values=[InsertValue(column="pages", value="3")])
        )


@pytest.mark.usefixtures("server")
async def test_a_block_goes_in_whole_or_not_at_all() -> None:
    refused = await adapter().insert_rows(
        InsertRowsRequest(node_id=NUMBERS, columns=["_id", "n"], rows=[["1000", "1"], ["1001", "x"]])
    )
    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in refused.cells] == [(1, "n", "x")]

    # The second document's id is taken: the first is taken out again.
    with pytest.raises(ValueError, match="unique index"):
        await adapter().insert_rows(
            InsertRowsRequest(node_id=NUMBERS, columns=["_id", "n"], rows=[["1000", "1"], ["5", "1"]])
        )
    assert await _stored("numbers", 1000) is None

    done = await adapter().insert_rows(
        InsertRowsRequest(node_id=NUMBERS, columns=["_id", "n"], rows=[["1000", "1"], ["1001", "2"]])
    )
    assert isinstance(done, RowsInserted)
    assert done.inserted == 2
    assert (await _stored("numbers", 1001) or {})["n"] == 2


@pytest.mark.usefixtures("server")
async def test_documents_are_deleted_only_as_they_were_read() -> None:
    _, _, handles = await _page(NUMBERS)

    answer = await adapter().delete_rows(
        DeleteRowsRequest(node_id=NUMBERS, row_handles=[handles[0] or "", handles[1] or ""])
    )

    assert answer.deleted == 2
    assert await _stored("numbers", 0) is None
    client = raw_client()
    try:
        await client[DATABASE]["numbers"].update_one({"_id": 2}, {"$set": {"n": 50}})
    finally:
        await client.close()
    with pytest.raises(RowConflict):
        await adapter().delete_rows(DeleteRowsRequest(node_id=NUMBERS, row_handles=[handles[2] or ""]))
    assert await _stored("numbers", 2) is not None


@pytest.mark.usefixtures("server")
async def test_a_view_takes_no_document() -> None:
    with pytest.raises(ValueError, match="pipeline"):
        await adapter().insert_row(
            InsertRowRequest(
                node_id=relation_id(DATABASE, "adults"), values=[InsertValue(column="name", value="x")]
            )
        )


# --- Documents whole ------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_documents_are_read_whole_as_json_lines() -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=NUMBERS, representation="jsonl", limit=10, offset=240)
    )

    assert isinstance(content, JsonLinesContent)
    assert [item.line_number for item in content.items] == list(range(241, 251))
    assert not content.has_more
    first = content.items[0].value
    assert isinstance(first, JsonObject)
    assert [entry.name for entry in first.entries] == ["_id", "n", "label"]

    people = await adapter().read_content(ContentRequest(node_id=PEOPLE, representation="jsonl"))
    assert isinstance(people, JsonLinesContent)
    ann = people.items[0].value
    assert isinstance(ann, JsonObject)
    born = next(entry.value for entry in ann.entries if entry.name == "born")
    assert isinstance(born, JsonObject)
    assert born.entries[0].name == "$date"
