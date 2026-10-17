"""Putting what was copied or cut into the folder being looked at."""

from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused, ActionResult, TakesParams
from app.adapters.explorer.actions import ExplorerActions
from app.adapters.file.storage import LocalStorage
from app.core.translation import current_language


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id,name\n1,one\n", encoding="utf-8")
    (tmp_path / "archive").mkdir()
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def actions(root: Path) -> ExplorerActions:
    return ExplorerActions(LocalStorage(root))


async def _paste(
    actions: ExplorerActions, into: str | None, **params: object
) -> ActionResult:
    action = actions.action("paste")
    assert isinstance(action, TakesParams)
    return await action.perform(into, params)


async def test_a_file_is_copied_and_both_ends_stay(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _paste(actions, "archive", sources=["notes.txt"], mode="copy")

    assert result.message == "1 item copied"
    assert (root / "archive" / "notes.txt").read_text(encoding="utf-8") == "first\n"
    assert (root / "notes.txt").exists()
    # Only the folder that gained something needs re-reading.
    assert result.reload_node_ids == ["archive"]


async def test_a_file_is_moved_and_both_folders_are_named(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _paste(actions, "archive", sources=["notes.txt"], mode="move")

    assert result.message == "1 item moved"
    assert (root / "archive" / "notes.txt").exists()
    assert not (root / "notes.txt").exists()
    # The one it went into, and the one it left. The root travels as None.
    assert result.reload_node_ids == ["archive", None]


async def test_a_folder_goes_with_everything_in_it(
    actions: ExplorerActions, root: Path
) -> None:
    await _paste(actions, "archive", sources=["reports"], mode="copy")

    assert (root / "archive" / "reports" / "q3.csv").exists()
    assert (root / "reports" / "q3.csv").exists()


async def test_several_things_go_at_once(actions: ExplorerActions, root: Path) -> None:
    result = await _paste(
        actions, "archive", sources=["notes.txt", "reports"], mode="move"
    )

    assert result.message == "2 items moved"
    assert (root / "archive" / "notes.txt").exists()
    assert (root / "archive" / "reports" / "q3.csv").exists()


async def test_a_taken_name_is_refused_by_default(
    actions: ExplorerActions, root: Path
) -> None:
    (root / "archive" / "notes.txt").write_text("already", encoding="utf-8")

    with pytest.raises(ActionRefused) as refused:
        await _paste(actions, "archive", sources=["notes.txt"], mode="copy")

    assert refused.value.reason == "conflict"
    assert (root / "archive" / "notes.txt").read_text(encoding="utf-8") == "already"


async def test_a_taken_name_can_be_kept_beside_the_one_that_is_there(
    actions: ExplorerActions, root: Path
) -> None:
    (root / "archive" / "notes.txt").write_text("already", encoding="utf-8")

    await _paste(
        actions, "archive", sources=["notes.txt"], mode="copy", conflict="rename"
    )

    assert (root / "archive" / "notes.txt").read_text(encoding="utf-8") == "already"
    assert (root / "archive" / "notes.txt (1)").read_text(encoding="utf-8") == "first\n"


async def test_a_taken_name_can_be_replaced_when_asked(
    actions: ExplorerActions, root: Path
) -> None:
    (root / "archive" / "notes.txt").write_text("already", encoding="utf-8")

    await _paste(
        actions, "archive", sources=["notes.txt"], mode="copy", conflict="replace"
    )

    assert (root / "archive" / "notes.txt").read_text(encoding="utf-8") == "first\n"


async def test_a_folder_cannot_be_put_inside_itself(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused, match="inside itself"):
        await _paste(actions, "reports", sources=["reports"], mode="move")


async def test_a_folder_cannot_be_put_inside_something_it_holds(
    actions: ExplorerActions, root: Path
) -> None:
    (root / "reports" / "inner").mkdir()

    with pytest.raises(ActionRefused, match="inside itself"):
        await _paste(actions, "reports/inner", sources=["reports"], mode="move")


async def test_a_source_outside_the_root_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ValueError):
        await _paste(actions, "archive", sources=["../escape"], mode="copy")


async def test_the_root_itself_cannot_be_moved(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused, match="root folder"):
        await _paste(actions, "archive", sources=[""], mode="move")


async def test_nothing_held_is_nothing_to_paste(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused, match="Copy or cut"):
        await _paste(actions, "archive", sources=[], mode="copy")


async def test_paste_is_offered_on_a_folder_and_on_the_root(
    actions: ExplorerActions,
) -> None:
    """It puts something into a place, so the place is what admits it."""
    folder = {action.name for action in await actions.available("archive")}
    root = {action.name for action in await actions.available(None)}
    file = {action.name for action in await actions.available("notes.txt")}

    assert "paste" in folder
    assert "paste" in root
    assert "paste" not in file


async def test_the_form_names_the_two_fields_the_client_fills() -> None:
    """By purpose, so the form fills them without knowing the action."""
    from app.adapters.explorer.actions import PasteParams

    properties = PasteParams.model_json_schema()["properties"]

    assert properties["sources"]["x-ui-purpose"] == "clipboard-nodes"
    assert properties["mode"]["x-ui-purpose"] == "clipboard-mode"
    assert properties["sources"]["x-ui-hidden"] is True
    assert properties["mode"]["x-ui-hidden"] is True


async def test_a_russian_request_reads_what_was_pasted_in_russian(
    actions: ExplorerActions, root: Path
) -> None:
    """A whole sentence per count, so the language words its own agreement (D226)."""
    (root / "plan.txt").write_text("second\n", encoding="utf-8")
    token = current_language.set("ru")
    try:
        moved = await _paste(
            actions, "archive", sources=["notes.txt", "plan.txt"], mode="move"
        )
        (root / "notes.txt").write_text("again\n", encoding="utf-8")
        with pytest.raises(ActionRefused) as refused:
            await _paste(actions, "archive", sources=["notes.txt"], mode="copy")
    finally:
        current_language.reset(token)

    assert moved.message == "Перемещено элементов: 2"
    assert refused.value.message == "notes.txt уже существует"
