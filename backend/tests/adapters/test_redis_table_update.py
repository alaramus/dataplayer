"""A table declared over Redis, edited as its rows (D173), against a real server."""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.declared_tables import DeclaredTable
from app.adapters.fetch import FetchRequest
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import folder_id, table_id
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
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

DB = chosen_database()
TABLE = table_id(DB, "user:")


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
def adapter() -> RedisAdapter:
    table = DeclaredTable.model_validate(
        {
            "place_id": folder_id(DB, "user:"),
            "name": "users",
            "columns": [
                {"name": "name", "type": "text"},
                {"name": "age", "type": "number"},
                {"name": "active", "type": "boolean"},
            ],
        }
    )
    return RedisAdapter(redis_options(), [table])


async def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(
        host=options.host, port=options.port, db=options.database, decode_responses=True
    )


async def _users() -> None:
    client = await _client()
    try:
        await client.hset("user:1", mapping={"name": "Ada", "age": "36", "note": "kept"})
        await client.hset("user:2", mapping={"name": "Grace"})
    finally:
        await client.aclose()


async def _hash(name: str) -> dict[str, str]:
    client = await _client()
    try:
        return dict(await client.hgetall(name))
    finally:
        await client.aclose()


async def _handles(adapter: RedisAdapter) -> dict[str, str]:
    page = await adapter.fetch(FetchRequest(node_id=TABLE))
    return {
        str(row[0]): handle
        for row, handle in zip(page.rows, page.row_handles, strict=True)
        if handle is not None
    }


async def test_the_page_offers_every_field_and_never_the_key(adapter: RedisAdapter) -> None:
    await _users()

    page = await adapter.fetch(FetchRequest(node_id=TABLE))

    assert page.update_supported and page.insert_supported and page.delete_supported
    assert {c.name: (c.editable, c.insertable, c.insert_required) for c in page.columns} == {
        "key": (False, True, True),
        "name": (True, True, False),
        "age": (True, True, False),
        "active": (True, True, False),
    }
    assert len(page.row_handles) == 2 and all(page.row_handles)


async def test_a_cell_is_one_field_of_one_hash(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    changed = await adapter.update_cell(
        UpdateCellRequest(node_id=TABLE, row_handle=handles["1"], column="age", value="37")
    )
    # Emptied, the field is gone; the field no column shows stays.
    emptied = await adapter.update_cell(
        UpdateCellRequest(
            node_id=TABLE, row_handle=changed.row_handle, column="name", value=None
        )
    )

    assert changed.values == ["1", "Ada", "37", None]
    assert emptied.values == ["1", None, "37", None]
    assert await _hash("user:1") == {"age": "37", "note": "kept"}


async def test_the_key_and_what_is_not_declared_are_not_edited(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    for column, message in (("key", "where the row lives"), ("note", 'no column "note"')):
        with pytest.raises(ValueError, match=message):
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id=TABLE, row_handle=handles["1"], column=column, value="x"
                )
            )


async def test_a_value_is_checked_against_its_declared_type(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    with pytest.raises(ValueError, match='"age" takes a number'):
        await adapter.update_cell(
            UpdateCellRequest(node_id=TABLE, row_handle=handles["1"], column="age", value="old")
        )
    rejected = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=TABLE,
            rows=[
                RowEdit(row_handle=handles["1"], cells=[CellEdit(column="age", value="40")]),
                RowEdit(
                    row_handle=handles["2"], cells=[CellEdit(column="active", value="maybe")]
                ),
            ],
        )
    )

    assert isinstance(rejected, CellsRejected)
    assert [(cell.row, cell.column) for cell in rejected.cells] == [(1, "active")]
    # Nothing was written, the good cell included.
    assert (await _hash("user:1"))["age"] == "36"


async def test_a_block_of_cells_is_written_at_once(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    done = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=TABLE,
            rows=[
                RowEdit(row_handle=handles["1"], cells=[CellEdit(column="active", value="true")]),
                RowEdit(row_handle=handles["2"], cells=[CellEdit(column="age", value="45")]),
            ],
        )
    )

    assert isinstance(done, CellsUpdated)
    assert [row.values for row in done.rows] == [
        ["1", "Ada", "36", "true"],
        ["2", "Grace", "45", None],
    ]
    assert (await _hash("user:2")) == {"name": "Grace", "age": "45"}


async def test_what_changed_since_it_was_read_is_a_conflict(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)
    client = await _client()
    try:
        await client.hset("user:1", "age", "99")
        await client.delete("user:2")
    finally:
        await client.aclose()

    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(node_id=TABLE, row_handle=handles["1"], column="name", value="A")
        )
    with pytest.raises(RowConflict):
        await adapter.delete_rows(DeleteRowsRequest(node_id=TABLE, row_handles=[handles["2"]]))


async def test_the_last_field_is_not_emptied(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    with pytest.raises(ValueError, match="delete the row instead"):
        await adapter.update_cell(
            UpdateCellRequest(node_id=TABLE, row_handle=handles["2"], column="name", value="")
        )

    assert await _hash("user:2") == {"name": "Grace"}


async def test_a_new_row_is_a_new_hash(adapter: RedisAdapter) -> None:
    await _users()

    made = await adapter.insert_row(
        InsertRowRequest(
            node_id=TABLE,
            values=[
                InsertValue(column="key", value="3"),
                InsertValue(column="name", value="Linus"),
                InsertValue(column="age", value=""),
            ],
        )
    )

    assert made.values == ["3", "Linus", None, None]
    assert made.row_handle in (await _handles(adapter)).values()
    assert await _hash("user:3") == {"name": "Linus"}


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([("name", "X")], "needs a key"),
        ([("key", "4")], "at least one field"),
        ([("key", "1"), ("name", "X")], '"1" is already in this folder'),
        ([("key", "4:x"), ("name", "X")], "folder below"),
        ([("key", "4"), ("age", "four")], "takes a number"),
        ([("key", "4"), ("note", "x")], 'no column "note"'),
    ],
)
async def test_a_new_row_is_refused_and_writes_nothing(
    adapter: RedisAdapter, values: list[tuple[str, str]], message: str
) -> None:
    await _users()

    with pytest.raises(ValueError, match=message):
        await adapter.insert_row(
            InsertRowRequest(
                node_id=TABLE,
                values=[InsertValue(column=column, value=value) for column, value in values],
            )
        )

    assert await _hash("user:4") == {}
    assert await _hash("user:4:x") == {}


async def test_many_rows_are_checked_whole_then_written(adapter: RedisAdapter) -> None:
    await _users()

    bad = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=TABLE,
            columns=["key", "name", "age"],
            rows=[["5", "Eve", "20"], ["6", "Bob", "old"], ["5", "Twice", None]],
        )
    )
    with pytest.raises(ValueError, match='"1" is already in this folder'):
        await adapter.insert_rows(
            InsertRowsRequest(
                node_id=TABLE, columns=["key", "name"], rows=[["7", "Ok"], ["1", "Taken"]]
            )
        )
    good = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=TABLE, columns=["key", "name"], rows=[["5", "Eve"], ["6", "Bob"]]
        )
    )

    assert isinstance(bad, ValuesRejected)
    assert [(cell.row, cell.column) for cell in bad.cells] == [(1, "age"), (2, "key")]
    assert await _hash("user:7") == {}
    assert isinstance(good, RowsInserted) and good.inserted == 2
    assert await _hash("user:6") == {"name": "Bob"}


async def test_deleting_rows_deletes_their_keys(adapter: RedisAdapter) -> None:
    await _users()
    handles = await _handles(adapter)

    done = await adapter.delete_rows(
        DeleteRowsRequest(node_id=TABLE, row_handles=[handles["1"], handles["2"]])
    )

    assert done.deleted == 2
    assert await _hash("user:1") == {} and await _hash("user:2") == {}
