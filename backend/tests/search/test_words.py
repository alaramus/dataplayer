"""The one rule for how a name matches the words (D202)."""

import pytest

from app.adapters.search import MatchClass, class_of_name, words_of
from tests.utils.word_cases import CASES


@pytest.mark.parametrize(("typed", "name", "expected"), CASES)
def test_a_name_is_classed_by_the_one_table(
    typed: str, name: str, expected: MatchClass | None
) -> None:
    assert class_of_name(words_of(typed), name) == expected


def test_words_are_split_on_white_space_folded_and_kept_once() -> None:
    assert words_of("  Orders\t2024  ORDERS ") == ("orders", "2024")


def test_nothing_typed_matches_nothing() -> None:
    assert class_of_name(words_of("   "), "orders") is None
