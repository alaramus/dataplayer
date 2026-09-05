"""What a PostgreSQL relation says about itself, apart from its rows (D75).

Every relation described here belongs to the server rather than to this
project: `pg_class` and `pg_views` exist on every server the suite is pointed
at, and they have dozens of columns and indexes between them. A nearly empty
table in `public` would let each count below pass at zero, which is the way a
test proves nothing while staying green.
"""

import pytest

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import NodeNotFound
from app.adapters.summary import RelationContents
from tests.utils.database import working_postgres_options


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_describes_a_table_by_what_it_is_made_of() -> None:
    summary = await _adapter().node_summary("pg_catalog.pg_class")

    assert summary.name == "pg_class"
    assert summary.kind == "table"
    # The same pair the catalog offers this node, so the two cannot disagree
    # about what opening it would show.
    assert [item.kind for item in summary.representations] == ["table", "sql"]
    assert summary.size_bytes is not None and summary.size_bytes > 0

    contents = summary.contents
    assert isinstance(contents, RelationContents)
    assert contents.relation_kind == "table"
    assert contents.schema_name == "pg_catalog"
    assert contents.owner
    assert contents.persistence == "permanent"
    assert contents.columns > 10
    assert contents.indexes >= 1
    # Neither is a partition nor partitioned, and both stay absent rather than
    # being filled with a word meaning "no".
    assert contents.partitioned_by is None
    assert contents.partition_of is None


async def test_describes_a_view_as_a_view_with_nothing_measured() -> None:
    summary = await _adapter().node_summary("pg_catalog.pg_views")

    assert summary.kind == "view"
    contents = summary.contents
    assert isinstance(contents, RelationContents)
    assert contents.relation_kind == "view"
    assert contents.columns > 0
    assert contents.indexes == 0
    # A view holds no rows, so the server never analyses or vacuums it and has
    # no entry for it in the statistics at all. Absent, rather than a date
    # nobody measured.
    assert contents.analyzed_at is None
    assert contents.vacuumed_at is None


async def test_says_a_relation_is_gone_rather_than_failing() -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().node_summary("public.no_such_relation_here")


async def test_refuses_an_id_that_names_no_relation() -> None:
    """A schema is not marked summarizable, so nothing should ask — and an id
    that arrived anyway is refused as the wrong shape rather than looked for.
    """
    with pytest.raises(ValueError, match="not a relation"):
        await _adapter().node_summary("public")
