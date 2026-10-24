import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused, PreparesConnector, TakesParams
from app.adapters.explorer.actions import ExplorerActions
from app.adapters.file.adapter import FileAdapter
from app.adapters.file.options import FileOptions
from app.adapters.file.storage import LocalStorage
from app.adapters.registry import AdapterContext


async def test_folder_draft_uses_the_home_path_even_from_a_nested_connector(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "library" / "Annual reports"
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("kept", encoding="utf-8")
    adapter = FileAdapter(
        FileOptions(path="library"), AdapterContext(home_dir=tmp_path)
    )
    action = adapter.action("connect_folder")
    assert isinstance(action, PreparesConnector)
    assert not isinstance(action, TakesParams)
    assert action.requires == "own"

    draft = await action.prepare_connector("Annual reports", {})

    assert draft.name == "Annual reports"
    assert draft.adapter_type == "file"
    assert draft.options == {"path": "/library/Annual reports"}
    assert str(tmp_path) not in draft.model_dump_json()
    derived = FileAdapter(
        FileOptions.model_validate(draft.options), AdapterContext(home_dir=tmp_path)
    )
    assert derived.root == folder
    assert [node.name for node in await derived.list_children(None)] == ["notes.txt"]
    assert (folder / "notes.txt").read_text(encoding="utf-8") == "kept"


@pytest.mark.parametrize("node_id", [None, "", "notes.txt", "../outside", "missing"])
async def test_a_connector_draft_requires_an_existing_child_directory(
    tmp_path: Path, node_id: str | None
) -> None:
    (tmp_path / "notes.txt").write_text("kept", encoding="utf-8")
    action = ExplorerActions(LocalStorage(tmp_path)).action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises((ValueError, ActionRefused)):
        await action.prepare_connector(node_id, {})


async def test_a_client_cannot_supply_the_draft_path(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    action = ExplorerActions(LocalStorage(tmp_path)).action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ValidationError):
        await action.prepare_connector("reports", {"path": "elsewhere"})


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
async def test_folder_drafts_follow_internal_links_but_refuse_escape(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    (home / "reports").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (home / "alias").symlink_to(home / "reports", target_is_directory=True)
    (home / "escape").symlink_to(tmp_path / "outside", target_is_directory=True)
    adapter = FileAdapter(FileOptions(), AdapterContext(home_dir=home))
    action = adapter.action("connect_folder")
    assert isinstance(action, PreparesConnector)
    draft = await action.prepare_connector("alias", {})
    assert draft.name == "alias"
    assert draft.options == {"path": "/reports"}
    with pytest.raises(ValueError):
        await action.prepare_connector("escape", {})


async def test_a_draft_cannot_rebase_a_root_outside_the_owners_home(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "outside" / "reports").mkdir(parents=True)
    actions = ExplorerActions(LocalStorage(tmp_path / "outside", home_dir=home))
    action = actions.action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ValueError, match="personal storage") as refused:
        await action.prepare_connector("reports", {})
    assert str(tmp_path) not in str(refused.value)


async def test_a_path_that_options_would_trim_is_not_retargeted(tmp_path: Path) -> None:
    (tmp_path / " reports").mkdir()
    action = ExplorerActions(LocalStorage(tmp_path)).action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ActionRefused, match="start or end with spaces"):
        await action.prepare_connector(" reports", {})


class _Elsewhere:
    """A storage whose places are no paths in anybody's home, as a server's
    folder or a bucket is: everything of a local one but the two answers."""

    def __init__(self, inner: LocalStorage) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name in ("connection_for", "path_in_home"):
            raise AttributeError(name)
        return getattr(self._inner, name)


async def test_a_database_file_becomes_a_draft_of_a_sqlite_connection_to_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "library" / "data").mkdir(parents=True)
    (tmp_path / "library" / "data" / "shop.db").write_bytes(b"SQLite format 3\x00")
    adapter = FileAdapter(FileOptions(path="library"), AdapterContext(home_dir=tmp_path))
    action = adapter.action("connect_sqlite")
    assert isinstance(action, PreparesConnector)
    assert action.requires == "own"

    offered = {one.name for one in await adapter.available("data/shop.db")}
    draft = await action.prepare_connector("data/shop.db", {})

    assert "connect_sqlite" in offered
    assert draft.name == "shop.db"
    assert draft.adapter_type == "sqlite"
    # The path below the owner's home, which is what a SQLite connection names.
    assert draft.options == {"path": "library/data/shop.db"}
    assert str(tmp_path) not in draft.model_dump_json()


async def test_a_file_that_is_no_database_is_not_offered_and_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("kept", encoding="utf-8")
    actions = ExplorerActions(LocalStorage(tmp_path))
    action = actions.action("connect_sqlite")
    assert isinstance(action, PreparesConnector)

    offered = {one.name for one in await actions.available("notes.txt")}

    assert "connect_sqlite" not in offered
    with pytest.raises(ActionRefused, match="database file"):
        await action.prepare_connector("notes.txt", {})


async def test_a_database_outside_personal_storage_is_offered_greyed_with_the_reason(
    tmp_path: Path,
) -> None:
    (tmp_path / "shop.db").write_bytes(b"SQLite format 3\x00")
    storage = _Elsewhere(LocalStorage(tmp_path))
    actions = ExplorerActions(storage)

    offers = await actions.action_offers("shop.db")
    action = actions.action("connect_sqlite")
    assert isinstance(action, PreparesConnector)

    assert "connect_sqlite" not in {one.name for one in offers.actions}
    assert offers.reason_for("connect_sqlite") == "Only a file in your personal storage can be connected as SQLite"
    with pytest.raises(ActionRefused, match="personal storage"):
        await action.prepare_connector("shop.db", {})

