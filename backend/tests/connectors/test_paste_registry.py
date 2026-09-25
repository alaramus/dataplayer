"""Which kinds of paste a pair of connections is offered (D164)."""

from pathlib import Path

from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import ConnectionCheckResult, DataAdapter
from app.connectors.paste.registry import KINDS, kind_named
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


def test_every_kind_is_reachable_by_its_name() -> None:
    assert [kind_named(kind.name) for kind in KINDS] == list(KINDS)
