"""Which kinds of paste a pair of connections is offered (D164)."""

from pathlib import Path

from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import ConnectionCheckResult, DataAdapter
from app.connectors.paste.models import PasteOffer
from app.connectors.paste.registry import KINDS, kind_named, open_kinds, outranked
from app.core.access import Access
from tests.utils.paste_sources import Database, Explorer, Table


class Keys:
    """A source with nothing any kind reads or writes, like a key store."""

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")


def test_kinds_are_matched_by_what_each_end_can_do(tmp_path: Path) -> None:
    files = Explorer(LocalStorage(tmp_path))
    table = Table()

    def serving(source: DataAdapter, destination: DataAdapter) -> list[str]:
        return [kind.name for kind in KINDS if kind.serves(source, destination)]

    assert serving(files, files) == ["file_copy", "file_move"]
    assert serving(table, files) == ["relation_csv"]
    assert serving(files, table) == []
    assert serving(table, table) == []
    assert serving(Keys(), files) == []


def test_rows_go_into_a_database_and_never_into_a_folder(tmp_path: Path) -> None:
    """A folder takes a file as it is or a table as CSV (D166)."""
    files = Explorer(LocalStorage(tmp_path))
    database = Database()

    def serving(source: DataAdapter, destination: DataAdapter) -> list[str]:
        return [kind.name for kind in KINDS if kind.serves(source, destination)]

    assert serving(database, database) == ["rows_new_relation", "rows_into_relation"]
    assert serving(database, files) == []
    assert serving(Keys(), database) == []


def test_what_two_connections_give_each_other_is_what_the_person_may_run(
    tmp_path: Path,
) -> None:
    """The first question of the hint, asked of no node (D174)."""
    files = Explorer(LocalStorage(tmp_path))
    database = Database()

    def names(
        source: DataAdapter, held: Access, destination: DataAdapter, holds: Access
    ) -> list[str]:
        return [kind.name for kind in open_kinds(source, held, destination, holds)]

    assert names(files, "read", files, "write") == ["file_copy"]
    assert names(files, "write", files, "write") == ["file_copy", "file_move"]
    assert names(database, "read", database, "write") == ["rows_into_relation"]
    assert names(database, "read", database, "structure") == [
        "rows_new_relation",
        "rows_into_relation",
    ]
    assert names(files, "own", database, "read") == []


def test_a_table_can_be_copied_but_never_cut(tmp_path: Path) -> None:
    table = Table()
    files = Explorer(LocalStorage(tmp_path))

    copying = [kind.name for kind in KINDS if kind.mode == "copy" and kind.takes_from(table)]
    cutting = [kind.name for kind in KINDS if kind.mode == "move" and kind.takes_from(table)]

    assert copying == ["relation_csv"]
    assert cutting == []
    assert [kind.name for kind in KINDS if kind.takes_from(files)] == [
        "file_copy",
        "file_move",
    ]


def test_a_table_copied_whole_stands_in_for_one_made_from_its_rows() -> None:
    """Paste opens one window, the one that fits what was copied (D182)."""
    whole = PasteOffer(kind="tables_copy", title="Copy tables", available=True)
    rows = PasteOffer(kind="rows_new_relation", title="Create a table", available=True)
    into = PasteOffer(kind="rows_into_relation", title="Add rows to a table", available=True)

    assert outranked([whole, rows, into]) == [whole, into]
    # One that cannot run stands in for nothing: a view is still made from rows.
    refused = whole.model_copy(update={"available": False, "reason": "only tables"})
    assert outranked([refused, rows]) == [refused, rows]


def test_every_kind_is_reachable_by_its_name() -> None:
    assert [kind_named(kind.name) for kind in KINDS] == list(KINDS)


def test_every_kind_says_what_its_source_must_be() -> None:
    """What a pair shows before anything is ticked (D167)."""
    assert all(kind.needs.startswith("Tick ") for kind in KINDS)

