"""Which cells an answer asks, and why it leaves the others (D200)."""

import uuid
from datetime import UTC, datetime

from app.search.models import (
    Cell,
    ConnectionPlace,
    Cost,
    Group,
    ObjectsPlace,
    SearchMode,
    SkipReason,
)
from app.search.plan import CONNECTION_GROUPS_RANK, Candidate, plan


def _object(cost: Cost = "instant") -> Candidate:
    return Candidate(
        cell=Cell(place=ObjectsPlace(provider="guide"), field="names"),
        cost=cost,
        group=Group(key="objects:guide", title="Guide", rank=100_600),
    )


def _connection(
    index: int,
    cost: Cost = "cheap",
    *,
    in_context: bool = False,
    blocked: SkipReason | None = None,
) -> Candidate:
    connector_id = uuid.uuid4()
    return Candidate(
        cell=Cell(place=ConnectionPlace(connector_id=connector_id), field="names"),
        cost=cost,
        group=Group(
            key=f"connection:{connector_id}",
            title=f"c{index}",
            rank=CONNECTION_GROUPS_RANK + index,
        ),
        connector_id=connector_id,
        in_context=in_context,
        blocked=blocked,
        since=datetime(2026, 10, 2, 14, 2, tzinfo=UTC) if blocked == "unreachable" else None,
        order=index,
    )


def _reasons(
    candidates: list[Candidate],
    mode: SearchMode = "search",
    *,
    insist: bool = False,
    max_connections: int = 20,
) -> list[SkipReason | None]:
    return [
        None if one.skipped is None else one.skipped.reason
        for one in plan(candidates, mode=mode, insist=insist, max_connections=max_connections)
    ]


def test_typing_asks_instant_cells_and_cheap_ones_in_context_only() -> None:
    near = _connection(0, in_context=True)
    far = _connection(1)
    large = _connection(2, "costly", in_context=True)

    # In the fixed order of the groups: connections before the guide.
    assert _reasons([_object(), near, far, large], "typing") == [
        None,
        "not_in_context",
        "too_costly",
        None,
    ]


def test_search_asks_everything_up_to_the_ceiling_in_the_order_given() -> None:
    candidates = [_connection(index) for index in range(4)]

    assert _reasons(candidates, max_connections=2) == [None, None, "not_asked", "not_asked"]


def test_a_place_that_cannot_be_asked_does_not_count_towards_the_ceiling() -> None:
    off = _connection(0, blocked="switched_off")
    mute = _connection(1, blocked="cannot_search")
    on = _connection(2)

    assert _reasons([off, mute, on], max_connections=1) == [
        "switched_off",
        "cannot_search",
        None,
    ]


def test_an_unreachable_connection_is_skipped_with_when_unless_insisted_on() -> None:
    down = _connection(0, blocked="unreachable")

    [skipped] = plan([down], mode="search", insist=False, max_connections=20)
    [insisted] = plan([down], mode="search", insist=True, max_connections=20)

    assert skipped.skipped is not None
    assert skipped.skipped.reason == "unreachable"
    assert skipped.skipped.since is not None
    assert skipped.cell.way == "none"
    assert insisted.skipped is None
    assert insisted.cell.way == "live"


def test_insisting_never_asks_a_connection_that_is_off() -> None:
    assert _reasons([_connection(0, blocked="switched_off")], insist=True) == ["switched_off"]


def test_a_job_is_never_planned() -> None:
    assert plan([_object("job")], mode="search", insist=False, max_connections=20) == []
