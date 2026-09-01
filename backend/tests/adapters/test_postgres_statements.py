"""Where statements end, and what they are.

No database: this is the part of preparation that is pure, and the awkward
forms — quoting, comments, dollar bodies, writable CTEs — are exactly what a
home-grown splitter gets wrong (D62).
"""

import logging

import pytest

from app.adapters.postgres.statements import bind, prepare, split
from app.adapters.query import StatementClass


def kinds(text: str) -> list[StatementClass]:
    return [statement.kind for statement in prepare(text).statements]


def texts(text: str) -> list[str]:
    return [statement.text for statement in prepare(text).statements]


def test_a_semicolon_inside_a_string_does_not_end_a_statement() -> None:
    text = "select 'a;b' as x; select 2"

    assert texts(text) == ["select 'a;b' as x", "select 2"]


def test_a_semicolon_inside_a_quoted_identifier_does_not_end_a_statement() -> None:
    assert texts('select 1 as "odd;name"') == ['select 1 as "odd;name"']


def test_a_semicolon_inside_a_comment_does_not_end_a_statement() -> None:
    text = "select 1 -- ; not the end\n; select 2 /* ; */"

    assert kinds(text) == ["read", "read"]


def test_a_dollar_quoted_body_is_one_statement() -> None:
    text = "do $$ begin raise notice 'x;y'; end $$; select 1"

    assert texts(text) == ["do $$ begin raise notice 'x;y'; end $$", "select 1"]
    assert kinds(text) == ["unknown", "read"]


def test_empty_pieces_between_semicolons_are_not_statements() -> None:
    assert kinds(";;select 1;;") == ["read"]
    assert split("") == []
    assert split("   \n  ") == []


def test_a_range_points_back_into_the_text_it_came_from() -> None:
    text = "select 1;\nselect 2"

    second = prepare(text).statements[1]

    assert text[second.start : second.end] == "select 2"


@pytest.mark.parametrize(
    ("sql", "kind"),
    [
        ("select 1", "read"),
        ("select * from t where a = 1", "read"),
        ("with recent as (select 1) select * from recent", "read"),
        ("values (1), (2)", "read"),
        ("select 1 union select 2", "read"),
        ("insert into t values (1)", "dml"),
        ("update t set a = 1", "dml"),
        ("delete from t", "dml"),
        ("merge into t using s on t.id = s.id when matched then update set a = 1", "dml"),
        ("create table t (a int)", "ddl"),
        ("drop table t", "ddl"),
        ("alter table t add column a int", "ddl"),
        ("truncate t", "ddl"),
        ("comment on table t is 'x'", "ddl"),
        ("begin", "transaction"),
        ("start transaction", "transaction"),
        ("commit", "transaction"),
        ("rollback", "transaction"),
        ("savepoint s1", "transaction"),
        ("set search_path to public", "session"),
        ("reset all", "session"),
        ("discard all", "session"),
        ("listen c", "session"),
        ("prepare p as select 1", "session"),
        ("copy t from stdin", "copy"),
        ("copy (select 1) to stdout", "copy"),
        ("explain select 1", "explain"),
        ("vacuum", "unknown"),
        ("call p()", "unknown"),
        ("refresh materialized view mv", "unknown"),
    ],
)
def test_the_class_of_one_statement(sql: str, kind: StatementClass) -> None:
    assert kinds(sql) == [kind]


@pytest.mark.parametrize(
    "sql",
    [
        "with moved as (insert into t values (1) returning *) select * from moved",
        "with gone as (delete from t returning *) select * from gone",
        "with changed as (update t set a = 1 returning *) select * from changed",
    ],
)
def test_a_writable_cte_is_not_a_read(sql: str) -> None:
    """The form a first word lets through, and the reason there is a parser."""
    assert kinds(sql) == ["dml"]


def test_select_into_creates_a_relation_and_is_not_a_read() -> None:
    assert kinds("select * into new_table from t") == ["ddl"]


def test_a_statement_that_does_not_parse_is_unknown_rather_than_a_guess() -> None:
    assert kinds("select from where") == ["unknown"]
    assert kinds("¡not sql at all!") == ["unknown"]


def test_named_parameters_are_found_and_casts_are_not_parameters() -> None:
    script = prepare("select :since::date, :until where a > :since")

    assert script.parameters == ["since", "until"]
    assert script.statements[0].parameters == ["since", "until"]


def test_a_colon_inside_a_string_is_not_a_parameter() -> None:
    assert prepare("select 'a:b' as x").parameters == []


def test_parameters_are_collected_across_a_script_in_order() -> None:
    script = prepare("select :a; select :b, :a")

    assert script.parameters == ["a", "b"]
    assert [statement.parameters for statement in script.statements] == [["a"], ["b", "a"]]


def test_a_statement_names_what_it_reads() -> None:
    assert prepare("select * from public.orders o join people p on true").statements[
        0
    ].targets == ["public.orders", "people"]


def test_unparsable_sql_is_not_written_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D64: SQL never enters application logs, and sqlglot logs what it cannot parse."""
    secret = "select * from salaries where person = 'a-recognisable-name' and"

    with caplog.at_level(logging.DEBUG):
        prepare(secret)

    assert "salaries" not in caplog.text
    assert "a-recognisable-name" not in caplog.text


@pytest.mark.parametrize("name", ["name", "text", "user", "date", "value", "n"])
def test_a_parameter_may_be_called_what_the_dialect_calls_something_else(
    name: str,
) -> None:
    """The tokenizer reads `name` as a keyword; a colon before it still binds."""
    assert prepare(f"select :{name}::text").parameters == [name]


def test_binding_rewrites_only_the_placeholders() -> None:
    assert bind("select :since::date, x from t where a > :since") == (
        "select %(since)s::date, x from t where a > %(since)s"
    )


def test_binding_doubles_a_literal_per_cent_sign() -> None:
    """The driver reads one as a placeholder as soon as anything is bound."""
    assert bind("select 'a%b' like '%' || :middle") == (
        "select 'a%%b' like '%%' || %(middle)s"
    )


def test_binding_leaves_a_cast_alone() -> None:
    assert bind("select a::text from t") == "select a::text from t"
