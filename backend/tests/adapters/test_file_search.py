import time
from pathlib import Path
from typing import cast

import pytest

from app.adapters.explorer import search as search_module
from app.adapters.explorer.search import ExplorerSearch
from app.adapters.explorer.storage import (
    LOCAL_SEARCH,
    ROOT,
    Entry,
    Place,
    SearchLimits,
    Storage,
)
from app.adapters.file.adapter import FileAdapter
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError, ErrorKind, NodeNotFound
from app.adapters.search import (
    DEFAULT_MATCHES,
    MAX_EXCERPT_CHARACTERS,
    LastSearch,
    MatchClass,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
)
from app.adapters.ssh.adapter import SshAdapter
from tests.utils.word_cases import CASES


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "notes.txt").write_text("top\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3-notes.md").write_text("# q3\n", encoding="utf-8")
    (tmp_path / "reports" / "q4.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "reports" / "drafts").mkdir()
    (tmp_path / "reports" / "drafts" / "NOTES.rst").write_text("x\n", encoding="utf-8")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "old.txt").write_text("old\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def search(root: Path) -> ExplorerSearch:
    return ExplorerSearch(LocalStorage(root))


async def _find(
    search: ExplorerSearch,
    query: str,
    *,
    node_id: str | None = None,
    limit: int = DEFAULT_MATCHES,
) -> NodeSearchResult:
    return await search.search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit)
    )


async def test_a_name_is_matched_anywhere_below_the_level_the_best_first(
    search: ExplorerSearch,
) -> None:
    """By class, then by nearness: two names that begin with the word, then
    one where it only begins a word (D202)."""
    found = await _find(search, "notes")

    assert [match.node.name for match in found.matches] == [
        "notes.txt",
        "NOTES.rst",
        "q3-notes.md",
    ]
    assert found.complete is True
    assert found.notice is None


async def test_the_match_is_case_insensitive_and_is_never_a_pattern(
    search: ExplorerSearch,
) -> None:
    """A person types words, not a language the source compiles."""
    upper = await _find(search, "NOTES")
    pattern = await _find(search, "note*")

    assert len(upper.matches) == 3
    # A star is a character in a name, and no name here holds one.
    assert pattern.matches == []


async def test_what_is_near_is_found_first(search: ExplorerSearch) -> None:
    """Breadth first, so a ceiling cuts the far end rather than a branch."""
    found = await _find(search, "notes", limit=1)

    assert [match.node.name for match in found.matches] == ["notes.txt"]
    assert found.complete is False
    assert found.notice is not None


async def test_a_match_says_where_it_was_found(search: ExplorerSearch) -> None:
    found = await _find(search, "NOTES.rst")

    match = found.matches[0]
    assert match.parent_id == "reports/drafts"
    assert match.location == "reports/drafts"


async def test_a_match_at_the_top_has_no_place_to_name(search: ExplorerSearch) -> None:
    """The root is the connector, and it has no name of its own."""
    found = await _find(search, "notes.txt")

    assert found.matches[0].parent_id is None
    assert found.matches[0].location == ""


async def test_a_search_starts_where_it_was_asked_to(search: ExplorerSearch) -> None:
    found = await _find(search, "notes", node_id="reports")

    assert [match.node.name for match in found.matches] == ["NOTES.rst", "q3-notes.md"]


async def test_a_found_node_is_the_node_the_listing_would_have_shown(
    search: ExplorerSearch,
) -> None:
    """One builder, so a row does not behave differently for being found."""
    found = await _find(search, "q4.csv")

    node = found.matches[0].node
    assert node.kind == "file"
    assert node.id == "reports/q4.csv"
    assert [item.kind for item in node.representations] == ["table"]
    assert node.describable is True
    assert node.summarizable is True


async def test_folders_are_found_as_well_as_files(search: ExplorerSearch) -> None:
    found = await _find(search, "drafts")

    assert [match.node.kind for match in found.matches] == ["directory"]


async def test_a_walk_that_hit_a_ceiling_says_so_rather_than_looking_complete(
    search: ExplorerSearch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_module, "MAX_SCANNED", 1)

    found = await _find(search, "notes")

    assert found.complete is False
    assert found.notice is not None


async def test_a_tree_deeper_than_the_ceiling_is_not_walked(
    search: ExplorerSearch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search_module, "MAX_DEPTH", 1)

    found = await _find(search, "notes")

    # The two levels within reach are answered; the third is not, and the
    # answer says it stopped rather than claiming there was nothing there.
    assert [match.node.name for match in found.matches] == ["notes.txt", "q3-notes.md"]
    assert found.complete is False
    assert found.notice is not None


async def test_an_exact_name_is_not_lost_behind_a_hundred_that_hold_the_word(
    tmp_path: Path,
) -> None:
    """The walk keeps the best classes it has met within its ceilings (D202)."""
    for index in range(150):
        (tmp_path / f"reorders-{index:03}.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "far" / "below").mkdir(parents=True)
    (tmp_path / "far" / "below" / "orders").write_text("x\n", encoding="utf-8")

    found = await _find(ExplorerSearch(LocalStorage(tmp_path)), "orders", limit=100)

    assert found.matches[0].node.name == "orders"
    assert found.matches[0].parent_id == "far/below"
    assert len(found.matches) == 100
    # More matched than were kept, and the answer says so.
    assert found.complete is False
    assert found.notice is not None


async def test_a_walk_out_of_time_stops_and_says_so(search: ExplorerSearch) -> None:
    """Time is the fourth bound, and its notice is the source's own (D76)."""
    found = await search.search_nodes(
        NodeSearchRequest(query="notes"), SearchBounds(deadline=time.monotonic() - 1)
    )

    assert found.matches == []
    assert found.complete is False
    assert found.notice is not None and found.notice.startswith("Time ran out")


async def test_a_walk_stops_when_its_answer_is_gone(search: ExplorerSearch) -> None:
    """Checked between entries, so a newer keystroke ends the older walk."""
    asked: list[bool] = []

    def stopped() -> bool:
        asked.append(True)
        return len(asked) > 1

    found = await search.search_nodes(
        NodeSearchRequest(query="notes"),
        SearchBounds(deadline=time.monotonic() + 60, stopped=stopped),
    )

    assert len(asked) == 2
    assert found.complete is False


class _Named:
    """A folder holding exactly one name, whatever this machine's disk allows.

    Two names of the table differ only by case and two hold a colon, which a
    Windows disk refuses; a server holds them, so the walk is asked about them
    here rather than on the disk.
    """

    search_limits = LOCAL_SEARCH

    def __init__(self, name: str) -> None:
        self._name = name

    def place(self, node_id: str | None) -> Place:
        return ROOT

    def entry(self, place: Place) -> Entry:
        return Entry(place=ROOT, is_directory=True, size_bytes=0, modified_at=None)

    def entries(self, place: Place) -> list[Entry]:
        found = Place(key="found", name=self._name)
        return [Entry(place=found, is_directory=False, size_bytes=1, modified_at=None)]


@pytest.mark.parametrize(("typed", "name", "expected"), CASES)
async def test_the_walk_agrees_with_the_word_table(
    typed: str, name: str, expected: MatchClass | None
) -> None:
    search = ExplorerSearch(cast(Storage, _Named(name)))

    found = await _find(search, typed)

    assert [match.node.name for match in found.matches] == ([name] if expected else [])


async def test_a_search_needs_something_to_look_for(search: ExplorerSearch) -> None:
    with pytest.raises(ValueError):
        await _find(search, "   ")


async def test_a_search_starts_in_a_folder(search: ExplorerSearch) -> None:
    with pytest.raises(ValueError):
        await _find(search, "notes", node_id="notes.txt")


async def test_a_level_that_is_gone_is_not_found(search: ExplorerSearch) -> None:
    with pytest.raises(NodeNotFound):
        await _find(search, "notes", node_id="nowhere")


async def test_a_connector_whose_directory_is_missing_says_that(
    tmp_path: Path,
) -> None:
    search = ExplorerSearch(LocalStorage(tmp_path / "gone"))

    with pytest.raises(AdapterError):
        await _find(search, "notes")


@pytest.mark.parametrize(
    "node_id", ["../secrets", "/etc", "C:/Windows", "reports/../.."]
)
async def test_a_level_outside_the_root_is_refused(
    search: ExplorerSearch, node_id: str
) -> None:
    """The one containment rule, before a single entry is listed (D8)."""
    with pytest.raises(ValueError):
        await _find(search, "notes", node_id=node_id)


async def _look_inside(
    search: ExplorerSearch,
    query: str,
    *,
    node_id: str | None = None,
    limit: int = DEFAULT_MATCHES,
) -> NodeSearchResult:
    return await search.search_contents(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit)
    )


@pytest.fixture
def written(root: Path) -> Path:
    """The same tree, with something worth grepping for inside it."""
    (root / "reports" / "q4.csv").write_text(
        "id,note\n1,upstream timeout after 30s\n2,fine\n", encoding="utf-8"
    )
    (root / "archive" / "old.txt").write_text(
        "nothing of interest here\n", encoding="utf-8"
    )
    (root / "picture.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00timeout\x00")
    return root


async def test_the_words_are_found_inside_a_file_that_is_not_named_for_them(
    written: Path,
) -> None:
    search = ExplorerSearch(LocalStorage(written))

    found = await _look_inside(search, "timeout")

    assert [match.node.name for match in found.matches] == ["q4.csv"]
    # The name search finds nothing at all, which is the whole point of the
    # second gesture.
    by_name = await _find(search, "timeout")
    assert (by_name.matches, by_name.complete, by_name.notice) == ([], True, None)


async def test_a_match_carries_the_line_it_was_found_on(written: Path) -> None:
    search = ExplorerSearch(LocalStorage(written))

    found = await _look_inside(search, "TIMEOUT")

    # Case-insensitive, as the name search is: the same words typed the same
    # way must not mean two different things.
    assert found.matches[0].excerpt == "1,upstream timeout after 30s"


async def test_a_line_longer_than_the_ceiling_is_cut_rather_than_carried(
    written: Path,
) -> None:
    """A log line or a minified document is one line and can be enormous."""
    (written / "wide.txt").write_text("x" * 5000 + "timeout\n", encoding="utf-8")
    search = ExplorerSearch(LocalStorage(written))

    found = await _look_inside(search, "timeout")

    excerpt = next(
        match.excerpt for match in found.matches if match.node.name == "wide.txt"
    )
    assert excerpt is not None
    assert len(excerpt) == MAX_EXCERPT_CHARACTERS


async def test_a_binary_file_is_not_searched_and_the_answer_says_so(
    written: Path,
) -> None:
    search = ExplorerSearch(LocalStorage(written))

    found = await _look_inside(search, "timeout")

    assert [match.node.name for match in found.matches] == ["q4.csv"]
    # The picture holds the word and was never read; "no matches" would have
    # meant "not in this folder", which is not what happened.
    assert found.complete is True
    assert found.notice is not None
    assert "not read" in found.notice


async def test_a_file_larger_than_the_ceiling_is_skipped(written: Path) -> None:
    storage = LocalStorage(written)
    storage.search_limits = SearchLimits(file_bytes=8, total_bytes=LOCAL_SEARCH.total_bytes)
    search = ExplorerSearch(storage)

    found = await _look_inside(search, "timeout")

    assert found.matches == []
    assert found.notice is not None


async def test_a_search_that_read_too_much_stops_rather_than_running_on(written: Path) -> None:
    storage = LocalStorage(written)
    storage.search_limits = SearchLimits(file_bytes=LOCAL_SEARCH.file_bytes, total_bytes=1)
    search = ExplorerSearch(storage)

    found = await _look_inside(search, "timeout")

    assert found.complete is False
    assert found.notice is not None


async def test_a_skipped_file_costs_nothing_of_what_a_search_may_read(tmp_path: Path) -> None:
    """The budget counts bytes read, not the sizes of files walked past.

    The small file is a level down, so the walk passes the large one first.
    """
    (tmp_path / "large.log").write_text("x" * 400 + "\ntimeout\n", encoding="utf-8")
    (tmp_path / "below").mkdir()
    (tmp_path / "below" / "small.log").write_text("upstream timeout\n", encoding="utf-8")
    storage = LocalStorage(tmp_path)
    storage.search_limits = SearchLimits(file_bytes=100, total_bytes=200)
    search = ExplorerSearch(storage)

    found = await _look_inside(search, "timeout")

    assert [match.node.name for match in found.matches] == ["small.log"]
    assert found.complete is True


class _BreaksBelow(LocalStorage):
    """A storage whose source fails when one folder is listed."""

    def __init__(self, root: Path, broken: str, kind: ErrorKind = "network") -> None:
        super().__init__(root)
        self._broken = broken
        self._kind: ErrorKind = kind

    def entries(self, place: Place) -> list[Entry]:
        if place.name == self._broken:
            raise AdapterError(self._kind, "The server closed the connection")
        return super().entries(place)


async def test_a_source_failing_part_way_keeps_what_was_found(root: Path) -> None:
    search = ExplorerSearch(_BreaksBelow(root, "reports"))

    found = await _find(search, "notes")

    # Found at the top before the walk reached the folder that failed.
    assert [match.node.name for match in found.matches] == ["notes.txt"]
    assert found.complete is False
    assert found.notice == "The server closed the connection"
    assert found.error_kind == "network"


async def test_a_locked_key_part_way_says_locked(written: Path) -> None:
    """The kind travels, so the catalog offers the owner the passphrase (D147)."""
    search = ExplorerSearch(_BreaksBelow(written, "archive", kind="locked"))

    found = await _look_inside(search, "timeout")

    assert found.complete is False
    assert found.error_kind == "locked"


async def test_reading_inside_starts_where_it_was_asked_to(written: Path) -> None:
    search = ExplorerSearch(LocalStorage(written))

    found = await _look_inside(search, "timeout", node_id="archive")

    assert found.matches == []


async def test_a_level_outside_the_root_is_refused_when_reading_inside_too(
    written: Path,
) -> None:
    """One containment rule, and the second search goes through it as well."""
    search = ExplorerSearch(LocalStorage(written))

    with pytest.raises(ValueError):
        await _look_inside(search, "timeout", node_id="../secrets")


async def test_a_link_is_listed_where_it_matches_and_never_walked_into(
    search: ExplorerSearch, root: Path
) -> None:
    """An alias can point at its own parent, and a search is where a loop shows."""
    try:
        (root / "loop-notes").symlink_to(root, target_is_directory=True)
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip("This platform will not create a symbolic link here")

    found = await _find(search, "notes")

    names = [match.node.name for match in found.matches]
    assert "loop-notes" in names
    # Walked into, the same three names would arrive again through the alias.
    assert names.count("notes.txt") == 1
    assert found.complete is True


def test_a_walk_by_name_is_cheap_on_this_server_and_costly_over_ssh() -> None:
    """Stated without asking anybody, so a dead server cannot hold a plan (D200)."""
    assert FileAdapter.search_cost("names", None) == "cheap"
    assert SshAdapter.search_cost("names", LastSearch(extent=10)) == "costly"
    assert FileAdapter.search_cost("contents", None) == "costly"
