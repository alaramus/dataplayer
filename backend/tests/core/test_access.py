from typing import get_args

import pytest

from app.core.access import Access, Grant, at_least, ranked


def test_every_level_has_a_rank() -> None:
    # The comparison reads its ranks from one dictionary. A value added to the
    # union without a rank would otherwise be silently unorderable.
    assert set(ranked()) == set(get_args(Access))


def test_the_scale_runs_from_read_to_own() -> None:
    assert ranked() == ("read", "write", "structure", "own")


def test_ownership_is_not_grantable() -> None:
    assert "own" not in get_args(Grant)
    assert set(get_args(Grant)) < set(get_args(Access))


@pytest.mark.parametrize(
    ("held", "required", "expected"),
    [
        ("read", "read", True),
        ("read", "write", False),
        ("write", "read", True),
        ("write", "structure", False),
        ("structure", "write", True),
        ("structure", "own", False),
        ("own", "structure", True),
        ("own", "own", True),
    ],
)
def test_a_level_admits_everything_below_it(
    held: Access, required: Access, expected: bool
) -> None:
    assert at_least(held, required) is expected
