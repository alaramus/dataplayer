from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.references import (
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceValue,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def _customer(schema: str) -> None:
    """Two regions, and one customer pointing at exactly one of them."""
    await run(
        f"INSERT INTO {schema}.regions (id, code) "  # noqa: S608 -- schema is fixture-owned.
        "VALUES (7, 'north'), (8, 'south')"
    )
    await run(
        f"INSERT INTO {schema}.customers "  # noqa: S608 -- schema is fixture-owned.
        "(region_id, region_code, name) VALUES (7, 'north', 'Ada')"
    )


async def test_a_fetched_page_lists_the_whole_key_once(schema: str) -> None:
    """A composite key is one reference, not one link per column.

    The old application copied a constraint onto every column it touched,
    which turned this exact two-column key into two independent links.
    """
    result = await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.customers", limit=1)
    )

    assert [reference.name for reference in result.references] == [
        "customers_region_fkey"
    ]
    reference = result.references[0]
    assert reference.columns == ["region_id", "region_code"]
    assert reference.target_title == f"{schema}.regions"


async def test_a_relation_without_keys_lists_none(schema: str) -> None:
    result = await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.regions", limit=1)
    )

    assert result.references == []


async def test_following_a_composite_key_matches_every_column(schema: str) -> None:
    await _customer(schema)

    target = await _adapter().follow_reference(
        FollowReferenceRequest(
            node_id=f"{schema}.customers",
            reference="customers_region_fkey",
            values=[
                ReferenceValue(column="region_id", value="7"),
                ReferenceValue(column="region_code", value="north"),
            ],
        )
    )

    assert isinstance(target, ReferencedRows)
    assert target.node.id == f"{schema}.regions"
    assert target.node.name == "regions"
    assert target.node.kind == "table"
    assert target.filters == [
        ScalarFilter(column="id", op="eq", value="7"),
        ScalarFilter(column="code", op="eq", value="north"),
    ]


async def test_the_filters_the_source_built_read_the_referenced_row(
    schema: str,
) -> None:
    """The predicate is handed straight back to fetch, and it lands."""
    await _customer(schema)
    adapter = _adapter()
    target = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id=f"{schema}.customers",
            reference="customers_region_fkey",
            values=[
                ReferenceValue(column="region_id", value="7"),
                ReferenceValue(column="region_code", value="north"),
            ],
        )
    )
    assert isinstance(target, ReferencedRows)

    result = await adapter.fetch(
        FetchRequest(node_id=target.node.id, filters=target.filters, limit=10)
    )

    names = [column.name for column in result.columns]
    assert len(result.rows) == 1
    assert result.rows[0][names.index("id")] == "7"
    assert result.rows[0][names.index("code")] == "north"


async def test_a_key_with_a_missing_value_names_no_row(schema: str) -> None:
    """A null key is an answer about the data, not a failure of the request."""
    target = await _adapter().follow_reference(
        FollowReferenceRequest(
            node_id=f"{schema}.customers",
            reference="customers_region_fkey",
            values=[
                ReferenceValue(column="region_id", value="7"),
                ReferenceValue(column="region_code", value=None),
            ],
        )
    )

    assert isinstance(target, NoReferencedRows)
    assert "no value" in target.reason


async def test_a_target_this_source_cannot_look_up_says_so(schema: str) -> None:
    """A key over bytea has no equality in the closed filter vocabulary."""
    await run(f"CREATE TABLE {schema}.blobs (id bytea PRIMARY KEY)")
    await run(
        f"CREATE TABLE {schema}.blob_uses ("  # noqa: S608 -- schema is fixture-owned.
        f"blob_id bytea NOT NULL REFERENCES {schema}.blobs (id))"
    )

    result = await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.blob_uses", limit=1)
    )
    reference = result.references[0]
    target = await _adapter().follow_reference(
        FollowReferenceRequest(
            node_id=f"{schema}.blob_uses",
            reference=reference.name,
            values=[ReferenceValue(column="blob_id", value="0x00")],
        )
    )

    assert isinstance(target, NoReferencedRows)
    assert "bytea" in target.reason


async def test_a_renamed_target_is_followed_to_its_new_name(schema: str) -> None:
    """The constraint holds an oid, and everything here is read fresh."""
    await _customer(schema)
    await run(f"ALTER TABLE {schema}.regions RENAME TO areas")

    target = await _adapter().follow_reference(
        FollowReferenceRequest(
            node_id=f"{schema}.customers",
            reference="customers_region_fkey",
            values=[
                ReferenceValue(column="region_id", value="7"),
                ReferenceValue(column="region_code", value="north"),
            ],
        )
    )

    assert isinstance(target, ReferencedRows)
    assert target.node.id == f"{schema}.areas"
    assert target.node.name == "areas"


async def test_a_reference_the_relation_does_not_have_is_refused(
    schema: str,
) -> None:
    with pytest.raises(ValueError, match="no reference"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id=f"{schema}.customers",
                reference="customers_region_fkey_x",
                values=[ReferenceValue(column="region_id", value="7")],
            )
        )


async def test_values_that_are_not_the_key_are_refused(schema: str) -> None:
    """Half a composite key would silently widen the predicate."""
    with pytest.raises(ValueError, match="region_id, region_code"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id=f"{schema}.customers",
                reference="customers_region_fkey",
                values=[ReferenceValue(column="region_id", value="7")],
            )
        )


async def test_a_column_that_is_not_in_the_key_is_refused(schema: str) -> None:
    """The caller cannot choose which column the predicate stands on."""
    with pytest.raises(ValueError, match="region_id, region_code"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id=f"{schema}.customers",
                reference="customers_region_fkey",
                values=[
                    ReferenceValue(column="region_id", value="7"),
                    ReferenceValue(column="name", value="Ada"),
                ],
            )
        )


async def test_a_relation_that_is_gone_has_no_reference_to_follow(
    schema: str,
) -> None:
    with pytest.raises(ValueError, match="no reference"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id=f"{schema}.no_such_table",
                reference="whatever",
                values=[ReferenceValue(column="id", value="1")],
            )
        )


async def test_a_key_dropped_since_the_page_was_read_is_refused(
    schema: str,
) -> None:
    """The reference is checked against the source, not against the request.

    A tab open on a page read minutes ago still offers the arrow. Dropping the
    constraint underneath it must refuse by name rather than build a predicate
    from a key that no longer exists.
    """
    await _customer(schema)
    adapter = _adapter()
    request = FollowReferenceRequest(
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[
            ReferenceValue(column="region_id", value="7"),
            ReferenceValue(column="region_code", value="north"),
        ],
    )
    assert isinstance(await adapter.follow_reference(request), ReferencedRows)

    await run(
        f"ALTER TABLE {schema}.customers DROP CONSTRAINT customers_region_fkey"
    )
    with pytest.raises(ValueError, match="no reference"):
        await adapter.follow_reference(request)


async def test_a_node_that_is_not_a_relation_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a relation"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id="public",
                reference="whatever",
                values=[ReferenceValue(column="id", value="1")],
            )
        )


async def test_injection_through_a_reference_name_never_reaches_sql(
    schema: str,
) -> None:
    """The name is compared against what the source says, never composed in."""
    with pytest.raises(ValueError, match="no reference"):
        await _adapter().follow_reference(
            FollowReferenceRequest(
                node_id=f"{schema}.customers",
                reference="customers_region_fkey'; DROP TABLE regions; --",
                values=[ReferenceValue(column="region_id", value="7")],
            )
        )

    assert await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.regions", limit=1)
    )

