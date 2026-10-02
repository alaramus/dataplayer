"""What a hit says it was found by: text in segments, never offsets (D198)."""

from app.search.excerpts import ELLIPSIS, segments


def _marked(text: str, *words: str) -> list[tuple[str, bool]]:
    return [(one.text, one.hit) for one in segments(text, words)]


def test_every_word_is_marked_where_it_occurs() -> None:
    assert _marked("orders_2024.csv", "2024", "orders") == [
        ("orders", True),
        ("_", False),
        ("2024", True),
        (".csv", False),
    ]


def test_an_emoji_before_the_hit_does_not_move_the_mark() -> None:
    """A UTF-16 offset would mark the wrong letters after it; text cannot."""
    assert _marked("🐘 elephant 🐘 auth", "auth") == [
        ("🐘 elephant 🐘 ", False),
        ("auth", True),
    ]


def test_a_folding_that_changes_length_marks_the_letters_typed() -> None:
    # `ß` folds to `ss`, so positions in the folded text are not the
    # original's.
    assert _marked("Große Straße", "strasse") == [("Große ", False), ("Straße", True)]


def test_a_long_text_is_cut_around_the_first_hit_within_the_limit() -> None:
    text = "x " * 300 + "the timeout happened here " + "y " * 300

    cut = segments(text, ["timeout"])

    shown = "".join(one.text for one in cut)
    assert len(shown) <= 200
    assert shown.startswith(ELLIPSIS) and shown.endswith(ELLIPSIS)
    assert [one.text for one in cut if one.hit] == ["timeout"]


def test_neighbouring_hits_are_one_segment() -> None:
    assert _marked("pg_class", "pg_", "class") == [("pg_class", True)]
