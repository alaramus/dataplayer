"""Editing what a key holds, one element at a time, against a real server.

The actions next door write a whole key; this is the grid's ordinary editing
contract answered by a source with no rows and no versions of its own. What
stands in for a version is a fingerprint of what the page showed, so the tests
here are as much about the refusals as about the writes.
"""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.fetch import FetchRequest
from app.adapters.protocol import (
    SupportsDelete,
    SupportsInsert,
    SupportsUpdate,
)
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, key_id
from app.adapters.update import (
    CellEdit,
    DeleteRowsRequest,
    InsertRowRequest,
    InsertValue,
    RowConflict,
    RowEdit,
    UpdateCellRequest,
    UpdateCellsRequest,
)
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

DB = chosen_database()


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
def adapter() -> RedisAdapter:
    return RedisAdapter(redis_options())


async def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(
        host=options.host, port=options.port, db=options.database
    )


async def _page(adapter: RedisAdapter, name: str):
    return await adapter.fetch(FetchRequest(node_id=key_id(DB, name), limit=100))


def _handle(page, index: int) -> str:
    handle = page.row_handles[index]
    assert handle is not None
    return handle


# --- what a page of a key says about itself --------------------------------


async def test_the_type_says_it_can_edit_insert_and_delete() -> None:
    """Read off the driver, so a screen cannot offer what would be refused."""
    assert issubclass(RedisAdapter, SupportsUpdate)
    assert issubclass(RedisAdapter, SupportsInsert)
    assert issubclass(RedisAdapter, SupportsDelete)


async def test_a_hash_offers_both_of_its_columns(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada", "city": "London"})
    finally:
        await client.aclose()

    page = await _page(adapter, "person")

    assert page.update_supported is True
    assert page.insert_supported is True
    assert page.delete_supported is True
    assert [column.editable for column in page.columns] == [True, True]
    assert all(handle is not None for handle in page.row_handles)


async def test_a_list_does_not_offer_its_positions(adapter: RedisAdapter) -> None:
    """Where an element is is not something it holds, and a list whose places
    could be typed is a list where two rows claim one."""
    client = await _client()
    try:
        await client.rpush("queue", "first", "second")
    finally:
        await client.aclose()

    page = await _page(adapter, "queue")

    assert [column.name for column in page.columns] == ["index", "value"]
    assert [column.editable for column in page.columns] == [False, True]
    # And an element cannot be taken out by position without rewriting it.
    assert page.delete_supported is False
    assert "cannot be removed by position" in (page.delete_reason or "")


async def test_a_string_key_has_one_row_and_no_rows_to_add(
    adapter: RedisAdapter,
) -> None:
    client = await _client()
    try:
        await client.set("greeting", "hello")
    finally:
        await client.aclose()

    page = await _page(adapter, "greeting")

    assert page.update_supported is True
    assert page.insert_supported is False
    assert "holds one value" in (page.insert_reason or "")
    assert page.delete_supported is False


async def test_a_stream_is_read_and_not_written(adapter: RedisAdapter) -> None:
    """An entry is an event: it was written once, by whatever wrote it."""
    client = await _client()
    try:
        await client.xadd("events", {"kind": "started"})
    finally:
        await client.aclose()

    page = await _page(adapter, "events")

    assert page.update_supported is False
    assert "written once" in (page.update_reason or "")
    assert page.row_handles == []


# --- changing one cell -----------------------------------------------------


async def test_the_value_of_a_string_key_is_written(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.set("greeting", "hello")
        page = await _page(adapter, "greeting")

        result = await adapter.update_cell(
            UpdateCellRequest(
                node_id=key_id(DB, "greeting"),
                row_handle=_handle(page, 0),
                column="value",
                value="good day",
            )
        )

        assert result.values == ["good day"]
        assert await client.get("greeting") == b"good day"
    finally:
        await client.aclose()


async def test_writing_a_value_keeps_the_deadline_somebody_set(
    adapter: RedisAdapter,
) -> None:
    """Editing what a key holds is not a statement about how long it lives."""
    client = await _client()
    try:
        await client.set("greeting", "hello", ex=600)
        page = await _page(adapter, "greeting")

        await adapter.update_cell(
            UpdateCellRequest(
                node_id=key_id(DB, "greeting"),
                row_handle=_handle(page, 0),
                column="value",
                value="good day",
            )
        )

        assert await client.ttl("greeting") > 0
    finally:
        await client.aclose()


async def test_a_field_of_a_hash_is_renamed_rather_than_duplicated(
    adapter: RedisAdapter,
) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada"})
        page = await _page(adapter, "person")

        await adapter.update_cell(
            UpdateCellRequest(
                node_id=key_id(DB, "person"),
                row_handle=_handle(page, 0),
                column="field",
                value="given_name",
            )
        )

        assert await client.hgetall("person") == {b"given_name": b"Ada"}
    finally:
        await client.aclose()


async def test_the_score_of_a_member_is_written(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.zadd("board", {"ada": 1})
        page = await _page(adapter, "board")

        await adapter.update_cell(
            UpdateCellRequest(
                node_id=key_id(DB, "board"),
                row_handle=_handle(page, 0),
                column="score",
                value="12.5",
            )
        )

        assert await client.zscore("board", "ada") == 12.5
    finally:
        await client.aclose()


async def test_a_position_cannot_be_typed_over(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.rpush("queue", "first")
        page = await _page(adapter, "queue")

        with pytest.raises(ValueError, match="cannot be edited"):
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id=key_id(DB, "queue"),
                    row_handle=_handle(page, 0),
                    column="index",
                    value="7",
                )
            )
    finally:
        await client.aclose()


async def test_a_cell_cannot_be_emptied_because_redis_holds_no_nulls(
    adapter: RedisAdapter,
) -> None:
    client = await _client()
    try:
        await client.set("greeting", "hello")
        page = await _page(adapter, "greeting")

        with pytest.raises(ValueError, match="no nulls"):
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id=key_id(DB, "greeting"),
                    row_handle=_handle(page, 0),
                    column="value",
                    value=None,
                )
            )
    finally:
        await client.aclose()


# --- what was read is what is written --------------------------------------


async def test_an_element_changed_since_it_was_read_is_refused(
    adapter: RedisAdapter,
) -> None:
    """The whole of this source's optimistic locking: there is no version to
    compare, so what was shown is compared instead."""
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada"})
        page = await _page(adapter, "person")
        await client.hset("person", "name", "Grace")

        with pytest.raises(RowConflict):
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id=key_id(DB, "person"),
                    row_handle=_handle(page, 0),
                    column="value",
                    value="Ada Lovelace",
                )
            )
        assert await client.hget("person", "name") == b"Grace"
    finally:
        await client.aclose()


async def test_an_element_that_is_gone_is_refused(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada"})
        page = await _page(adapter, "person")
        await client.hdel("person", "name")

        with pytest.raises(RowConflict):
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id=key_id(DB, "person"),
                    row_handle=_handle(page, 0),
                    column="value",
                    value="Grace",
                )
            )
    finally:
        await client.aclose()


# --- a block of cells ------------------------------------------------------


async def test_a_block_with_an_unreadable_score_writes_nothing(
    adapter: RedisAdapter,
) -> None:
    """Named rather than counted, and nothing written: the values are in front
    of the person who pasted them."""
    client = await _client()
    try:
        await client.zadd("board", {"ada": 1, "grace": 2})
        page = await _page(adapter, "board")

        result = await adapter.update_cells(
            UpdateCellsRequest(
                node_id=key_id(DB, "board"),
                rows=[
                    RowEdit(
                        row_handle=_handle(page, 0),
                        cells=[CellEdit(column="score", value="3")],
                    ),
                    RowEdit(
                        row_handle=_handle(page, 1),
                        cells=[CellEdit(column="score", value="not a number")],
                    ),
                ],
            )
        )

        assert result.kind == "rejected"
        assert [cell.row for cell in result.cells] == [1]
        assert await client.zscore("board", "ada") == 1
    finally:
        await client.aclose()


# --- adding and removing an element ----------------------------------------


async def test_a_field_can_be_added_to_a_hash(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada"})

        await adapter.insert_row(
            InsertRowRequest(
                node_id=key_id(DB, "person"),
                values=[
                    InsertValue(column="field", value="city"),
                    InsertValue(column="value", value="London"),
                ],
            )
        )

        assert await client.hget("person", "city") == b"London"
    finally:
        await client.aclose()


async def test_a_new_row_needs_every_value_it_is_named_by(
    adapter: RedisAdapter,
) -> None:
    """Redis has no defaults: a field with no name is not a field."""
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada"})

        with pytest.raises(ValueError, match="needs a value"):
            await adapter.insert_row(
                InsertRowRequest(
                    node_id=key_id(DB, "person"),
                    values=[InsertValue(column="value", value="London")],
                )
            )
    finally:
        await client.aclose()


async def test_a_member_can_be_taken_out_of_a_set(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.sadd("tags", "red", "blue")
        page = await _page(adapter, "tags")

        result = await adapter.delete_rows(
            DeleteRowsRequest(
                node_id=key_id(DB, "tags"), row_handles=[_handle(page, 0)]
            )
        )

        assert result.deleted == 1
        assert await client.scard("tags") == 1
    finally:
        await client.aclose()


async def test_a_folder_is_not_something_to_type_over(adapter: RedisAdapter) -> None:
    """The keys under one are a listing; a name in it is a node rather than a
    value."""
    with pytest.raises(ValueError, match="Only what a key holds"):
        await adapter.delete_rows(
            DeleteRowsRequest(
                node_id=database_id(DB), row_handles=["anything"]
            )
        )
