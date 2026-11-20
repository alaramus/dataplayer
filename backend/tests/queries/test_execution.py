"""What a run is admitted with, before anything is recorded (D62, D206, D383)."""

import pytest

from app.adapters.postgres.statements import prepare
from app.adapters.sqlite.statements import prepare as prepare_sqlite
from app.queries.execution import RunRefused, admit, limits
from app.queries.write_access import NEEDED

BOUNDS = limits(statement_timeout_seconds=30)


def test_an_unclassified_statement_is_refused_where_the_source_does_not_run_one() -> None:
    with pytest.raises(RunRefused) as refused:
        admit(prepare_sqlite("pragma foo"), BOUNDS, mode="auto_commit")

    assert "could not establish" in refused.value.message


def test_an_unclassified_statement_is_admitted_alone_where_the_source_runs_one() -> None:
    admitted = admit(
        prepare("do $$begin perform 1; end$$"),
        BOUNDS,
        mode="auto_commit",
        unclassified=True,
    )

    assert admitted == [(0, "unknown")]


@pytest.mark.parametrize(
    ("text", "mode", "says"),
    [
        ("call p(); select 1", "auto_commit", "on its own"),
        ("call p()", "manual", "outside a transaction"),
        ("call p()", "read", "this run is a read"),
    ],
)
def test_an_unclassified_statement_runs_nowhere_but_alone_in_auto_commit(
    text: str, mode: str, says: str
) -> None:
    with pytest.raises(RunRefused) as refused:
        admit(prepare(text), BOUNDS, scope="script", mode=mode, unclassified=True)

    assert says in refused.value.message


def test_an_unclassified_statement_needs_the_most_a_grant_gives() -> None:
    assert NEEDED["unknown"] == "own"
