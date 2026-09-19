"""Local copies of remote files: fetched once, bounded, and never taken from a reader (D152)."""

from pathlib import Path

import pytest

from app.adapters.explorer.copies import Copies, TooLargeToCopy


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Remote:
    """What a storage would fetch: the bytes of each version, and how often."""

    def __init__(self) -> None:
        self.fetched: list[str] = []

    def fetcher(self, content: bytes, label: str):  # type: ignore[no-untyped-def]  # a test double
        def fetch(target: Path) -> None:
            self.fetched.append(label)
            target.write_bytes(content)

        return fetch


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def copies(tmp_path: Path, clock: _Clock) -> Copies:
    held = Copies(
        tmp_path / "copies", largest_bytes=10, capacity_bytes=16, idle_seconds=60, clock=clock
    )
    held.clear()
    return held


def test_a_version_is_fetched_once_and_carries_the_files_own_name(copies: Copies) -> None:
    remote = _Remote()

    with copies.held("server", "logs/a.csv", "a.csv", "v1", 3, remote.fetcher(b"one", "v1")) as first:
        assert first.name == "a.csv"
        assert first.read_bytes() == b"one"
    with copies.held("server", "logs/a.csv", "a.csv", "v1", 3, remote.fetcher(b"one", "v1")) as again:
        assert again == first

    assert remote.fetched == ["v1"]


def test_a_new_version_is_fetched_beside_the_one_being_read(copies: Copies) -> None:
    remote = _Remote()

    with copies.held("server", "a.csv", "a.csv", "v1", 3, remote.fetcher(b"one", "v1")) as old:
        with copies.held("server", "a.csv", "a.csv", "v2", 3, remote.fetcher(b"two", "v2")) as new:
            assert new != old
            assert new.read_bytes() == b"two"
        assert old.read_bytes() == b"one"

    assert remote.fetched == ["v1", "v2"]


def test_a_file_larger_than_a_copy_may_be_is_not_fetched(copies: Copies) -> None:
    remote = _Remote()

    with pytest.raises(TooLargeToCopy, match="download it"):
        with copies.held("server", "big.bin", "big.bin", "v1", 11, remote.fetcher(b"", "big")):
            pass

    assert remote.fetched == []


def test_the_oldest_copies_go_once_the_capacity_is_passed(copies: Copies, clock: _Clock) -> None:
    remote = _Remote()
    paths = []
    for index in range(3):
        clock.now = index
        with copies.held(
            "server", f"f{index}", f"f{index}", "v1", 8, remote.fetcher(b"x" * 8, f"f{index}")
        ) as path:
            paths.append(path)

    # Sixteen bytes hold two of the three; the one read longest ago went.
    assert [path.exists() for path in paths] == [False, True, True]


def test_a_copy_being_read_is_never_taken_away(copies: Copies, clock: _Clock) -> None:
    remote = _Remote()

    with copies.held("server", "kept", "kept", "v1", 8, remote.fetcher(b"x" * 8, "kept")) as kept:
        clock.now = 1000
        for index in range(3):
            with copies.held(
                "server", f"f{index}", f"f{index}", "v1", 8, remote.fetcher(b"y" * 8, "other")
            ):
                pass
        assert kept.exists()


def test_a_copy_nobody_has_read_for_an_hour_goes(copies: Copies, clock: _Clock) -> None:
    remote = _Remote()
    with copies.held("server", "old", "old", "v1", 2, remote.fetcher(b"ab", "old")) as old:
        pass

    clock.now = 61
    with copies.held("server", "new", "new", "v1", 2, remote.fetcher(b"cd", "new")):
        pass

    assert not old.exists()


def test_a_failed_fetch_leaves_nothing_and_is_tried_again(copies: Copies) -> None:
    def broken(target: Path) -> None:
        target.write_bytes(b"ha")
        raise OSError("connection lost")

    with pytest.raises(OSError, match="connection lost"):
        with copies.held("server", "a", "a", "v1", 2, broken):
            pass
    remote = _Remote()
    with copies.held("server", "a", "a", "v1", 2, remote.fetcher(b"ok", "again")) as path:
        assert path.read_bytes() == b"ok"

    assert remote.fetched == ["again"]
    assert not list(path.parent.glob("*.part"))


def test_a_scratch_folder_goes_with_its_block(copies: Copies) -> None:
    with copies.scratch("server") as folder:
        (folder / "staged").write_bytes(b"x")

    assert not folder.exists()


def test_clearing_takes_everything_a_previous_process_left(copies: Copies) -> None:
    leftover = copies.root / "somebody" / "stale.bin"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x")

    copies.clear()

    assert list(copies.root.iterdir()) == []
