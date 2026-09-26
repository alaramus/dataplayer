"""Tables declared over Redis folders, and what every Redis node is as a relation (D170).

Against a real server, like the rest of the Redis tests: whether a folder's
hashes read as rows is a question about what the driver does to a Redis.
"""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.catalog import DatabaseNode, DirectoryNode, KeyNode, TableNode
from app.adapters.declared_tables import (
    DeclaredColumn,
    DeclaredTable,
    DeclareTableRequest,
)
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import (
    NodeNotFound,
    SupportsDeclaredTables,
    SupportsExport,
    SupportsNodePath,
    SupportsRelationModel,
)
from app.adapters.redis import tables as redis_tables
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import (
    database_id,
    folder_id,
    key_id,
    table_id,
)
from app.adapters.redis.tables import guessed_type
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

DB = chosen_database()
USERS = folder_id(DB, "user:")
TABLE = table_id(DB, "user:")


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


def declared(*columns: tuple[str, str], place: str = USERS, name: str = "users") -> DeclaredTable:
    return DeclaredTable.model_validate(
        {
            "place_id": place,
            "name": name,
            "columns": [{"name": column, "type": kind} for column, kind in columns],
        }
    )


def adapter(*tables: DeclaredTable) -> RedisAdapter:
    return RedisAdapter(redis_options(), tables)


async def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(host=options.host, port=options.port, db=options.database)


async def _users() -> None:
    """Three users, one of them without an email, a string among them and a
    folder below them."""
    client = await _client()
    try:
        await client.hset("user:1", mapping={"name": "Ada", "email": "ada@example.com", "age": "36"})
        await client.hset("user:2", mapping={"name": "Grace", "age": "45"})
        await client.hset("user:10", mapping={"name": "Linus", "email": "l@example.com", "age": "x"})
        await client.set("user:count", "3")
        await client.hset("user:1:settings", mapping={"theme": "dark"})
    finally:
        await client.aclose()


def test_every_redis_node_is_described_located_exported_and_declarable() -> None:
    subject = adapter()

    assert isinstance(subject, SupportsRelationModel)
    assert isinstance(subject, SupportsNodePath)
    assert isinstance(subject, SupportsExport)
    assert isinstance(subject, SupportsDeclaredTables)


# --- where a table can stand ----------------------------------------------------


async def test_a_folder_can_carry_a_table_and_nothing_else_can() -> None:
    await _users()
    subject = adapter()

    place = await subject.table_place(USERS)

    assert (place.place_id, place.listed_in, place.declared) == (USERS, database_id(DB), None)
    for other in (database_id(DB), key_id(DB, "user:count"), "garbage"):
        with pytest.raises(ValueError, match="Select a folder"):
            await subject.table_place(other)


async def test_a_declared_table_names_its_folder() -> None:
    table = declared(("name", "text"))
    subject = adapter(table)

    place = await subject.table_place(TABLE)

    assert (place.place_id, place.declared) == (USERS, table)
    with pytest.raises(NodeNotFound):
        await adapter().table_place(TABLE)


async def test_a_nested_folder_is_listed_in_the_folder_above() -> None:
    subject = adapter()

    place = await subject.table_place(folder_id(DB, "app:user:"))

    assert place.listed_in == folder_id(DB, "app:")


# --- what the window starts from ------------------------------------------------


async def test_the_proposal_is_the_fields_of_the_first_hashes() -> None:
    await _users()

    proposal = await adapter().propose_table(USERS)

    assert proposal.name == "user"
    assert not proposal.declared
    # user:1:settings is below the folder, and user:count is a string.
    assert proposal.sampled == 3
    assert proposal.reserved == ["key"]
    found = {column.name: (column.type, column.ticked, column.found_in) for column in proposal.columns}
    assert found == {
        "name": ("text", True, 3),
        "email": ("text", True, 2),
        # One age is "x", so the three are not all numbers.
        "age": ("text", True, 3),
    }


async def test_the_sample_reads_only_the_first_hundred_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _users()
    monkeypatch.setattr(redis_tables, "SAMPLE_KEYS", 2)

    proposal = await adapter().propose_table(USERS)

    # By name: user:1 and user:10 come before user:2.
    assert proposal.sampled == 2
    assert {column.name: column.found_in for column in proposal.columns}["email"] == 2


async def test_a_declared_table_proposes_itself_first_and_the_rest_unticked() -> None:
    await _users()
    subject = adapter(declared(("email", "text"), ("phone", "number")))

    proposal = await subject.propose_table(TABLE)

    assert proposal.declared and proposal.name == "users"
    assert [(c.name, c.type, c.ticked, c.found_in) for c in proposal.columns] == [
        ("email", "text", True, 2),
        ("phone", "number", True, 0),
        ("name", "text", False, 3),
        ("age", "text", False, 3),
    ]


def test_a_type_is_guessed_from_every_sampled_value() -> None:
    assert guessed_type(["1", "2.5", "-3e2"]) == "number"
    assert guessed_type(["true", "False"]) == "boolean"
    assert guessed_type(["2026-09-25", "2026-09-25T10:00:00+00:00"]) == "datetime"
    assert guessed_type(["1", "one"]) == "text"
    assert guessed_type(["1_000"]) == "text"
    assert guessed_type(["", " "]) == "text"


async def test_a_declaration_is_checked_by_the_source() -> None:
    subject = adapter()

    kept = await subject.declared_table(
        DeclareTableRequest(
            node_id=USERS, name=" users ", columns=[DeclaredColumn(name="name")]
        )
    )

    assert kept == declared(("name", "text"))
    with pytest.raises(ValueError, match="cannot be called key"):
        await subject.declared_table(
            DeclareTableRequest(node_id=USERS, name="users", columns=[DeclaredColumn(name="key")])
        )
    with pytest.raises(ValueError, match="same name"):
        DeclareTableRequest.model_validate(
            {"node_id": USERS, "name": "u", "columns": [{"name": "a"}, {"name": "a"}]}
        )


# --- in the catalog -------------------------------------------------------------


async def test_the_table_stands_beside_its_folder() -> None:
    await _users()
    subject = adapter(declared(("name", "text")))

    listed = await subject.list_children(database_id(DB))
    inside = await subject.list_children(USERS)

    assert [(node.kind, node.name) for node in listed] == [
        ("directory", "user:"),
        ("table", "users"),
    ]
    table = listed[1]
    assert isinstance(table, TableNode)
    assert table.id == TABLE and table.describable
    assert table.declared_over == "user:"
    assert [one.kind for one in table.representations] == ["table"]
    # The folder is as it was: its keys remain keys of their own.
    assert {node.name for node in inside} >= {"1", "2", "10", "count"}
    assert await subject.available(TABLE) == []


async def test_a_table_over_an_empty_folder_still_stands() -> None:
    subject = adapter(declared(("name", "text")))

    listed = await subject.list_children(database_id(DB))

    assert [(node.kind, node.name) for node in listed] == [("table", "users")]
    page = await subject.fetch(FetchRequest(node_id=TABLE))
    assert page.rows == []


# --- as rows --------------------------------------------------------------------


async def test_the_table_reads_one_row_per_hash_in_key_order() -> None:
    await _users()
    subject = adapter(declared(("name", "text"), ("email", "text"), ("age", "number")))

    page = await subject.fetch(FetchRequest(node_id=TABLE))

    assert [column.name for column in page.columns] == ["key", "name", "email", "age"]
    assert [column.type.category for column in page.columns] == [
        "string", "string", "string", "number",
    ]
    assert page.rows == [
        ["1", "Ada", "ada@example.com", "36"],
        ["10", "Linus", "l@example.com", "x"],
        # A field a hash lacks is an empty cell.
        ["2", "Grace", None, "45"],
    ]
    assert not page.has_more
    # user:count is a string: not a row, and said so.
    assert page.notice == "1 key of another type is not a row"
    assert not page.update_supported and page.update_reason == "A declared table is read-only"
    assert not page.insert_supported and not page.delete_supported
    assert not any(column.sortable or column.filter_operators for column in page.columns)


async def test_the_table_pages_over_its_hashes() -> None:
    await _users()
    subject = adapter(declared(("name", "text")))

    first = await subject.fetch(FetchRequest(node_id=TABLE, limit=2))
    second = await subject.fetch(FetchRequest(node_id=TABLE, offset=2, limit=2))

    assert [row[0] for row in first.rows] == ["1", "10"] and first.has_more
    assert [row[0] for row in second.rows] == ["2"] and not second.has_more


async def test_a_folder_past_the_ceiling_is_shown_in_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await _client()
    try:
        for number in range(30):
            await client.hset(f"user:{number}", mapping={"name": str(number)})
    finally:
        await client.aclose()
    monkeypatch.setattr(redis_tables, "TABLE_CEILING", 10)

    page = await adapter(declared(("name", "text"))).fetch(FetchRequest(node_id=TABLE))

    assert page.notice == "Only 10 keys under this folder were read; the rest are not shown"
    assert 10 <= len(page.rows) < 30


async def test_a_table_nobody_declared_is_not_there() -> None:
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=TABLE))


# --- as a relation, and where it lies -------------------------------------------


async def test_each_node_has_a_relation_model() -> None:
    await _users()
    client = await _client()
    try:
        await client.rpush("queue", "a", "b")
    finally:
        await client.aclose()
    subject = adapter(declared(("name", "text"), ("age", "number")))

    table = await subject.relation_model(TABLE)
    key = await subject.relation_model(key_id(DB, "user:1"))
    listing = await subject.relation_model(USERS)
    database = await subject.relation_model(database_id(DB))
    queue = await subject.relation_model(key_id(DB, "queue"))

    assert (table.kind, table.name) == ("declared_table", "users")
    assert [(c.name, c.type.category) for c in table.columns] == [
        ("key", "string"), ("name", "string"), ("age", "number"),
    ]
    assert (key.kind, key.name, key.row_estimate) == ("key", "user:1", 3)
    assert [c.name for c in key.columns] == ["field", "value"]
    assert [c.name for c in queue.columns] == ["index", "value"]
    assert (listing.kind, listing.name) == ("key_listing", "user")
    assert [c.name for c in listing.columns] == ["key", "type", "ttl", "size"]
    assert database.name == f"db{DB}"
    with pytest.raises(NodeNotFound):
        await subject.relation_model(key_id(DB, "user:gone"))


async def test_each_node_has_a_path() -> None:
    await _users()
    subject = adapter(declared(("name", "text"), place=folder_id(DB, "user:1:")))

    key = await subject.path_to(key_id(DB, "user:1:settings"))
    table = await subject.path_to(table_id(DB, "user:1:"))
    folder = await subject.path_to(folder_id(DB, "user:1:"))
    database = await subject.path_to(database_id(DB))

    assert [(node.kind, node.name) for node in key] == [
        ("database", f"db{DB}"), ("directory", "user:"), ("directory", "1:"), ("key", "settings"),
    ]
    assert isinstance(key[0], DatabaseNode) and key[0].preferred
    assert isinstance(key[-1], KeyNode)
    # A table stands beside its folder, in the folder above it.
    assert [(node.kind, node.name) for node in table] == [
        ("database", f"db{DB}"), ("directory", "user:"), ("table", "users"),
    ]
    assert [node.id for node in folder][-1] == folder_id(DB, "user:1:")
    assert all(isinstance(node, DirectoryNode) for node in folder[1:])
    assert [node.kind for node in database] == ["database"]
    for missing in (key_id(DB, "user:gone"), table_id(DB, "user:"), folder_id(DB, "user"), "d999"):
        with pytest.raises(NodeNotFound):
            await subject.path_to(missing)
