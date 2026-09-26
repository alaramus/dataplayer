"""What a kind makes, and what it answers of a node a link will make (D178)."""

from pathlib import Path

from app.adapters.fetch import FetchColumn
from app.adapters.file.storage import LocalStorage
from app.adapters.relation import ColumnType
from app.connectors.paste.files import FileCopy, FileMove
from app.connectors.paste.kinds import text_column
from app.connectors.paste.models import Foreseen, PasteColumn
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.rows import RowsIntoRelation, RowsNewRelation
from tests.utils.paste_sources import Database, Explorer, Table

ORDERS = Foreseen(
    kind="table",
    name="orders",
    columns=[
        FetchColumn(name="id", type=ColumnType(sql="integer", category="number")),
        FetchColumn(name="total", type=ColumnType(sql="numeric", category="number")),
    ],
)


def test_each_kind_says_what_it_makes_and_names_it() -> None:
    saved = RelationCsv().made(ORDERS, None, None)
    assert saved == Foreseen(kind="file", name="orders.csv", columns=[text_column("id"), text_column("total")])
    assert RelationCsv().made(ORDERS, "monthly", None) == saved.model_copy(update={"name": "monthly.csv"})
    # A name no file can have falls back to the suggested one.
    assert RelationCsv().made(ORDERS, "a/b", None) == saved
    assert RelationCsv().made(saved, None, None) is None

    made = RowsNewRelation().made(
        saved, "loaded", [PasteColumn(source="id", target="order_id", type_code="bigint")]
    )
    assert made is not None and (made.kind, made.name) == ("table", "loaded")
    assert [(one.name, one.type.sql, one.insertable) for one in made.columns] == [("order_id", "bigint", True)]
    assert RowsIntoRelation().made(saved, None, None) is None

    # A copy is what it copies, columns and all; a table is not carried.
    assert FileCopy().made(saved, "ignored", None) == saved
    assert FileMove().made(Foreseen(kind="folder", name="reports"), None, None) == Foreseen(
        kind="folder", name="reports"
    )
    assert FileCopy().made(ORDERS, None, None) is None
    assert all(kind.makes for kind in (RelationCsv(), RowsNewRelation(), FileCopy(), FileMove()))
    assert not RowsIntoRelation().makes


async def test_a_file_yet_to_be_made_is_offered_by_its_name(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "orders.csv").write_text("id\n1\n")
    files = Explorer(LocalStorage(tmp_path))
    coming = Foreseen(kind="file", name="orders.csv", columns=[text_column("id")])

    taken = await FileCopy().foresee(files, files, coming, "reports")
    assert (taken.available, taken.name_conflict, taken.reason) == (False, True, "orders.csv is already there")
    assert taken.makes is True

    into_coming = await FileCopy().foresee(files, files, coming, Foreseen(kind="folder", name="later"))
    assert into_coming.available is True
    refused = await FileCopy().foresee(files, files, ORDERS, "reports")
    assert (refused.available, refused.reason) == (False, FileCopy().needs)


async def test_a_table_yet_to_be_made_is_saved_as_csv_by_its_own_name(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    files = Explorer(LocalStorage(tmp_path))

    offer = await RelationCsv().foresee(Table(), files, ORDERS, "reports")

    assert (offer.available, offer.suggested_name, offer.name_conflict) == (True, "orders.csv", False)
    (tmp_path / "reports" / "orders.csv").write_text("id\n")
    assert (await RelationCsv().foresee(Table(), files, ORDERS, "reports")).name_conflict is True
    # From a real table into a folder a link will make: nothing there is taken.
    later = await RelationCsv().foresee(Table(), files, "public.people", Foreseen(kind="folder", name="x"))
    assert (later.available, later.suggested_name) == (True, "people.csv")
    assert (await RelationCsv().foresee(Table(), files, Foreseen(kind="file", name="a.csv"), "reports")).available is False


async def test_rows_go_into_a_table_yet_to_be_made_by_its_chosen_columns() -> None:
    database = Database()
    csv = Foreseen(kind="file", name="orders.csv", columns=[text_column("id"), text_column("total")])
    table = RowsNewRelation().made(
        csv, "loaded", [PasteColumn(source="id", target="id", type_code="text")]
    )
    assert table is not None

    offer = await RowsIntoRelation().foresee(database, database, csv, table)

    assert offer.available is True
    assert [one.name for one in offer.source_columns] == ["id", "total"]
    assert [one.name for one in offer.target_columns] == ["id"]
    assert (await RowsIntoRelation().foresee(database, database, csv, None)).available is False
    folder = Foreseen(kind="folder", name="reports")
    assert (await RowsIntoRelation().foresee(database, database, folder, table)).reason == "This cannot be read as rows"
    # A schema is never something a link makes.
    assert (await RowsNewRelation().foresee(database, database, csv, table)).reason == (
        "Choose the schema the table goes in"
    )
