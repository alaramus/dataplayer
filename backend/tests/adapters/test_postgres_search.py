"""PostgreSQL found by name, and its relations by their columns (D202, S4, S8).

Against the system catalog, which always holds hundreds of relations: a search
that passed on a nearly empty schema would prove nothing about its bounds or
its order.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator

import psycopg
import pytest
from psycopg import sql

from app.adapters.catalog import ReportNode, SchemaNode, TableNode
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import SECTION_ID
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.search import (
    MatchClass,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    class_of_name,
    class_rank,
    words_of,
)
from tests.utils.database import working_postgres_options
from tests.utils.word_cases import CASES


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _conninfo() -> str:
    options = working_postgres_options()
    return psycopg.conninfo.make_conninfo(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )


async def _find(
    query: str, *, node_id: str | None = None, limit: int = 100
) -> NodeSearchResult:
    return await _adapter().search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit),
        SearchBounds.within(10),
    )


def _names(found: NodeSearchResult) -> list[str]:
    return [match.node.name for match in found.matches]


async def test_class_finds_pg_class_among_hundreds() -> None:
    found = await _find("class")

    [pg_class] = [match for match in found.matches if match.node.id == "pg_catalog.pg_class"]
    assert pg_class.parent_id == "pg_catalog"
    assert pg_class.location == "pg_catalog"
    assert class_of_name(words_of("class"), pg_class.node.name) == "word"


async def test_exact_and_prefix_names_come_first_and_survive_the_limit() -> None:
    """Ordered inside the query, before its LIMIT, so the best is never cut."""
    # `tables` is a view of information_schema, and a word of a dozen more.
    found = await _find("tables", limit=2)

    assert _names(found)[0] == "tables"
    assert found.complete is False
    assert found.notice is not None


async def test_a_percent_sign_is_a_character_and_finds_nothing() -> None:
    """`strpos` on a bound value: `100%` is not a pattern for everything.

    Only a name that holds the characters themselves is found — the word
    table's schema has one while it exists — and the catalog has none.
    """
    found = await _find("100%")

    assert all("100%" in name for name in _names(found))
    assert found.complete is True
    assert await _find("100%", node_id="pg_catalog") == NodeSearchResult()


@pytest.mark.parametrize("typed", ["%", "_%_"])
async def test_wildcards_of_like_match_only_themselves(typed: str) -> None:
    found = await _find(typed, node_id="pg_catalog")

    assert found.matches == []


async def test_a_schema_is_found_by_its_name() -> None:
    found = await _find("catalog")

    schemas = [match for match in found.matches if isinstance(match.node, SchemaNode)]
    assert [match.node.name for match in schemas] == ["pg_catalog"]
    assert (schemas[0].parent_id, schemas[0].location) == (None, "")


async def test_a_found_relation_is_the_node_its_listing_gives() -> None:
    """One builder for the listing, the walk back up and the search (D76)."""
    adapter = _adapter()

    found = await adapter.search_nodes(
        NodeSearchRequest(query="pg_class", node_id="pg_catalog"), SearchBounds.within(10)
    )
    walked = await adapter.path_to("pg_catalog.pg_class")

    assert found.matches[0].node == walked[-1]
    assert isinstance(found.matches[0].node, TableNode)


async def test_a_search_in_a_schema_stays_in_it() -> None:
    found = await _find("pg", node_id="information_schema")

    assert found.matches
    assert {match.parent_id for match in found.matches} == {"information_schema"}


async def test_a_schema_that_is_gone_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await _find("orders", node_id=f"gone_{uuid.uuid4().hex[:8]}")


async def test_a_relation_is_not_a_level_to_search_from() -> None:
    with pytest.raises(ValueError):
        await _find("orders", node_id="pg_catalog.pg_class")


async def test_the_reports_are_found_by_their_titles() -> None:
    found = await _find("settings", node_id=SECTION_ID)

    assert _names(found) == ["Settings"]
    assert isinstance(found.matches[0].node, ReportNode)
    assert found.matches[0].parent_id == SECTION_ID


async def test_a_search_out_of_time_says_so_without_asking() -> None:
    found = await _adapter().search_nodes(
        NodeSearchRequest(query="class"), SearchBounds(deadline=time.monotonic() - 1)
    )

    assert found.complete is False
    assert found.notice is not None


# --- the one table of words ---------------------------------------------------


@pytest.fixture(scope="module")
async def named_schema() -> AsyncGenerator[str]:
    """A schema holding a view named after every name in the word table.

    And two more for `orders`: a word of one name and only a part of another,
    the part first in the alphabet.
    """
    schema = f"search_words_{uuid.uuid4().hex[:8]}"
    names = sorted({name for _, name, _ in CASES} | {"aaa_xorders", "zzz_orders"})
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        for name in names:
            await conn.execute(
                sql.SQL("CREATE VIEW {}.{} AS SELECT 1 AS one").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            )
    try:
        yield schema
    finally:
        async with await psycopg.AsyncConnection.connect(
            _conninfo(), autocommit=True
        ) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.parametrize(("typed", "name", "expected"), CASES)
async def test_the_query_agrees_with_the_word_table(
    named_schema: str, typed: str, name: str, expected: MatchClass | None
) -> None:
    found = await _find(typed, node_id=named_schema)

    assert (name in _names(found)) is (expected is not None)


@pytest.mark.parametrize("typed", sorted({typed for typed, _, _ in CASES}))
async def test_the_query_orders_by_the_classes_of_the_word_table(
    named_schema: str, typed: str
) -> None:
    found = await _find(typed, node_id=named_schema)

    classes = [class_of_name(words_of(typed), name) for name in _names(found)]
    assert None not in classes
    ranks = [class_rank(one) for one in classes if one is not None]
    assert ranks == sorted(ranks)


async def test_a_word_survives_the_limit_ahead_of_names_that_merely_hold_it(
    named_schema: str,
) -> None:
    """Ordered by class before the LIMIT, not by the alphabet (D202)."""
    found = await _find("orders", node_id=named_schema, limit=5)

    assert _names(found)[-1] == "zzz_orders"
    assert "aaa_xorders" not in _names(found)
    assert found.complete is False


async def test_a_table_somebody_holds_is_found_at_once_without_its_size() -> None:
    """Reading a size waits behind an ALTER TABLE or a VACUUM FULL; a search
    does not wait for a migration to say where a table is."""
    marker = uuid.uuid4().hex[:8]
    schema, table = f"search_held_{marker}", f"held_{marker}"
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        await conn.execute(
            sql.SQL("CREATE TABLE {}.{} (id int)").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
    holder = await psycopg.AsyncConnection.connect(_conninfo())
    try:
        await holder.execute(
            sql.SQL("LOCK TABLE {}.{} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )
        started = time.monotonic()
        held = await _find(table, node_id=schema)
        took = time.monotonic() - started
        await holder.rollback()
        free = await _find(table, node_id=schema)
    finally:
        await holder.close()
        async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )

    assert took < 2
    [found] = held.matches
    assert isinstance(found.node, TableNode)
    assert found.node.size_bytes is None
    [unheld] = free.matches
    assert isinstance(unheld.node, TableNode)
    assert unheld.node.size_bytes is not None


async def test_the_tables_of_a_found_schema_are_the_listing_s() -> None:
    """Read after the limit, for the schemas kept, and the same as listed."""
    adapter = _adapter()

    found = await _find("public")
    [listed] = [node for node in await adapter.list_children(None) if node.id == "public"]

    [public] = [match.node for match in found.matches if match.node.id == "public"]
    assert public == listed


# --- the server stops what nobody waits for ----------------------------------


async def test_the_statement_timeout_is_the_time_left() -> None:
    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    started = time.monotonic()

    with pytest.raises(AdapterError) as caught:
        await session.bounded_query(sql.SQL("SELECT pg_sleep(5)"), (), seconds=0.2)

    assert caught.value.error_kind == "timeout"
    assert time.monotonic() - started < 3


async def test_a_cancelled_search_is_cancelled_on_the_server() -> None:
    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    marker = f"search_cancel_{uuid.uuid4().hex[:8]}"
    statement = sql.SQL("SELECT pg_sleep(30), {}").format(sql.Literal(marker))
    running = asyncio.create_task(session.bounded_query(statement, (), seconds=30))

    async def holding() -> int:
        async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
            cursor = await conn.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'active' AND strpos(query, %s) > 0 AND pid <> pg_backend_pid()",
                (marker,),
            )
            row = await cursor.fetchone()
            assert row is not None
            return int(row[0])

    for _ in range(50):
        if await holding():
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("The query never started")
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    for _ in range(30):
        if not await holding():
            return
        await asyncio.sleep(0.1)
    pytest.fail("The server is still running a query nobody waits for")


# --- columns and comments (S8) -------------------------------------------------


@pytest.fixture(scope="module")
async def described_schema() -> AsyncGenerator[str]:
    schema = f"search_columns_{uuid.uuid4().hex[:8]}"
    statements = [
        "CREATE SCHEMA {schema}",
        "CREATE TABLE {schema}.buyers (id int, customer_email text, city text)",
        "CREATE TABLE {schema}.ledger (id int, amount numeric)",
        "COMMENT ON TABLE {schema}.ledger IS 'Every invoice the warehouse settled'",
        "CREATE TABLE {schema}.parcels (id int, sent_to text)",
        "COMMENT ON COLUMN {schema}.parcels.sent_to IS 'Where the courier delivers'",
        "CREATE TABLE {schema}.quiet (id int)",
    ]
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
        for statement in statements:
            await conn.execute(sql.SQL(statement).format(schema=sql.Identifier(schema)))
    try:
        yield schema
    finally:
        async with await psycopg.AsyncConnection.connect(
            _conninfo(), autocommit=True
        ) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


async def _by_columns(query: str, schema: str) -> NodeSearchResult:
    return await _adapter().search_columns(
        NodeSearchRequest(query=query, node_id=schema), SearchBounds.within(10)
    )


async def test_a_relation_is_found_by_a_column_and_says_which(described_schema: str) -> None:
    found = await _by_columns("email", described_schema)

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("buyers", "customer_email")
    ]
    assert found.matches[0].node.id == f"{described_schema}.buyers"


async def test_a_table_comment_is_found_by_a_word_in_it(described_schema: str) -> None:
    found = await _by_columns("invoice warehouse", described_schema)

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("ledger", "Every invoice the warehouse settled")
    ]


async def test_a_column_comment_names_its_column(described_schema: str) -> None:
    found = await _by_columns("courier", described_schema)

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("parcels", "sent_to: Where the courier delivers")
    ]


async def test_a_name_search_does_not_look_at_columns(described_schema: str) -> None:
    found = await _find("email", node_id=described_schema)

    assert found.matches == []


async def test_the_cost_of_names_and_of_columns() -> None:
    assert PostgresAdapter.search_cost("names", None) == "cheap"
    assert PostgresAdapter.search_cost("columns", None) == "costly"
