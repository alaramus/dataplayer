import zipfile
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.catalog import DatasetNode
from app.adapters.content import ContentRequest, EditorContentRequest
from app.adapters.dataset import WorksheetDataset
from app.adapters.fetch import FetchRequest
from app.adapters.file.actions import FileActions
from app.adapters.file.catalog import FileCatalog
from app.adapters.file.content import FileContent
from app.adapters.file.fetch import FileFetch
from app.adapters.file.relation import FileRelations
from app.adapters.file.session import FileSession
from app.adapters.file.workbook import MAX_UNPACKED_BYTES, NotAWorkbook
from app.adapters.protocol import NodeNotFound

SHEET_ROWS = 120


def _write_workbook(path: Path) -> None:
    book = Workbook()
    revenue = book.active
    assert revenue is not None
    revenue.title = "Revenue"
    revenue.append(["quarter", "amount", "closed"])
    for index in range(1, SHEET_ROWS + 1):
        revenue.append([f"Q{index}", index * 100, index % 2 == 0])
    people = book.create_sheet("People")
    people.append(["name", "started", ""])
    people.append(["Ann", date(2026, 1, 14), None])
    people.append(["Bo", None, "note"])
    notes = book.create_sheet("Working notes")
    notes.append(["note"])
    notes.sheet_state = "hidden"
    book.save(path)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _write_workbook(tmp_path / "budget.xlsx")
    (tmp_path / "not-really.xlsx").write_bytes(b"not a zip at all")
    # A directory whose name looks like a workbook, holding a file called "1":
    # the same id shape a sheet has, and it must keep its ordinary meaning.
    (tmp_path / "trap.xlsx").mkdir()
    (tmp_path / "trap.xlsx" / "1").write_text("id,name\n7,seven\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def catalog(root: Path) -> FileCatalog:
    return FileCatalog(FileSession(root))


@pytest.fixture
def fetch(root: Path) -> FileFetch:
    return FileFetch(FileSession(root))


@pytest.fixture
def relations(root: Path) -> FileRelations:
    return FileRelations(FileSession(root))


async def test_a_workbook_is_a_file_that_opens_and_also_holds_nodes(
    catalog: FileCatalog,
) -> None:
    """Both, which is what a spreadsheet is: several tables in one file. It
    opens as the first of them rather than making somebody walk into a folder
    before they can see a figure."""
    nodes = {node.name: node for node in await catalog.list_children(None)}

    workbook = nodes["budget.xlsx"]
    assert workbook.kind == "file"
    assert workbook.has_children is True
    assert [one.kind for one in workbook.representations] == ["table"]
    assert workbook.describable is False


async def test_the_sheets_are_the_children_in_workbook_order(
    catalog: FileCatalog,
) -> None:
    nodes = await catalog.list_children("budget.xlsx")

    assert [node.name for node in nodes] == ["Revenue", "People", "Working notes"]
    assert [node.id for node in nodes] == [
        "budget.xlsx/1",
        "budget.xlsx/2",
        "budget.xlsx/3",
    ]
    assert all(node.kind == "dataset" for node in nodes)
    assert all(
        [item.kind for item in node.representations] == ["table"] for node in nodes
    )


async def test_a_sheet_states_what_the_workbook_declared_about_it(
    catalog: FileCatalog,
) -> None:
    nodes = await catalog.list_children("budget.xlsx")

    revenue = nodes[0]
    assert isinstance(revenue, DatasetNode)
    assert revenue.row_count == SHEET_ROWS
    assert revenue.column_count == 3
    assert revenue.hidden is False
    hidden = nodes[2]
    assert isinstance(hidden, DatasetNode)
    assert hidden.hidden is True


async def test_a_hidden_sheet_is_listed_rather_than_left_out(
    catalog: FileCatalog,
) -> None:
    """Hiding a sheet is a spreadsheet's own presentation, not a permission."""
    nodes = await catalog.list_children("budget.xlsx")

    assert "Working notes" in [node.name for node in nodes]


async def test_the_path_to_a_sheet_walks_through_its_workbook(
    catalog: FileCatalog,
) -> None:
    path = await catalog.path_to("budget.xlsx/2")

    assert [(node.kind, node.name) for node in path] == [
        ("file", "budget.xlsx"),
        ("dataset", "People"),
    ]


async def test_the_path_to_a_sheet_that_is_not_there_is_not_found(
    catalog: FileCatalog,
) -> None:
    with pytest.raises(NodeNotFound):
        await catalog.path_to("budget.xlsx/9")


async def test_the_first_row_names_the_columns(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="budget.xlsx/1", limit=2))

    assert [column.name for column in result.columns] == [
        "quarter",
        "amount",
        "closed",
    ]
    assert result.rows[0] == ["Q1", "100", "false"]
    assert result.has_more is True


async def test_a_worksheet_column_has_no_type_of_its_own(fetch: FileFetch) -> None:
    """A spreadsheet types cells, so a column type read off a page would move."""
    result = await fetch.fetch(FetchRequest(node_id="budget.xlsx/1", limit=1))

    assert {column.type.category for column in result.columns} == {"string"}


async def test_a_cell_is_rendered_by_its_own_type(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="budget.xlsx/2", limit=10))

    assert [column.name for column in result.columns] == [
        "name",
        "started",
        "column_3",
    ]
    assert result.rows == [
        ["Ann", "2026-01-14T00:00:00", None],
        ["Bo", None, "note"],
    ]


async def test_a_page_of_a_sheet_starts_where_it_was_asked_to(
    fetch: FileFetch,
) -> None:
    result = await fetch.fetch(
        FetchRequest(node_id="budget.xlsx/1", limit=2, offset=100)
    )

    assert [row[0] for row in result.rows] == ["Q101", "Q102"]


async def test_the_last_page_of_a_sheet_knows_it_is_the_last(
    fetch: FileFetch,
) -> None:
    result = await fetch.fetch(
        FetchRequest(node_id="budget.xlsx/1", limit=5, offset=SHEET_ROWS - 2)
    )

    assert len(result.rows) == 2
    assert result.has_more is False


async def test_the_workbook_itself_is_read_as_its_first_sheet(
    fetch: FileFetch,
) -> None:
    """What somebody opening it in a spreadsheet would see first."""
    opened = await fetch.fetch(FetchRequest(node_id="budget.xlsx", limit=5))
    first = await fetch.fetch(FetchRequest(node_id="budget.xlsx/1", limit=5))

    assert [column.name for column in opened.columns] == [
        column.name for column in first.columns
    ]
    assert opened.rows == first.rows


async def test_a_sheet_that_does_not_exist_is_refused(fetch: FileFetch) -> None:
    with pytest.raises(ValueError, match="no sheet 9"):
        await fetch.fetch(FetchRequest(node_id="budget.xlsx/9", limit=1))


async def test_a_member_that_is_not_a_position_is_refused(fetch: FileFetch) -> None:
    with pytest.raises(ValueError, match="No such sheet"):
        await fetch.fetch(FetchRequest(node_id="budget.xlsx/Revenue", limit=1))


async def test_a_real_file_under_a_workbook_name_keeps_its_meaning(
    fetch: FileFetch,
) -> None:
    """`trap.xlsx` is a directory, so `trap.xlsx/1` is the file inside it.

    Read as the plain file it is — the text projection, because it has no
    suffix — rather than as the first sheet of anything.
    """
    result = await fetch.fetch(FetchRequest(node_id="trap.xlsx/1", limit=5))

    assert [column.name for column in result.columns] == ["line_no", "line"]
    assert result.rows == [["1", "id,name"], ["2", "7,seven"]]


async def test_bytes_that_are_not_a_workbook_are_refused(catalog: FileCatalog) -> None:
    with pytest.raises(NotAWorkbook, match="not a workbook"):
        await catalog.list_children("not-really.xlsx")


async def test_a_workbook_that_would_unpack_past_the_ceiling_is_refused(
    tmp_path: Path,
) -> None:
    """The zip's own directory says so; nothing is inflated to find out."""
    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"\0" * 4096)
    # Rewrite the declared uncompressed size the way a crafted archive would.
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
    assert entries[0].file_size == 4096
    _inflate_declared_size(path, MAX_UNPACKED_BYTES + 1)

    catalog = FileCatalog(FileSession(tmp_path))
    with pytest.raises(ValueError, match="unpacks to more than"):
        await catalog.list_children("bomb.xlsx")


async def test_a_sheet_offers_no_content_viewer(root: Path) -> None:
    content = FileContent(FileSession(root))

    with pytest.raises(ValueError, match="No such file"):
        await content.read_content(
            ContentRequest(node_id="budget.xlsx/1", representation="text")
        )


async def test_a_sheet_cannot_be_edited_as_a_document(root: Path) -> None:
    content = FileContent(FileSession(root))

    with pytest.raises(ValueError, match="No such file"):
        await content.read_editor_content(
            EditorContentRequest(node_id="budget.xlsx/1")
        )


async def test_a_workbook_cannot_be_edited_as_a_document(root: Path) -> None:
    """Its bytes are a zip; the editor is for a document, not a container."""
    content = FileContent(FileSession(root))

    with pytest.raises(ValueError, match="no text to show"):
        await content.read_editor_content(EditorContentRequest(node_id="budget.xlsx"))


async def test_a_sheet_offers_no_actions(root: Path) -> None:
    """Rename, delete and download name the kinds they act on; a dataset is
    not one of them, so the menu is empty without a rule of its own."""
    actions = FileActions(FileSession(root))

    assert await actions.available("budget.xlsx/1") == []
    assert [action.name for action in await actions.available("budget.xlsx")]


async def test_the_relation_model_of_a_sheet_states_where_it_sits(
    relations: FileRelations,
) -> None:
    model = await relations.relation_model("budget.xlsx/3")

    assert model.kind == "dataset"
    assert model.name == "Working notes"
    assert [column.name for column in model.columns] == ["note"]
    dataset = model.dataset
    assert isinstance(dataset, WorksheetDataset)
    assert dataset.workbook == "budget.xlsx"
    assert dataset.sheet_name == "Working notes"
    assert dataset.sheet_position == 3
    assert dataset.sheet_count == 3
    assert dataset.hidden is True


async def test_the_workbook_itself_states_no_columns(
    relations: FileRelations,
) -> None:
    with pytest.raises(ValueError, match="states no columns"):
        await relations.relation_model("budget.xlsx")


def _inflate_declared_size(path: Path, declared: int) -> None:
    """Claim a larger uncompressed size in the archive's own directory.

    A zip bomb is exactly this claim made honestly: the guard reads the
    declaration rather than inflating, so the test has to change what is
    declared. Both copies of the size are patched — the local header and the
    central directory — because zipfile reads the latter.
    """
    raw = bytearray(path.read_bytes())
    signature = b"PK\x01\x02"
    start = raw.index(signature)
    # Uncompressed size sits 24 bytes into the central directory header.
    raw[start + 24 : start + 28] = declared.to_bytes(4, "little")
    path.write_bytes(bytes(raw))
