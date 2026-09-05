from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.adapters.dataset import ParquetDataset
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.file.fetch import FileFetch
from app.adapters.file.parquet import MAX_COLUMNS, NotParquet
from app.adapters.file.relation import FileRelations
from app.adapters.file.session import FileSession

ROWS = 250
# Small enough that a page of a hundred rows begins inside the second group.
ROW_GROUP = 100


def _cities() -> pa.Table:
    return pa.table(
        {
            "id": pa.array(range(1, ROWS + 1), type=pa.int64()),
            "city": pa.array([f"city-{index}" for index in range(1, ROWS + 1)]),
            "population": pa.array(
                [index * 1000.5 for index in range(1, ROWS + 1)], type=pa.float64()
            ),
            "capital": pa.array([index % 7 == 0 for index in range(1, ROWS + 1)]),
            "seen": pa.array([datetime(2026, 8, 31, 12, 0, tzinfo=UTC)] * ROWS),
            "tags": pa.array(
                [["north"] if index % 2 else ["south", "coast"] for index in range(1, ROWS + 1)],
                type=pa.list_(pa.string()),
            ),
            "blob": pa.array([b"\x01\x02"] * ROWS, type=pa.binary()),
        }
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    pq.write_table(_cities(), tmp_path / "cities.parquet", row_group_size=ROW_GROUP)
    pq.write_table(_cities().slice(0, 0), tmp_path / "empty.parquet")
    (tmp_path / "not-really.parquet").write_bytes(b"this is not a footer")
    return tmp_path


@pytest.fixture
def fetch(root: Path) -> FileFetch:
    return FileFetch(FileSession(root))


@pytest.fixture
def relations(root: Path) -> FileRelations:
    return FileRelations(FileSession(root))


async def test_columns_keep_the_types_the_file_declares(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.parquet", limit=1))

    categories = {column.name: column.type.category for column in result.columns}
    assert categories == {
        "id": "number",
        "city": "string",
        "population": "number",
        "capital": "boolean",
        "seen": "datetime",
        "tags": "json",
        "blob": "binary",
    }
    assert next(c for c in result.columns if c.name == "id").type.sql == "int64"


async def test_values_cross_the_boundary_as_canonical_text(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.parquet", limit=1))

    assert result.rows[0] == [
        "1",
        "city-1",
        "1000.5",
        "false",
        "2026-08-31T12:00:00+00:00",
        '["north"]',
        "0x0102",
    ]


async def test_a_page_may_begin_inside_a_later_row_group(fetch: FileFetch) -> None:
    """The offset falls in the second group; the first is never read."""
    result = await fetch.fetch(
        FetchRequest(node_id="cities.parquet", limit=3, offset=ROW_GROUP + 5)
    )

    assert [row[0] for row in result.rows] == ["106", "107", "108"]
    assert result.has_more is True


async def test_the_last_page_knows_it_is_the_last(fetch: FileFetch) -> None:
    result = await fetch.fetch(
        FetchRequest(node_id="cities.parquet", limit=5, offset=ROWS - 2)
    )

    assert [row[0] for row in result.rows] == ["249", "250"]
    assert result.has_more is False


async def test_a_value_is_looked_up_across_every_row_group(
    fetch: FileFetch,
) -> None:
    """A filter gives up the row-group arithmetic and reads the file (D109)."""
    result = await fetch.fetch(
        FetchRequest(
            node_id="cities.parquet",
            filters=[ScalarFilter(column="city", op="eq", value="city-200")],
        )
    )

    assert [row[0] for row in result.rows] == ["200"]
    assert result.has_more is False


async def test_a_filter_over_a_column_a_parquet_file_has_not_got_is_refused(
    fetch: FileFetch,
) -> None:
    request = FetchRequest(
        node_id="cities.parquet",
        filters=[ScalarFilter(column="invented", op="eq", value="1")],
    )

    with pytest.raises(ValueError, match="invented"):
        await fetch.fetch(request)


async def test_a_page_past_the_end_is_empty(fetch: FileFetch) -> None:
    result = await fetch.fetch(
        FetchRequest(node_id="cities.parquet", limit=5, offset=ROWS + 100)
    )

    assert result.rows == []
    assert result.has_more is False


async def test_a_file_without_rows_still_states_its_columns(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="empty.parquet", limit=10))

    assert [column.name for column in result.columns][:2] == ["id", "city"]
    assert result.rows == []
    assert result.has_more is False


async def test_a_parquet_file_is_read_only(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.parquet", limit=1))

    assert result.update_supported is False
    assert result.insert_supported is False
    assert result.delete_supported is False


async def test_bytes_that_are_not_parquet_are_refused_without_driver_text(
    fetch: FileFetch,
) -> None:
    with pytest.raises(NotParquet) as raised:
        await fetch.fetch(FetchRequest(node_id="not-really.parquet", limit=1))

    assert str(raised.value) == "This file is not a Parquet file"


async def test_a_refused_file_is_closed_again(root: Path, fetch: FileFetch) -> None:
    """A reader that leaks a descriptor per malformed file is a slow failure.

    On Windows an open handle also blocks the delete, which is what this
    asserts: the file can be removed straight after the refusal.
    """
    with pytest.raises(NotParquet):
        await fetch.fetch(FetchRequest(node_id="not-really.parquet", limit=1))

    (root / "not-really.parquet").unlink()


async def test_a_file_wider_than_a_page_may_carry_is_refused(
    tmp_path: Path,
) -> None:
    width = MAX_COLUMNS + 1
    table = pa.table({f"c{index}": pa.array([index]) for index in range(width)})
    pq.write_table(table, tmp_path / "wide.parquet")
    fetch = FileFetch(FileSession(tmp_path))

    with pytest.raises(ValueError, match=f"more than {MAX_COLUMNS} columns"):
        await fetch.fetch(FetchRequest(node_id="wide.parquet", limit=1))


async def test_the_relation_model_states_what_the_footer_knows(
    relations: FileRelations,
) -> None:
    model = await relations.relation_model("cities.parquet")

    assert model.kind == "dataset"
    assert model.row_estimate == ROWS
    assert [column.name for column in model.columns][:2] == ["id", "city"]
    dataset = model.dataset
    assert isinstance(dataset, ParquetDataset)
    assert dataset.rows == ROWS
    assert dataset.row_groups == 3
    assert dataset.columns == 7
    assert dataset.compression == ["SNAPPY"]
    assert dataset.created_by is not None
    assert dataset.format_version


async def test_a_described_file_has_no_relational_vocabulary_it_lacks(
    relations: FileRelations,
) -> None:
    model = await relations.relation_model("cities.parquet")

    assert model.schema_name is None
    assert model.owner is None
    assert model.persistence is None
    assert all(column.storage is None for column in model.columns)


async def test_nothing_about_a_file_dataset_may_be_changed(
    relations: FileRelations,
) -> None:
    model = await relations.relation_model("cities.parquet")

    assert model.column_changes_supported is False
    assert model.index_changes_supported is False
    assert model.constraint_changes_supported is False
    assert model.column_changes_reason is not None
