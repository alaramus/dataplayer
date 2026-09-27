"""What a copy of tables takes from a source's catalog as one expression (D182)."""

import pytest

from app.adapters.table_copy import is_one_fragment


@pytest.mark.parametrize(
    "text",
    [
        "(balance >= (0)::numeric)",
        "CHECK ((VALUE <> ''::text))",
        "'it''s'::text",
        "PRIMARY KEY (id) INCLUDE (name)",
        "btree (lower((email)::text)) WHERE (active IS TRUE)",
        '"Odd; name"',
        "'semi; colon -- and /* comment */'::text",
    ],
)
def test_one_expression_is_taken(text: str) -> None:
    assert is_one_fragment(text)


@pytest.mark.parametrize(
    "text",
    [
        "0); DROP TABLE people; --",
        "true) OR (1 = 1",
        "(1 = 1",
        "1 = 1 -- the rest is a comment",
        "1 /* a comment */",
        "'unterminated",
        '"unterminated',
        "$$body$$",
        "",
        "   ",
    ],
)
def test_anything_that_could_end_the_statement_is_not(text: str) -> None:
    assert not is_one_fragment(text)
