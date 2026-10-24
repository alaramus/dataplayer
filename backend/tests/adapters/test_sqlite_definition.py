"""Reading what a CREATE TABLE text says that the pragmas do not (D249)."""

from app.adapters.sqlite.definition import index_predicate, read_table, tokenize


def test_names_strings_and_comments_are_single_tokens() -> None:
    tokens = tokenize(
        'a "b ""c""" [d e] `f``g` ' + "'h, (i)' -- j, k\n" + "/* l, ( */ x'00' 1.5e3"
    )

    assert [(token.kind, token.value) for token in tokens] == [
        ("word", "A"),
        ("name", 'b "c"'),
        ("name", "d e"),
        ("name", "f`g"),
        ("string", "'h, (i)'"),
        ("other", "x'00'"),
        ("number", "1.5e3"),
    ]


def test_a_check_keeps_its_own_text_with_commas_and_parentheses() -> None:
    table = read_table(
        """CREATE TABLE t (
          a TEXT CHECK (a IN ('x, y', '(z)')),
          b INT, CONSTRAINT "b is small" CHECK (b < max(1, 2))
        )"""
    )

    assert [(check.name, check.expression) for check in table.checks] == [
        (None, "a IN ('x, y', '(z)')"),
        ("b is small", "b < max(1, 2)"),
    ]


def test_column_clauses_are_read_in_any_order() -> None:
    table = read_table(
        """CREATE TABLE t (
          id INTEGER CONSTRAINT pk PRIMARY KEY ASC AUTOINCREMENT,
          name VARCHAR(20) NOT NULL DEFAULT ('a,b') COLLATE NOCASE UNIQUE,
          total AS (id * 2) VIRTUAL,
          other_id INT REFERENCES other (id) ON DELETE SET NULL CONSTRAINT checked CHECK (other_id > 0)
        )"""
    )

    assert table.primary_key is not None
    assert (table.primary_key.name, table.primary_key.columns) == ("pk", ["id"])
    assert table.columns["name"].collation == "NOCASE"
    assert [key.columns for key in table.unique] == [["name"]]
    assert table.columns["total"].generated == "id * 2"
    assert [(key.columns, key.target) for key in table.foreign] == [(["other_id"], "other")]
    assert [(check.name, check.expression) for check in table.checks] == [
        ("checked", "other_id > 0")
    ]


def test_table_keys_are_read_with_their_names() -> None:
    table = read_table(
        """CREATE TABLE t (a, b, c,
          CONSTRAINT both_ PRIMARY KEY (a DESC, b COLLATE NOCASE),
          UNIQUE (c),
          CONSTRAINT out FOREIGN KEY (b, c) REFERENCES "far table" (x, y)
        ) WITHOUT ROWID"""
    )

    assert table.primary_key is not None
    assert (table.primary_key.name, table.primary_key.columns) == ("both_", ["a", "b"])
    assert [(key.name, key.columns) for key in table.unique] == [(None, ["c"])]
    assert [(key.name, key.columns, key.target) for key in table.foreign] == [
        ("out", ["b", "c"], "far table")
    ]


def test_what_cannot_be_read_says_nothing_rather_than_failing() -> None:
    assert read_table(None).checks == []
    assert read_table("CREATE TABLE t AS SELECT 1").columns == {}
    assert read_table("CREATE TABLE t (a CHECK (").checks[0].expression == ""
    assert read_table("garbage ) ( , ,").checks == []


def test_a_partial_index_gives_its_condition() -> None:
    assert index_predicate("CREATE INDEX i ON t (a) WHERE a > 0 AND (b = 'WHERE')") == (
        "a > 0 AND (b = 'WHERE')"
    )
    assert index_predicate("CREATE INDEX i ON t (coalesce(a, 'x'))") is None
