"""The parts of a declared reference that need no database (D106)."""

import uuid

from app.connectors.declared import (
    DeclaredReference,
    ReferenceEnd,
    end_of,
    fingerprint,
    issued_name,
    other,
    parse_name,
)


def _end(connector: uuid.UUID, node: str, column: str) -> ReferenceEnd:
    return ReferenceEnd(connector_id=connector, node_id=node, column=column)


def test_a_name_issued_here_parses_back_to_its_reference_and_end() -> None:
    reference_id = uuid.uuid4()

    assert parse_name(issued_name(reference_id, "a")) == (reference_id, "a")
    assert parse_name(issued_name(reference_id, "b")) == (reference_id, "b")


def test_a_name_a_source_could_have_issued_is_not_one_of_ours() -> None:
    """The prefix is what makes recognising one a lookup and not a guess."""
    assert parse_name("customers_region_fkey") is None
    assert parse_name(f"declared_{uuid.uuid4()}:a") is None


def test_a_name_that_is_not_a_reference_of_ours_parses_to_nothing() -> None:
    assert parse_name("declared:not-a-uuid:a") is None
    assert parse_name(f"declared:{uuid.uuid4()}") is None
    assert parse_name(f"declared:{uuid.uuid4()}:c") is None


def test_the_pair_is_the_same_whichever_way_round_it_was_drawn() -> None:
    first = _end(uuid.UUID(int=1), "public.regions", "code")
    second = _end(uuid.UUID(int=2), "regions.csv", "code")

    assert fingerprint(first, second) == fingerprint(second, first)


def test_a_different_column_is_a_different_pair() -> None:
    connector = uuid.UUID(int=1)
    other_connector = uuid.UUID(int=2)
    first = _end(connector, "public.regions", "code")

    assert fingerprint(first, _end(other_connector, "regions.csv", "code")) != (
        fingerprint(first, _end(other_connector, "regions.csv", "label"))
    )


def test_the_two_ends_are_read_off_the_row_by_letter() -> None:
    reference = DeclaredReference(
        author_id=uuid.UUID(int=9),
        a_connector_id=uuid.UUID(int=1),
        a_node_id="public.regions",
        a_column="code",
        a_label="regions",
        b_connector_id=uuid.UUID(int=2),
        b_node_id="regions.csv",
        b_column="code",
        b_label="regions.csv",
        fingerprint="x",
    )

    assert end_of(reference, "a").node_id == "public.regions"
    assert end_of(reference, other("a")).node_id == "regions.csv"
    assert end_of(reference, "b").label == "regions.csv"
