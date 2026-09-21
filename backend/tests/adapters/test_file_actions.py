from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused, ActionResult, TakesFile, TakesParams
from app.adapters.explorer.actions import ExplorerActions
from app.adapters.file.storage import LocalStorage
from tests.utils.files import look


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id,name\n1,one\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    return tmp_path


@pytest.fixture
def actions(root: Path) -> ExplorerActions:
    return ExplorerActions(LocalStorage(root))


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "uploaded.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


async def _run(
    actions: ExplorerActions, action_name: str, node_id: str | None, **params: object
) -> ActionResult:
    action = actions.action(action_name)
    assert isinstance(action, TakesParams)
    return await action.perform(node_id, params)


async def _upload(
    actions: ExplorerActions, node_id: str | None, payload: Upload, **params: object
) -> ActionResult:
    action = actions.action("upload")
    assert isinstance(action, TakesFile)
    return await action.perform_with_file(node_id, params, payload)


# --- what applies where ------------------------------------------------------


async def test_a_directory_admits_creating_uploading_renaming_and_deleting(
    actions: ExplorerActions,
) -> None:
    names = {action.name for action in await actions.available("reports")}

    assert names == {
        "create_folder",
        "create_file",
        "connect_folder",
        "upload",
        "paste",
        "download",
        "create_archive",
        "rename",
        "delete",
    }


async def test_a_file_admits_only_renaming_and_deleting(actions: ExplorerActions) -> None:
    """Not extracting: a file that is not an archive is not one to expand."""
    names = {action.name for action in await actions.available("notes.txt")}

    assert names == {"download", "create_archive", "rename", "delete"}


async def test_the_root_of_the_connector_cannot_be_renamed_or_deleted(
    actions: ExplorerActions,
) -> None:
    """A question of state, not of kind: the root is an ordinary directory."""
    names = {action.name for action in await actions.available(None)}

    assert names == {"create_folder", "create_file", "upload", "paste"}


async def test_the_whole_vocabulary_is_offered_whatever_the_node(
    actions: ExplorerActions,
) -> None:
    """What the source can do at all, apart from what this node admits.

    The vocabulary and applicability remain separate source statements; the
    client may then omit commands that do not apply to the current selection.
    """
    names = {action.name for action in await actions.all_actions()}

    assert names == {
        "create_folder",
        "create_file",
        "connect_folder",
        "upload",
        "paste",
        "download",
        "create_archive",
        "extract_archive",
        "rename",
        "delete",
    }


async def test_each_action_says_whether_it_changes_the_node_or_its_contents(
    actions: ExplorerActions,
) -> None:
    by_name = {action.name: action.acts_on for action in await actions.all_actions()}

    assert by_name == {
        "create_folder": "children",
        "create_file": "children",
        "connect_folder": "node",
        "upload": "children",
        # Pasting puts something into a place, so the place is the subject.
        "paste": "children",
        "download": "node",
        # Both archive commands are about the nodes that were picked out: one
        # packs them, the other expands one of them.
        "create_archive": "node",
        "extract_archive": "node",
        "rename": "node",
        "delete": "node",
    }


async def test_a_node_outside_the_root_admits_nothing(actions: ExplorerActions) -> None:
    with pytest.raises(ValueError):
        await actions.available("../..")


async def test_a_node_that_does_not_exist_admits_nothing(
    actions: ExplorerActions,
) -> None:
    with pytest.raises(ValueError):
        await actions.available("nowhere")


# --- create_folder -----------------------------------------------------------


async def test_creating_a_folder_makes_it(actions: ExplorerActions, root: Path) -> None:
    result = await _run(actions, "create_folder", "reports", name="2026")

    assert (root / "reports" / "2026").is_dir()
    assert result.reload_node_ids == ["reports"]


async def test_creating_a_folder_in_the_root_reloads_the_root(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _run(actions, "create_folder", None, name="inbox")

    assert (root / "inbox").is_dir()
    assert result.reload_node_ids == [None]


async def test_default_folder_names_are_numbered_when_taken(
    actions: ExplorerActions, root: Path
) -> None:
    first = await _run(actions, "create_folder", None)
    second = await _run(actions, "create_folder", None)

    assert (root / "new folder").is_dir()
    assert (root / "new folder (1)").is_dir()
    assert first.message == "Folder new folder created"
    assert second.message == "Folder new folder (1) created"


@pytest.mark.parametrize("name", ["..", "../evil", "/etc", "C:", "a/b", ".", ""])
async def test_a_folder_name_must_be_a_plain_name(
    actions: ExplorerActions, name: str
) -> None:
    """The same rule that judges a path segment, not a second one."""
    with pytest.raises(ValueError):
        await _run(actions, "create_folder", None, name=name)


# --- create_file -------------------------------------------------------------


async def test_creating_a_file_makes_an_empty_one(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _run(actions, "create_file", "reports", name="example.txt")

    assert (root / "reports" / "example.txt").read_bytes() == b""
    assert result.message == "example.txt created"
    assert result.reload_node_ids == ["reports"]


async def test_creating_a_file_in_the_root_reloads_the_root(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _run(actions, "create_file", None, name="todo.md")

    assert (root / "todo.md").is_file()
    assert result.reload_node_ids == [None]


async def test_a_file_name_defaults_when_the_form_is_unchanged(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _run(actions, "create_file", "reports")

    assert (root / "reports" / "new file").read_bytes() == b""
    assert result.message == "new file created"


async def test_a_file_over_a_taken_name_is_refused(
    actions: ExplorerActions, root: Path
) -> None:
    """Not numbered like a folder: whoever named it refers to it by that name."""
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "create_file", None, name="notes.txt")

    assert caught.value.reason == "conflict"
    assert (root / "notes.txt").read_text(encoding="utf-8") == "first\n"
    assert not (root / "notes (1).txt").exists()


async def test_a_file_over_a_folder_name_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "create_file", None, name="reports")

    assert caught.value.reason == "conflict"


@pytest.mark.parametrize(
    "name", ["..", "../evil.txt", "/etc/passwd", "C:evil.txt", "a/b.txt", ".", ""]
)
async def test_a_file_name_must_be_a_plain_name(
    actions: ExplorerActions, root: Path, name: str
) -> None:
    """The one containment rule, not a second one (D8)."""
    with pytest.raises(ValueError):
        await _run(actions, "create_file", None, name=name)

    assert not (root.parent / "evil.txt").exists()


async def test_a_file_cannot_be_created_inside_a_file(actions: ExplorerActions) -> None:
    with pytest.raises(ValueError):
        await _run(actions, "create_file", "notes.txt", name="x.txt")


# --- rename ------------------------------------------------------------------


async def test_renaming_a_file_moves_it_within_its_folder(
    actions: ExplorerActions, root: Path
) -> None:
    result = await _run(actions, "rename", "reports/q3.csv", new_name="q4.csv")

    assert not (root / "reports" / "q3.csv").exists()
    assert (root / "reports" / "q4.csv").read_text(encoding="utf-8").startswith("id,")
    assert result.reload_node_ids == ["reports"]


async def test_renaming_a_folder_keeps_what_is_inside(
    actions: ExplorerActions, root: Path
) -> None:
    await _run(actions, "rename", "reports", new_name="archive")

    assert (root / "archive" / "q3.csv").exists()


async def test_renaming_onto_a_taken_name_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "rename", "reports", new_name="empty")

    assert caught.value.reason == "conflict"


async def test_renaming_the_root_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "rename", None, new_name="somewhere")

    assert caught.value.reason == "not_applicable"


@pytest.mark.parametrize("new_name", ["../escaped", "/etc/passwd", "C:", "a/b"])
async def test_a_new_name_cannot_leave_the_folder(
    actions: ExplorerActions, new_name: str
) -> None:
    with pytest.raises(ValueError):
        await _run(actions, "rename", "notes.txt", new_name=new_name)


# --- delete ------------------------------------------------------------------


async def test_deleting_a_file_removes_it(actions: ExplorerActions, root: Path) -> None:
    result = await _run(actions, "delete", "notes.txt")

    assert not (root / "notes.txt").exists()
    assert result.reload_node_ids == [None]


async def test_deleting_an_empty_folder_removes_it(
    actions: ExplorerActions, root: Path
) -> None:
    await _run(actions, "delete", "empty")

    assert not (root / "empty").exists()


async def test_deleting_a_folder_removes_everything_inside_after_confirmation(
    actions: ExplorerActions, root: Path
) -> None:
    await _run(actions, "delete", "reports")

    assert not (root / "reports").exists()


async def test_deleting_the_root_is_refused(actions: ExplorerActions, root: Path) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "delete", None)

    assert caught.value.reason == "not_applicable"
    assert await look(root.is_dir)


async def test_deleting_outside_the_root_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ValueError):
        await _run(actions, "delete", "../..")


# --- upload ------------------------------------------------------------------


async def test_uploading_writes_the_file(actions: ExplorerActions, root: Path) -> None:
    result = await _upload(actions, "reports", Upload(b"id,name\n7,seven\n"))

    assert (root / "reports" / "uploaded.csv").read_text(encoding="utf-8") == (
        "id,name\n7,seven\n"
    )
    assert result.reload_node_ids == ["reports"]


async def test_uploading_leaves_no_temporary_file_behind(
    actions: ExplorerActions, root: Path
) -> None:
    await _upload(actions, None, Upload(b"body"))

    leftovers = await look(lambda: [entry.name for entry in root.iterdir()])
    assert [name for name in leftovers if name.startswith(".")] == []


async def test_uploading_over_a_taken_name_is_refused(
    actions: ExplorerActions, root: Path
) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _upload(actions, "reports", Upload(b"new", filename="q3.csv"))

    assert caught.value.reason == "conflict"
    assert (root / "reports" / "q3.csv").read_text(encoding="utf-8") == "id,name\n1,one\n"


async def test_uploading_over_a_taken_name_is_allowed_when_asked(
    actions: ExplorerActions, root: Path
) -> None:
    await _upload(
        actions,
        "reports",
        Upload(b"new", filename="q3.csv"),
        conflict="replace",
    )

    assert (root / "reports" / "q3.csv").read_text(encoding="utf-8") == "new"


async def test_uploading_over_a_taken_name_can_keep_both(
    actions: ExplorerActions, root: Path
) -> None:
    (root / "reports" / "q3 (1).csv").write_text("older", encoding="utf-8")

    result = await _upload(
        actions, "reports", Upload(b"new", filename="q3.csv"), conflict="rename"
    )

    assert (root / "reports" / "q3.csv").read_text(encoding="utf-8") == (
        "id,name\n1,one\n"
    )
    assert (root / "reports" / "q3 (2).csv").read_text(encoding="utf-8") == "new"
    assert result.message == "q3 (2).csv uploaded"


@pytest.mark.parametrize("filename", ["../evil.txt", "/etc/passwd", "C:evil", "", None])
async def test_the_name_of_an_uploaded_file_is_judged_like_a_path_segment(
    actions: ExplorerActions, filename: str | None
) -> None:
    """The filename comes from the client too, and gets the same rule."""
    with pytest.raises(ValueError):
        await _upload(actions, "reports", Upload(b"body", filename=filename))


async def test_uploading_more_than_the_ceiling_is_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 8)
    actions = ExplorerActions(LocalStorage(root))

    with pytest.raises(ActionRefused) as caught:
        await _upload(actions, None, Upload(b"x" * 64, filename="big.bin"))

    assert caught.value.reason == "too_large"
    assert not (root / "big.bin").exists()
    assert await look(lambda: list(root.glob(".*"))) == []


async def test_uploading_into_a_file_is_refused(actions: ExplorerActions) -> None:
    with pytest.raises(ValueError):
        await _upload(actions, "notes.txt", Upload(b"body"))
