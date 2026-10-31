"""Documents read whole and changed field by field (D295)."""

import json
from collections.abc import AsyncIterator

import pytest
from bson import Decimal128, Int64

from app.adapters.content import ContentRequest, JsonContent, JsonObject
from app.adapters.database_ids import relation_id
from app.adapters.documents import (
    DocumentChangeRequest,
    DocumentsRequest,
    DocumentText,
    FieldChange,
    FieldChanges,
    SupportsDocuments,
)
from app.adapters.fetch import ScalarFilter, Sort
from app.adapters.mongodb.documents import differences
from app.adapters.update import RowConflict
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


@pytest.fixture
async def server() -> AsyncIterator[None]:
    """Rebuilt for every test: each one writes."""
    MONGODB.require()
    await build()
    yield
    await tear_down()


async def _stored(key: object) -> dict[str, object]:
    client = raw_client()
    try:
        found = await client[DATABASE]["people"].find_one({"_id": key})
    finally:
        await client.close()
    assert found is not None
    return found


async def _ann() -> tuple[str, str]:
    page = await adapter().read_documents(
        DocumentsRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="eq", value="Ann")])
    )
    [item] = page.items
    assert item.row_handle is not None
    return item.row_handle, item.text


def test_the_type_reads_documents() -> None:
    assert isinstance(adapter(), SupportsDocuments)


def test_only_what_differs_is_written() -> None:
    before = {"_id": 1, "a": Int64(5), "b": {"c": 1, "d": 2}, "e": [1, 2], "gone": True}
    after = {"_id": 1, "a": 5, "b": {"c": 1, "d": 3}, "e": [1, 2, 3], "new": "x"}

    sets, unsets = differences(before, after)

    # `a` reads the same, so the Int64 is not written back as an int.
    assert sets == {("b", "d"): 3, ("e",): [1, 2, 3], ("new",): "x"}
    assert unsets == [("gone",)]


# --- Reading ---------------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_page_is_the_grid_s_query_read_as_documents() -> None:
    page = await adapter().read_documents(
        DocumentsRequest(node_id=NUMBERS, limit=3, sort=[Sort(column="n", descending=True)])
    )

    assert [json.loads(item.text)["_id"] for item in page.items] == [6, 13, 20]
    assert page.has_more
    assert page.change_supported
    assert all(isinstance(item.value, JsonObject) for item in page.items)

    ann = (await adapter().read_documents(DocumentsRequest(node_id=PEOPLE, limit=1))).items[0]
    # Relaxed Extended JSON, as mongosh writes it, indented to be edited.
    assert '"$oid": "650000000000000000000001"' in ann.text
    assert '"$date": "1994-03-01T12:30:00Z"' in ann.text
    assert '"$numberDecimal": "1.10"' in ann.text

    view = await adapter().read_documents(DocumentsRequest(node_id=relation_id(DATABASE, "adults")))
    assert not view.change_supported
    assert view.change_reason is not None


# --- Changing ----------------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_an_edited_document_changes_only_its_edited_field() -> None:
    handle, text = await _ann()
    edited = json.loads(text)
    edited["age"] = 32
    edited["tags"] = ["a", "b", "c"]
    del edited["active"]

    answer = await adapter().change_document(
        DocumentChangeRequest(node_id=PEOPLE, row_handle=handle, change=DocumentText(text=json.dumps(edited)))
    )

    assert answer.changed == 3
    stored = await _stored(PEOPLE_IDS[0])
    assert stored["age"] == 32
    assert stored["tags"] == ["a", "b", "c"]
    assert "active" not in stored
    # What was not edited keeps its BSON type, though its text is a bare number.
    assert isinstance(stored["big"], Int64)
    assert stored["price"] == Decimal128("1.10")
    assert answer.item.row_handle != handle


@pytest.mark.usefixtures("server")
async def test_a_change_inside_an_object_leaves_its_other_fields() -> None:
    client = raw_client()
    try:
        await client[DATABASE]["people"].update_one(
            {"_id": PEOPLE_IDS[1]}, {"$set": {"address": {"city": "Riga", "zip": Int64(1001)}}}
        )
    finally:
        await client.close()
    page = await adapter().read_documents(
        DocumentsRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="eq", value="Bob")])
    )
    item = page.items[0]
    edited = json.loads(item.text)
    edited["address"]["city"] = "Oslo"

    answer = await adapter().change_document(
        DocumentChangeRequest(
            node_id=PEOPLE, row_handle=item.row_handle or "", change=DocumentText(text=json.dumps(edited))
        )
    )

    assert answer.changed == 1
    stored = await _stored(PEOPLE_IDS[1])
    assert stored["address"] == {"city": "Oslo", "zip": Int64(1001)}
    assert isinstance(stored["address"]["zip"], Int64)  # type: ignore[index]  # read back as a dict


@pytest.mark.usefixtures("server")
async def test_nothing_differing_writes_nothing() -> None:
    handle, text = await _ann()

    answer = await adapter().change_document(
        DocumentChangeRequest(node_id=PEOPLE, row_handle=handle, change=DocumentText(text=text))
    )

    assert answer.changed == 0
    assert answer.item.row_handle == handle


@pytest.mark.usefixtures("server")
async def test_fields_are_set_and_removed_by_path() -> None:
    handle, _ = await _ann()

    await adapter().change_document(
        DocumentChangeRequest(
            node_id=PEOPLE,
            row_handle=handle,
            change=FieldChanges(
                changes=[
                    FieldChange(path=["address", "city"], op="set", value='"Tallinn"'),
                    FieldChange(path=["seen"], op="set", value='{"$date": "2026-01-01T00:00:00Z"}'),
                    FieldChange(path=["tags"], op="unset"),
                ]
            ),
        )
    )

    stored = await _stored(PEOPLE_IDS[0])
    assert stored["address"] == {"city": "Tallinn"}
    assert stored["seen"].year == 2026  # type: ignore[attr-defined]  # a datetime
    assert "tags" not in stored


@pytest.mark.usefixtures("server")
async def test_what_cannot_be_written_is_refused_first() -> None:
    handle, text = await _ann()
    source = adapter()

    async def change(edited: str) -> None:
        await source.change_document(
            DocumentChangeRequest(node_id=PEOPLE, row_handle=handle, change=DocumentText(text=edited))
        )

    with pytest.raises(ValueError, match="not valid JSON"):
        await change("{ not json")
    with pytest.raises(ValueError, match="object"):
        await change("[1, 2]")
    changed_id = json.loads(text)
    changed_id["_id"] = {"$oid": "650000000000000000000099"}
    with pytest.raises(ValueError, match="_id"):
        await change(json.dumps(changed_id))
    with pytest.raises(ValueError, match="unique index"):
        await change(json.dumps({**json.loads(text), "name": "Bob"}))
    with pytest.raises(ValueError, match="_id"):
        await source.change_document(
            DocumentChangeRequest(
                node_id=PEOPLE,
                row_handle=handle,
                change=FieldChanges(changes=[FieldChange(path=["_id"], op="unset")]),
            )
        )
    assert (await _stored(PEOPLE_IDS[0]))["name"] == "Ann"


@pytest.mark.usefixtures("server")
async def test_a_field_no_query_can_name_is_kept_and_cannot_be_changed() -> None:
    page = await adapter().read_documents(
        DocumentsRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="eq", value="Cy")])
    )
    item = page.items[0]
    edited = json.loads(item.text)
    edited["name"] = "Cyril"

    await adapter().change_document(
        DocumentChangeRequest(
            node_id=PEOPLE, row_handle=item.row_handle or "", change=DocumentText(text=json.dumps(edited))
        )
    )
    stored = await _stored(PEOPLE_IDS[2])
    assert stored["odd.field"] == 1
    assert stored["name"] == "Cyril"

    page = await adapter().read_documents(
        DocumentsRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="eq", value="Cyril")])
    )
    edited = json.loads(page.items[0].text)
    edited["odd.field"] = 2
    with pytest.raises(ValueError, match="cannot be changed by a query"):
        await adapter().change_document(
            DocumentChangeRequest(
                node_id=PEOPLE,
                row_handle=page.items[0].row_handle or "",
                change=DocumentText(text=json.dumps(edited)),
            )
        )


@pytest.mark.usefixtures("server")
async def test_a_document_changed_since_it_was_read_is_not_written() -> None:
    handle, text = await _ann()
    client = raw_client()
    try:
        await client[DATABASE]["people"].update_one({"_id": PEOPLE_IDS[0]}, {"$set": {"age": 99}})
    finally:
        await client.close()

    with pytest.raises(RowConflict):
        await adapter().change_document(
            DocumentChangeRequest(
                node_id=PEOPLE,
                row_handle=handle,
                change=DocumentText(text=json.dumps({**json.loads(text), "age": 1})),
            )
        )
    assert (await _stored(PEOPLE_IDS[0]))["age"] == 99


# --- The definition ----------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_definition_is_a_tree_and_documents_are_not_content() -> None:
    content = await adapter().read_content(ContentRequest(node_id=PEOPLE, representation="tree"))

    assert isinstance(content, JsonContent)
    with pytest.raises(ValueError):
        await adapter().read_content(ContentRequest(node_id=PEOPLE, representation="jsonl"))
