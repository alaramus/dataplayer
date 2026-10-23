"""MySQL and MariaDB found by name, and their relations by their columns (D202, D237).

Against the server's own catalog, which holds hundreds of relations, and a
database of a view per name in the shared word table, so this query is held
to the same rule as every other implementation.
"""

import time
import uuid
from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode, SchemaNode, TableNode
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.reports import SECTION_ID
from app.adapters.protocol import NodeNotFound
from app.adapters.search import (
    MatchClass,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    class_of_name,
    class_rank,
    words_of,
)
from tests.adapters.mysql_fixture import TARGETS, Target, run
from tests.utils.word_cases import CASES

WORDS = f"dp_words_{uuid.uuid4().hex[:8]}"
DESCRIBED = f"dp_described_{uuid.uuid4().hex[:8]}"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    """Both databases on one server: a view per name of the word table, and
    relations known by their columns and comments.

    And two more views for `orders`: a word of one name and only a part of
    another, the part first in the alphabet.
    """
    chosen: Target = request.param
    chosen.server.require()
    names = sorted({name for _, name, _ in CASES} | {"aaa_xorders", "zzz_orders"})
    await run(
        chosen,
        f"DROP DATABASE IF EXISTS `{WORDS}`",
        f"DROP DATABASE IF EXISTS `{DESCRIBED}`",
        f"CREATE DATABASE `{WORDS}`",
        *(f"CREATE VIEW `{WORDS}`.`{name}` AS SELECT 1 AS one" for name in names),
        f"CREATE DATABASE `{DESCRIBED}`",
        f"CREATE TABLE `{DESCRIBED}`.buyers (id INT, customer_email VARCHAR(80))",
        f"CREATE TABLE `{DESCRIBED}`.ledger (id INT) COMMENT 'Every invoice the warehouse settled'",
        f"CREATE TABLE `{DESCRIBED}`.parcels (id INT, sent_to TEXT "
        "COMMENT 'Where the courier delivers')",
        f"CREATE TABLE `{DESCRIBED}`.quiet (id INT)",
    )
    yield chosen
    await run(chosen, f"DROP DATABASE IF EXISTS `{WORDS}`", f"DROP DATABASE IF EXISTS `{DESCRIBED}`")


async def _find(
    target: Target, query: str, *, node_id: str | None = None, limit: int = 100
) -> NodeSearchResult:
    return await target.adapter().search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit), SearchBounds.within(10)
    )


def _names(found: NodeSearchResult) -> list[str]:
    return [match.node.name for match in found.matches]


async def test_priv_finds_the_server_s_own_table_among_hundreds(target: Target) -> None:
    found = await _find(target, "priv")

    [table] = [
        match for match in found.matches if match.node.id == ids.relation_id("mysql", "columns_priv")
    ]
    assert (table.parent_id, table.location) == ("mysql", "mysql")
    assert isinstance(table.node, TableNode)
    assert table.node.is_system


async def test_a_database_is_found_by_its_name(target: Target) -> None:
    found = await _find(target, WORDS)

    [database] = [match for match in found.matches if isinstance(match.node, SchemaNode)]
    assert database.node.id == ids.database_id(WORDS)
    assert (database.parent_id, database.location) == (None, "")


async def test_a_found_relation_is_the_node_its_listing_gives(target: Target) -> None:
    """One builder for the listing, the walk back up and the search (D76)."""
    adapter = target.adapter()

    found = await adapter.search_nodes(
        NodeSearchRequest(query="buyers", node_id=ids.database_id(DESCRIBED)),
        SearchBounds.within(10),
    )
    walked = await adapter.path_to(ids.relation_id(DESCRIBED, "buyers"))

    # A new table's estimates are InnoDB's to refresh between two reads.
    estimates = {"row_count_estimate", "size_bytes"}
    assert found.matches[0].node.model_dump(exclude=estimates) == walked[-1].model_dump(
        exclude=estimates
    )


async def test_a_search_in_a_database_stays_in_it(target: Target) -> None:
    found = await _find(target, "orders", node_id=ids.database_id(WORDS))

    assert found.matches
    assert {match.location for match in found.matches} == {WORDS}


@pytest.mark.parametrize("typed", ["%", "_%_", "_"])
async def test_wildcards_of_like_match_only_themselves(target: Target, typed: str) -> None:
    found = await _find(target, typed, node_id=ids.database_id(DESCRIBED))

    assert found.matches == []


@pytest.mark.parametrize(("typed", "name", "expected"), CASES)
async def test_the_query_agrees_with_the_word_table(
    target: Target, typed: str, name: str, expected: MatchClass | None
) -> None:
    found = await _find(target, typed, node_id=ids.database_id(WORDS))

    assert (name in _names(found)) is (expected is not None)


@pytest.mark.parametrize("typed", sorted({typed for typed, _, _ in CASES}))
async def test_the_query_orders_by_the_classes_of_the_word_table(
    target: Target, typed: str
) -> None:
    found = await _find(target, typed, node_id=ids.database_id(WORDS))

    classes = [class_of_name(words_of(typed), name) for name in _names(found)]
    assert None not in classes
    ranks = [class_rank(one) for one in classes if one is not None]
    assert ranks == sorted(ranks)


async def test_a_word_survives_the_limit_ahead_of_names_that_merely_hold_it(
    target: Target,
) -> None:
    """Ordered by class before the LIMIT, not by the alphabet (D202)."""
    found = await _find(target, "orders", node_id=ids.database_id(WORDS), limit=5)

    assert _names(found)[-1] == "zzz_orders"
    assert "aaa_xorders" not in _names(found)
    assert found.complete is False
    assert found.notice is not None


async def test_a_database_that_is_gone_is_not_found(target: Target) -> None:
    with pytest.raises(NodeNotFound):
        await _find(target, "orders", node_id=ids.database_id(f"gone_{uuid.uuid4().hex[:8]}"))


async def test_a_relation_is_not_a_level_to_search_from(target: Target) -> None:
    with pytest.raises(ValueError):
        await _find(target, "orders", node_id=ids.relation_id(DESCRIBED, "buyers"))


async def test_the_reports_are_found_by_their_titles(target: Target) -> None:
    found = await _find(target, "proc", node_id=SECTION_ID)

    assert _names(found) == ["Processes"]
    assert isinstance(found.matches[0].node, ReportNode)
    assert found.matches[0].parent_id == SECTION_ID


async def test_a_search_out_of_time_says_so_without_asking(target: Target) -> None:
    found = await target.adapter().search_nodes(
        NodeSearchRequest(query="user"), SearchBounds(deadline=time.monotonic() - 1)
    )

    assert found.complete is False
    assert found.notice is not None


async def _by_columns(target: Target, query: str) -> NodeSearchResult:
    return await target.adapter().search_columns(
        NodeSearchRequest(query=query, node_id=ids.database_id(DESCRIBED)),
        SearchBounds.within(10),
    )


async def test_a_relation_is_found_by_a_column_and_says_which(target: Target) -> None:
    found = await _by_columns(target, "email")

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("buyers", "customer_email")
    ]
    assert found.matches[0].node.id == ids.relation_id(DESCRIBED, "buyers")


async def test_a_table_comment_is_found_by_a_word_in_it(target: Target) -> None:
    found = await _by_columns(target, "invoice warehouse")

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("ledger", "Every invoice the warehouse settled")
    ]


async def test_a_column_comment_names_its_column(target: Target) -> None:
    found = await _by_columns(target, "courier")

    assert [(match.node.name, match.excerpt) for match in found.matches] == [
        ("parcels", "sent_to: Where the courier delivers")
    ]


async def test_a_name_search_does_not_look_at_columns(target: Target) -> None:
    found = await _find(target, "email", node_id=ids.database_id(DESCRIBED))

    assert found.matches == []


async def test_every_name_is_kept_once_with_its_place(target: Target) -> None:
    names = [
        name
        async for batch in target.adapter().enumerate_names(100_000, SearchBounds.within(10))
        for name in batch.names
    ]

    ids_kept = [name.node.id for name in names]
    assert len(ids_kept) == len(set(ids_kept))
    [buyers] = [name for name in names if name.node.id == ids.relation_id(DESCRIBED, "buyers")]
    assert (buyers.parent_id, buyers.location) == (ids.database_id(DESCRIBED), DESCRIBED)
    assert ids.database_id(WORDS) in ids_kept


async def test_a_kept_list_past_its_ceiling_says_so(target: Target) -> None:
    batches = [
        batch async for batch in target.adapter().enumerate_names(3, SearchBounds.within(10))
    ]

    assert sum(len(batch.names) for batch in batches) == 3
    assert batches[-1].notice is not None


def test_the_cost_of_names_and_of_columns() -> None:
    assert MysqlAdapter.search_cost("names", None) == "cheap"
    assert MysqlAdapter.search_cost("columns", None) == "costly"
