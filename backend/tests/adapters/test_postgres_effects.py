"""Which nodes a structure change was about.

No database: this is the part of invalidation that is pure. What matters here
is that a client never has to work a node id out of the SQL it sent, and that
where the statement does not say enough the answer widens instead of guessing
(D66).
"""

import pytest

from app.adapters.postgres.effects import effect_of

PATH = ["demo_lab", "public"]


def test_a_new_table_changes_what_its_schema_holds() -> None:
    effect = effect_of("create table demo_lab.t (a int)", search_path=PATH)

    assert effect.scope == "nodes"
    assert effect.reload_node_ids == ["demo_lab"]
    assert effect.relation_node_ids == ["demo_lab.t"]


def test_a_created_table_does_not_claim_the_tables_it_read_from_changed() -> None:
    """`CREATE TABLE a AS SELECT ... FROM b` is about a, and only a."""
    effect = effect_of(
        "create table demo_lab.a as select * from other.b", search_path=PATH
    )

    assert effect.reload_node_ids == ["demo_lab"]
    assert effect.relation_node_ids == ["demo_lab.a"]


def test_an_unqualified_name_names_every_schema_it_could_be_in() -> None:
    """A superset is safe; a subset would leave a stale screen behind."""
    effect = effect_of("drop table t", search_path=PATH)

    assert effect.reload_node_ids == ["demo_lab", "public"]
    assert effect.relation_node_ids == ["demo_lab.t", "public.t"]


def test_a_new_schema_changes_the_root() -> None:
    assert effect_of("create schema s", search_path=PATH).reload_node_ids == [None]
    assert effect_of("drop schema s cascade", search_path=PATH).reload_node_ids == [None]


def test_a_rename_names_the_old_node_and_the_new_one() -> None:
    effect = effect_of("alter table demo_lab.t rename to u", search_path=PATH)

    assert effect.relation_node_ids == ["demo_lab.t", "demo_lab.u", "public.u"]


def test_a_created_index_names_the_relation_it_is_on() -> None:
    effect = effect_of("create index i on demo_lab.t (a)", search_path=PATH)

    assert effect.relation_node_ids == ["demo_lab.t"]
    assert effect.reload_node_ids == []


def test_a_dropped_index_does_not_say_which_relation_it_was_on() -> None:
    """The honest answer is the whole connection, not a node worked out (D66)."""
    effect = effect_of("drop index demo_lab.i", search_path=PATH)

    assert effect.scope == "connection"


def test_a_comment_on_a_column_names_its_relation() -> None:
    effect = effect_of("comment on column demo_lab.t.a is 'x'", search_path=PATH)

    assert effect.relation_node_ids == ["demo_lab.t"]


def test_truncating_names_the_relation() -> None:
    assert effect_of("truncate demo_lab.t", search_path=PATH).relation_node_ids == [
        "demo_lab.t"
    ]


def test_a_statement_that_cannot_be_read_widens_rather_than_guesses() -> None:
    assert effect_of("¡not sql at all!", search_path=PATH).scope == "connection"


def test_an_unqualified_name_with_no_context_widens() -> None:
    """Nothing to resolve against is not the same as nothing changing."""
    assert effect_of("drop table t", search_path=[]).scope == "connection"


@pytest.mark.parametrize(
    "sql",
    ["alter table demo_lab.t add column a int", "comment on table demo_lab.t is 'x'"],
)
def test_changing_a_relation_names_the_relation(sql: str) -> None:
    assert "demo_lab.t" in effect_of(sql, search_path=PATH).relation_node_ids


def test_two_changes_commit_as_one_answer() -> None:
    """A transaction commits together, so what it changed is one list."""
    first = effect_of("create table demo_lab.a (x int)", search_path=PATH)
    second = effect_of("create table demo_lab.b (x int)", search_path=PATH)

    both = first.with_(second)

    assert both.reload_node_ids == ["demo_lab"]
    assert both.relation_node_ids == ["demo_lab.a", "demo_lab.b"]


def test_one_inexact_statement_makes_the_whole_answer_inexact() -> None:
    exact = effect_of("create table demo_lab.a (x int)", search_path=PATH)
    vague = effect_of("drop index demo_lab.i", search_path=PATH)

    assert exact.with_(vague).scope == "connection"
