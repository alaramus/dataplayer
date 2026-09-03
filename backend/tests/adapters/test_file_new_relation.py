from pathlib import Path

import pytest

from app.adapters.file.new_relation import FileNewRelations
from app.adapters.file.session import FileSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "notes.txt").write_text("top\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def relations(root: Path) -> FileNewRelations:
    return FileNewRelations(FileSession(root))


def _request(
    name: str = "orders",
    *,
    parent: str = "reports",
    columns: tuple[str, ...] = ("id", "note"),
    rows: list[list[str | None]] | None = None,
) -> CreateRelationRequest:
    return CreateRelationRequest(
        parent_node_id=parent,
        name=name,
        columns=[NewColumn(name=column, type_code="text") for column in columns],
        rows=[["1", "first"], ["2", None]] if rows is None else rows,
    )


async def test_a_folder_accepts_a_relation_and_offers_the_one_type_it_has(
    relations: FileNewRelations,
) -> None:
    """Every value in a delimited file is text, so there is nothing to choose."""
    options = await relations.new_relation_options("reports")

    assert options.supported is True
    assert [option.code for option in options.column_type_options] == ["text"]


async def test_the_root_is_a_folder_like_any_other(
    relations: FileNewRelations,
) -> None:
    """A connection with no folders in it still has somewhere to write."""
    options = await relations.new_relation_options("")

    assert options.supported is True


async def test_a_file_says_why_it_holds_no_relation_rather_than_failing(
    relations: FileNewRelations,
) -> None:
    options = await relations.new_relation_options("notes.txt")

    assert options.supported is False
    assert options.reason is not None


async def test_a_node_that_is_not_there_is_not_a_container(
    relations: FileNewRelations,
) -> None:
    with pytest.raises(NodeNotFound):
        await relations.new_relation_options("nowhere")


@pytest.mark.parametrize("parent", ["../secrets", "/etc", "C:/Windows"])
async def test_a_container_outside_the_root_is_refused(
    relations: FileNewRelations, parent: str
) -> None:
    """The one containment rule, before anything is written (D8)."""
    with pytest.raises(ValueError):
        await relations.new_relation_options(parent)


async def test_the_rows_become_a_delimited_file_the_catalog_can_describe(
    relations: FileNewRelations, root: Path
) -> None:
    result = await relations.create_relation(_request())

    assert isinstance(result, RelationCreated)
    assert result.inserted == 2
    assert result.node.name == "orders.csv"
    assert result.node.id == "reports/orders.csv"
    written = root / "reports" / "orders.csv"
    # An absent value is an empty cell: a delimited file has no null (D23).
    assert written.read_text(encoding="utf-8") == "id,note\n1,first\n2,\n"


async def test_a_name_that_is_already_a_delimited_one_is_left_alone(
    relations: FileNewRelations, root: Path
) -> None:
    result = await relations.create_relation(_request("orders.tsv"))

    assert isinstance(result, RelationCreated)
    # The name decides the delimiter, as it does when one is read back.
    assert (root / "reports" / "orders.tsv").read_text(
        encoding="utf-8"
    ) == "id\tnote\n1\tfirst\n2\t\n"


async def test_a_taken_name_is_refused_and_nothing_is_replaced(
    relations: FileNewRelations, root: Path
) -> None:
    (root / "reports" / "orders.csv").write_text("kept\n", encoding="utf-8")

    with pytest.raises(ValueError):
        await relations.create_relation(_request())

    assert (root / "reports" / "orders.csv").read_text(encoding="utf-8") == "kept\n"


@pytest.mark.parametrize("name", ["../orders", "a/b", "C:orders"])
async def test_a_name_that_is_not_a_plain_name_is_refused(
    relations: FileNewRelations, name: str
) -> None:
    """A typed name and a path are the same kind of string here (D8)."""
    with pytest.raises(ValueError):
        await relations.create_relation(_request(name))


async def test_a_type_this_source_never_published_is_refused(
    relations: FileNewRelations, root: Path
) -> None:
    request = CreateRelationRequest(
        parent_node_id="reports",
        name="orders",
        columns=[NewColumn(name="id", type_code="integer")],
        rows=[],
    )

    with pytest.raises(ValueError):
        await relations.create_relation(request)

    assert list((root / "reports").iterdir()) == []


async def test_a_relation_may_start_with_no_rows_at_all(
    relations: FileNewRelations, root: Path
) -> None:
    result = await relations.create_relation(_request(rows=[]))

    assert isinstance(result, RelationCreated)
    assert result.inserted == 0
    assert (root / "reports" / "orders.csv").read_text(encoding="utf-8") == "id,note\n"


async def test_a_file_is_not_a_container_for_a_new_relation(
    relations: FileNewRelations,
) -> None:
    with pytest.raises(ValueError):
        await relations.create_relation(_request(parent="notes.txt"))


async def test_nothing_is_left_behind_when_the_write_fails(
    relations: FileNewRelations, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The draft is beside the destination, so a failure must not leave it."""
    import app.adapters.file.new_relation as module

    def explode(_source: object, _target: object) -> None:
        raise OSError("disk is full")

    monkeypatch.setattr(module.os, "link", explode)

    with pytest.raises(OSError, match="disk is full"):
        await relations.create_relation(_request())

    assert list((root / "reports").iterdir()) == []
