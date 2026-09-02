"""Where a statement ends, what it is and what it names — with no files.

The dialect module opens nothing, so every awkward form is tested here: a
semicolon inside a string, a comment between statements, a CTE that looks like
a table, and each family that is refused before a run is recorded (D77).
"""

from app.adapters.file import dialect
from app.adapters.file.dialect import prepare, shape_of


def test_a_semicolon_inside_a_string_is_not_a_boundary() -> None:
    script = prepare("SELECT ';' AS a; SELECT 2")

    assert len(script.statements) == 2
    assert script.statements[0].text == "SELECT ';' AS a"
    assert script.statements[1].text == "SELECT 2"


def test_a_comment_between_statements_belongs_to_the_one_after_it() -> None:
    script = prepare("SELECT 1;\n\n-- why\nSELECT 2;\n")

    first, second = script.statements
    assert (first.start, first.end) == (0, 8)
    assert script.statements[1].text.startswith("-- why")
    assert second.end == len("SELECT 1;\n\n-- why\nSELECT 2;\n")


def test_ranges_survive_a_statement_the_engine_rewrites() -> None:
    """`PRAGMA` comes back as the query it stands for, not as the text sent.

    The offsets after it must still point at the text a person is looking at,
    so the unfound statement takes the gap rather than shifting everything.
    """
    text = "PRAGMA version; SELECT 1"

    first, second = prepare(text).statements

    assert (first.start, first.end) == (0, 15)
    assert text[second.start : second.end] == " SELECT 1"


def test_a_read_is_a_read() -> None:
    statement = prepare('SELECT * FROM "sales.csv"').statements[0]

    assert statement.kind == "read"
    assert statement.refused is None
    assert statement.targets == ["sales.csv"]


def test_each_family_is_refused_by_name() -> None:
    families = {
        'DELETE FROM "sales.csv"': "dml",
        "CREATE TABLE t (a int)": "ddl",
        "COPY (SELECT 1) TO 'x.csv'": "copy",
        "BEGIN": "transaction",
        "SET threads=1": "session",
        "ATTACH 'other.db'": "session",
        "INSTALL httpfs": "session",
        "EXPLAIN SELECT 1": "explain",
    }
    for text, kind in families.items():
        statement = prepare(text).statements[0]
        assert statement.kind == kind, text
        assert statement.refused == dialect.REFUSALS[kind], text


def test_a_table_function_is_refused_whatever_it_is_called() -> None:
    for text in [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM glob('/etc/*')",
        "SELECT * FROM range(10)",
        "SELECT * FROM sniff_csv('x.csv')",
    ]:
        assert prepare(text).statements[0].refused == dialect.TABLE_FUNCTION, text


def test_a_qualified_name_is_refused() -> None:
    for text in [
        'SELECT * FROM main."sales.csv"',
        'SELECT * FROM memory.main."sales.csv"',
        "SELECT * FROM information_schema.tables",
    ]:
        assert prepare(text).statements[0].refused == dialect.QUALIFIED, text


def test_text_that_does_not_parse_is_one_unknown_statement() -> None:
    script = prepare("SELEC 1")

    statement = script.statements[0]
    assert statement.kind == "unknown"
    assert (statement.start, statement.end) == (0, len("SELEC 1"))
    assert statement.refused == dialect.REFUSALS["unknown"]


def test_a_cte_is_not_a_file() -> None:
    """A CTE is written like a table and is defined by the text itself."""
    statement = prepare(
        'WITH recent AS (SELECT * FROM "sales.csv") SELECT * FROM recent'
    ).statements[0]

    assert statement.targets == ["sales.csv"]


def test_a_recursive_cte_is_not_a_file_either() -> None:
    statement = prepare(
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3)"
        " SELECT * FROM r"
    ).statements[0]

    assert statement.targets == []
    assert statement.refused is None


def test_parameters_are_found_in_the_order_they_are_written() -> None:
    script = prepare(
        'SELECT * FROM "sales.csv" WHERE region = $region AND amount > $cutoff'
    )

    assert script.statements[0].parameters == ["region", "cutoff"]
    assert script.parameters == ["region", "cutoff"]


def test_a_script_collects_every_parameter_once() -> None:
    script = prepare("SELECT $a; SELECT $b, $a")

    assert script.parameters == ["a", "b"]


def test_an_unnamed_parameter_is_not_offered_as_a_name() -> None:
    """The engine numbers a `?`, and a number is not a question to answer."""
    assert prepare("SELECT ?").statements[0].parameters == []


def test_several_files_in_one_statement_are_all_named() -> None:
    statement = prepare(
        'SELECT * FROM "a.csv" JOIN "reports/b.parquet" USING (id)'
    ).statements[0]

    assert statement.targets == ["a.csv", "reports/b.parquet"]


def test_a_shape_the_engine_will_not_serialise_is_not_established() -> None:
    assert shape_of("DELETE FROM t").serialised is False
