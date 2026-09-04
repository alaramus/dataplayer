import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused, PreparesConnector, TakesParams
from app.adapters.file.actions import FileActions
from app.adapters.file.adapter import FileAdapter
from app.adapters.file.options import FileOptions
from app.adapters.file.session import FileSession
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
    assert draft.options == {"path": "library/Annual reports"}
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
    action = FileActions(FileSession(tmp_path)).action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises((ValueError, ActionRefused)):
        await action.prepare_connector(node_id, {})


async def test_a_client_cannot_supply_the_draft_path(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    action = FileActions(FileSession(tmp_path)).action("connect_folder")
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
    assert draft.options == {"path": "reports"}
    with pytest.raises(ValueError):
        await action.prepare_connector("escape", {})


async def test_a_draft_cannot_rebase_a_root_outside_the_owners_home(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "outside" / "reports").mkdir(parents=True)
    actions = FileActions(FileSession(tmp_path / "outside", home_dir=home))
    action = actions.action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ValueError, match="personal storage") as refused:
        await action.prepare_connector("reports", {})
    assert str(tmp_path) not in str(refused.value)


async def test_a_path_that_options_would_trim_is_not_retargeted(tmp_path: Path) -> None:
    (tmp_path / " reports").mkdir()
    action = FileActions(FileSession(tmp_path)).action("connect_folder")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ActionRefused, match="start or end with spaces"):
        await action.prepare_connector(" reports", {})
