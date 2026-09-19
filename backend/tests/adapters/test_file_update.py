from pathlib import Path

import pytest

from app.adapters.column_changes import (
    AddColumnRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.explorer.fetch import ExplorerFetch
from app.adapters.explorer.relation import ExplorerRelations
from app.adapters.explorer.update import ExplorerTableChanges
from app.adapters.fetch import FetchRequest
from app.adapters.file.storage import LocalStorage
from app.adapters.update import (
    CellEdit,
    DeleteRowsRequest,
    InsertRowRequest,
    InsertRowsRequest,
    InsertValue,
    RowConflict,
    RowEdit,
    UpdateCellRequest,
    UpdateCellsRequest,
)


@pytest.fixture
def source(tmp_path: Path) -> tuple[ExplorerFetch, ExplorerTableChanges, Path]:
    path = tmp_path / "people.csv"
    path.write_text("id,name\n1,Ada\n2,Grace\n3,Linus\n", encoding="utf-8")
    session = LocalStorage(tmp_path)
    return ExplorerFetch(session), ExplorerTableChanges(session), path


async def test_updates_one_cell_and_issues_fresh_handles(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    fetch, changes, path = source
    before = await fetch.fetch(FetchRequest(node_id="people.csv"))

    result = await changes.update_cell(
        UpdateCellRequest(
            node_id="people.csv",
            row_handle=before.row_handles[1] or "",
            column="name",
            value="Hopper",
        )
    )

    assert result.values == ["2", "Hopper"]
    assert result.row_handle != before.row_handles[1]
    assert "2,Hopper" in path.read_text(encoding="utf-8")


async def test_pastes_a_block_atomically(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    fetch, changes, path = source
    before = await fetch.fetch(FetchRequest(node_id="people.csv"))

    await changes.update_cells(
        UpdateCellsRequest(
            node_id="people.csv",
            rows=[
                RowEdit(
                    row_handle=before.row_handles[0] or "",
                    cells=[CellEdit(column="name", value="Augusta")],
                ),
                RowEdit(
                    row_handle=before.row_handles[1] or "",
                    cells=[CellEdit(column="name", value="Rear Admiral Hopper")],
                ),
            ],
        )
    )

    text = path.read_text(encoding="utf-8")
    assert "1,Augusta" in text
    assert "2,Rear Admiral Hopper" in text


async def test_inserts_one_row_and_a_mapped_block(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    _, changes, path = source
    await changes.insert_row(
        InsertRowRequest(
            node_id="people.csv",
            values=[InsertValue(column="name", value="Margaret")],
        )
    )
    result = await changes.insert_rows(
        InsertRowsRequest(
            node_id="people.csv", columns=["id", "name"], rows=[["5", "Edsger"]]
        )
    )

    assert result.inserted == 1
    assert ",Margaret" in path.read_text(encoding="utf-8")
    assert "5,Edsger" in path.read_text(encoding="utf-8")


async def test_deletes_selected_rows(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    fetch, changes, path = source
    before = await fetch.fetch(FetchRequest(node_id="people.csv"))

    result = await changes.delete_rows(
        DeleteRowsRequest(
            node_id="people.csv",
            row_handles=[before.row_handles[0] or "", before.row_handles[2] or ""],
        )
    )

    assert result.deleted == 2
    assert path.read_text(encoding="utf-8") == "id,name\n2,Grace\n"


async def test_adds_renames_and_drops_csv_columns(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    _, changes, path = source

    await changes.add_column(
        AddColumnRequest(node_id="people.csv", name="note", type_code="text")
    )
    await changes.rename_column(
        RenameColumnRequest(
            node_id="people.csv", name="note", new_name="comment"
        )
    )
    await changes.drop_column(
        DropColumnRequest(node_id="people.csv", name="id")
    )

    assert path.read_text(encoding="utf-8") == (
        "name,comment\nAda,\nGrace,\nLinus,\n"
    )


async def test_a_csv_relation_model_offers_only_header_operations(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    _, _, path = source
    model = await ExplorerRelations(LocalStorage(path.parent)).relation_model("people.csv")

    assert [column.name for column in model.columns] == ["id", "name"]
    assert model.column_operations == ["add", "drop", "rename"]
    assert [option.code for option in model.column_type_options] == ["text"]


async def test_a_stale_file_handle_cannot_overwrite_a_newer_file(
    source: tuple[ExplorerFetch, ExplorerTableChanges, Path]
) -> None:
    fetch, changes, path = source
    before = await fetch.fetch(FetchRequest(node_id="people.csv"))
    path.write_text("id,name\n9,New\n", encoding="utf-8")

    with pytest.raises(RowConflict):
        await changes.update_cell(
            UpdateCellRequest(
                node_id="people.csv",
                row_handle=before.row_handles[0] or "",
                column="name",
                value="Old",
            )
        )

    assert path.read_text(encoding="utf-8") == "id,name\n9,New\n"


async def test_non_delimited_files_are_not_changed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "people.json"
    path.write_text('[["Ada"]]', encoding="utf-8")
    changes = ExplorerTableChanges(LocalStorage(tmp_path))

    with pytest.raises(ValueError, match="CSV or TSV"):
        await changes.insert_row(InsertRowRequest(node_id="people.json"))

    assert path.read_text(encoding="utf-8") == '[["Ada"]]'
