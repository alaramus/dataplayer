import os
from pathlib import Path

import pytest

from app.adapters.file.session import FileSession


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("a,b\n1,2\n")
    return tmp_path


def test_no_node_id_means_the_root(root: Path) -> None:
    session = FileSession(root)

    assert session.resolve(None) == root


def test_a_node_id_is_a_path_inside_the_root(root: Path) -> None:
    session = FileSession(root)

    assert session.resolve("reports/q3.csv") == root / "reports" / "q3.csv"


@pytest.mark.parametrize(
    "node_id",
    ["..", "../secrets", "reports/../../secrets", "/etc/passwd", "C:/Windows"],
)
def test_a_path_leaving_the_root_is_refused(root: Path, node_id: str) -> None:
    session = FileSession(root)

    with pytest.raises(ValueError):
        session.resolve(node_id)


def test_the_refusal_does_not_name_the_server_path(root: Path) -> None:
    """Error text is what the user sees; the server layout is not theirs."""
    session = FileSession(root)

    with pytest.raises(ValueError) as raised:
        session.resolve("../secrets")

    assert str(root) not in str(raised.value)


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
def test_a_symlink_out_of_the_root_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (root / "escape").symlink_to(outside)
    session = FileSession(root)

    with pytest.raises(ValueError):
        session.resolve("escape")


async def test_check_reports_a_readable_root(root: Path) -> None:
    session = FileSession(root)

    result = await session.check()

    assert result.ok is True


async def test_check_reports_a_missing_root(tmp_path: Path) -> None:
    session = FileSession(tmp_path / "not-there")

    result = await session.check()

    assert result.ok is False
    assert result.error_kind == "config"
