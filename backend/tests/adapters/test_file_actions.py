from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused, ActionResult, TakesFile, TakesParams
from app.adapters.file.actions import FileActions
from app.adapters.file.session import FileSession
from tests.utils.files import look


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id,name\n1,one\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    return tmp_path


@pytest.fixture
def actions(root: Path) -> FileActions:
    return FileActions(FileSession(root))


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "uploaded.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


async def _run(
    actions: FileActions, action_name: str, node_id: str | None, **params: object
) -> ActionResult:
    action = actions.action(action_name)
    assert isinstance(action, TakesParams)
    return await action.perform(node_id, params)


async def _upload(
    actions: FileActions, node_id: str | None, payload: Upload, **params: object
) -> ActionResult:
    action = actions.action("upload")
    assert isinstance(action, TakesFile)
    return await action.perform_with_file(node_id, params, payload)


# --- what applies where ------------------------------------------------------


async def test_a_directory_admits_creating_uploading_renaming_and_deleting(
    actions: FileActions,
) -> None:
    names = {action.name for action in await actions.available("reports")}

    assert names == {"create_folder", "upload", "download", "rename", "delete"}


async def test_a_file_admits_only_renaming_and_deleting(actions: FileActions) -> None:
    names = {action.name for action in await actions.available("notes.txt")}

    assert names == {"download", "rename", "delete"}


async def test_the_root_of_the_connector_cannot_be_renamed_or_deleted(
    actions: FileActions,
) -> None:
    """A question of state, not of kind: the root is an ordinary directory."""
    names = {action.name for action in await actions.available(None)}

    assert names == {"create_folder", "upload"}


async def test_the_whole_vocabulary_is_offered_whatever_the_node(
    actions: FileActions,
) -> None:
    """What the source can do at all, apart from what this node admits.

    A menu built from the applicable set alone changes shape as the user walks
    the tree; one built from the vocabulary stays put and greys out what does
    not apply here.
    """
    names = {action.name for action in actions.all_actions()}

    assert names == {"create_folder", "upload", "download", "rename", "delete"}


async def test_each_action_says_whether_it_changes_the_node_or_its_contents(
    actions: FileActions,
) -> None:
    by_name = {action.name: action.acts_on for action in actions.all_actions()}

    assert by_name == {
        "create_folder": "children",
        "upload": "children",
        "download": "node",
        "rename": "node",
        "delete": "node",
    }


async def test_a_node_outside_the_root_admits_nothing(actions: FileActions) -> None:
    with pytest.raises(ValueError):
        await actions.available("../..")


async def test_a_node_that_does_not_exist_admits_nothing(
    actions: FileActions,
) -> None:
    with pytest.raises(ValueError):
        await actions.available("nowhere")


# --- create_folder -----------------------------------------------------------


async def test_creating_a_folder_makes_it(actions: FileActions, root: Path) -> None:
    result = await _run(actions, "create_folder", "reports", name="2026")

    assert (root / "reports" / "2026").is_dir()
    assert result.reload_node_id == "reports"


async def test_creating_a_folder_in_the_root_reloads_the_root(
    actions: FileActions, root: Path
) -> None:
    result = await _run(actions, "create_folder", None, name="inbox")

    assert (root / "inbox").is_dir()
    assert result.reload_node_id is None


async def test_creating_a_folder_over_a_taken_name_is_refused(
    actions: FileActions,
) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "create_folder", None, name="reports")

    assert caught.value.reason == "conflict"


@pytest.mark.parametrize("name", ["..", "../evil", "/etc", "C:", "a/b", ".", ""])
async def test_a_folder_name_must_be_a_plain_name(
    actions: FileActions, name: str
) -> None:
    """The same rule that judges a path segment, not a second one."""
    with pytest.raises(ValueError):
        await _run(actions, "create_folder", None, name=name)


# --- rename ------------------------------------------------------------------


async def test_renaming_a_file_moves_it_within_its_folder(
    actions: FileActions, root: Path
) -> None:
    result = await _run(actions, "rename", "reports/q3.csv", new_name="q4.csv")

    assert not (root / "reports" / "q3.csv").exists()
    assert (root / "reports" / "q4.csv").read_text(encoding="utf-8").startswith("id,")
    assert result.reload_node_id == "reports"


async def test_renaming_a_folder_keeps_what_is_inside(
    actions: FileActions, root: Path
) -> None:
    await _run(actions, "rename", "reports", new_name="archive")

    assert (root / "archive" / "q3.csv").exists()


async def test_renaming_onto_a_taken_name_is_refused(actions: FileActions) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "rename", "reports", new_name="empty")

    assert caught.value.reason == "conflict"


async def test_renaming_the_root_is_refused(actions: FileActions) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "rename", None, new_name="somewhere")

    assert caught.value.reason == "not_applicable"


@pytest.mark.parametrize("new_name", ["../escaped", "/etc/passwd", "C:", "a/b"])
async def test_a_new_name_cannot_leave_the_folder(
    actions: FileActions, new_name: str
) -> None:
    with pytest.raises(ValueError):
        await _run(actions, "rename", "notes.txt", new_name=new_name)


# --- delete ------------------------------------------------------------------


async def test_deleting_a_file_removes_it(actions: FileActions, root: Path) -> None:
    result = await _run(actions, "delete", "notes.txt")

    assert not (root / "notes.txt").exists()
    assert result.reload_node_id is None


async def test_deleting_an_empty_folder_removes_it(
    actions: FileActions, root: Path
) -> None:
    await _run(actions, "delete", "empty")

    assert not (root / "empty").exists()


async def test_deleting_a_folder_with_files_needs_saying_so(
    actions: FileActions, root: Path
) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "delete", "reports")

    assert caught.value.reason == "conflict"
    assert (root / "reports" / "q3.csv").exists()


async def test_deleting_a_folder_with_files_recursively_removes_it(
    actions: FileActions, root: Path
) -> None:
    await _run(actions, "delete", "reports", recursive=True)

    assert not (root / "reports").exists()


async def test_deleting_the_root_is_refused(actions: FileActions, root: Path) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _run(actions, "delete", None, recursive=True)

    assert caught.value.reason == "not_applicable"
    assert await look(root.is_dir)


async def test_deleting_outside_the_root_is_refused(actions: FileActions) -> None:
    with pytest.raises(ValueError):
        await _run(actions, "delete", "../..")


# --- upload ------------------------------------------------------------------


async def test_uploading_writes_the_file(actions: FileActions, root: Path) -> None:
    result = await _upload(actions, "reports", Upload(b"id,name\n7,seven\n"))

    assert (root / "reports" / "uploaded.csv").read_text(encoding="utf-8") == (
        "id,name\n7,seven\n"
    )
    assert result.reload_node_id == "reports"


async def test_uploading_leaves_no_temporary_file_behind(
    actions: FileActions, root: Path
) -> None:
    await _upload(actions, None, Upload(b"body"))

    leftovers = await look(lambda: [entry.name for entry in root.iterdir()])
    assert [name for name in leftovers if name.startswith(".")] == []


async def test_uploading_over_a_taken_name_is_refused(
    actions: FileActions, root: Path
) -> None:
    with pytest.raises(ActionRefused) as caught:
        await _upload(actions, "reports", Upload(b"new", filename="q3.csv"))

    assert caught.value.reason == "conflict"
    assert (root / "reports" / "q3.csv").read_text(encoding="utf-8") == "id,name\n1,one\n"


async def test_uploading_over_a_taken_name_is_allowed_when_asked(
    actions: FileActions, root: Path
) -> None:
    await _upload(
        actions, "reports", Upload(b"new", filename="q3.csv"), overwrite=True
    )

    assert (root / "reports" / "q3.csv").read_text(encoding="utf-8") == "new"


@pytest.mark.parametrize("filename", ["../evil.txt", "/etc/passwd", "C:evil", "", None])
async def test_the_name_of_an_uploaded_file_is_judged_like_a_path_segment(
    actions: FileActions, filename: str | None
) -> None:
    """The filename comes from the client too, and gets the same rule."""
    with pytest.raises(ValueError):
        await _upload(actions, "reports", Upload(b"body", filename=filename))


async def test_uploading_more_than_the_ceiling_is_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 8)
    actions = FileActions(FileSession(root))

    with pytest.raises(ActionRefused) as caught:
        await _upload(actions, None, Upload(b"x" * 64, filename="big.bin"))

    assert caught.value.reason == "too_large"
    assert not (root / "big.bin").exists()
    assert await look(lambda: list(root.glob(".*"))) == []


async def test_uploading_into_a_file_is_refused(actions: FileActions) -> None:
    with pytest.raises(ValueError):
        await _upload(actions, "notes.txt", Upload(b"body"))
