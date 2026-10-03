"""Which cells an answer asks, which it does not, and why (D200, D203).

Pure: everything it decides on is in its arguments, nothing is asked of a
server to plan, so a dead server cannot hold the plan.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.search.models import (
    Cell,
    Cost,
    Group,
    Outcome,
    PlannedCell,
    ProviderKey,
    SearchMode,
    SkipReason,
    cell_key,
)

# The fixed order of the groups (D202). Connections, then one group per
# connection in the order they are asked, then the application's own kinds.
# Open tabs stand first from S9. What was opened lately is the whole of an
# empty search and is never planned beside the others (S6).
OPEN_TABS_RANK = 0
RECENT_RANK = 5
CONNECTIONS_RANK = 10
CONNECTION_GROUPS_RANK = 1000
PROVIDER_RANKS: dict[ProviderKey, int] = {
    "open_tabs": OPEN_TABS_RANK,
    "recent": RECENT_RANK,
    "saved_queries": 100_000,
    "pipelines": 100_100,
    "dashboards": 100_200,
    "conversations": 100_300,
    "services": 100_400,
    "ssh_keys": 100_500,
    "guide": 100_600,
    "source_types": 100_700,
}


@dataclass(frozen=True)
class Candidate:
    """A cell that could be asked, and what is already known about it."""

    cell: Cell
    cost: Cost
    group: Group
    connector_id: uuid.UUID | None = None
    in_context: bool = False
    # Decided before any mode is applied: a connection switched off, one whose
    # type cannot search, one the health monitor last saw down.
    blocked: SkipReason | None = None
    since: datetime | None = None
    owned: bool = False
    # Where a connection stands in the order connections are asked in.
    order: int = 0


@dataclass(frozen=True)
class Planned:
    cell: PlannedCell
    # Set when the cell is not asked: its outcome is already known.
    skipped: Outcome | None = None


def plan(
    candidates: Sequence[Candidate],
    *,
    mode: SearchMode,
    insist: bool,
    max_connections: int,
) -> list[Planned]:
    """Every candidate, asked or skipped with its reason.

    Typing asks instant cells everywhere and cheap cells of the connections in
    context only; Search asks instant, cheap and costly, but no more than
    `max_connections` connections, in the order given, the rest `not asked`.
    A job is never planned: contents are looked inside on request (S7).
    `insist` is a person naming these places and saying ask them anyway,
    whatever their health or the ceiling; what the mode spends still holds.
    """
    planned: list[Planned] = []
    asked_connections: list[uuid.UUID] = []
    for candidate in sorted(
        (one for one in candidates if one.cost != "job"),
        key=lambda one: (one.group.rank, one.order),
    ):
        reason = _reason(candidate, mode=mode, insist=insist)
        if (
            reason is None
            and candidate.connector_id is not None
            and not insist
            and candidate.connector_id not in asked_connections
        ):
            if len(asked_connections) >= max_connections:
                reason = "not_asked"
            else:
                asked_connections.append(candidate.connector_id)
        planned.append(
            Planned(
                cell=PlannedCell(
                    key=cell_key(candidate.cell),
                    cell=candidate.cell,
                    group=candidate.group,
                    cost=candidate.cost,
                    way="none" if reason is not None else "live",
                    connector_id=candidate.connector_id,
                ),
                skipped=None
                if reason is None
                else Outcome(
                    way="none",
                    status="skipped",
                    reason=reason,
                    since=candidate.since if reason == "unreachable" else None,
                ),
            )
        )
    return planned


def _reason(candidate: Candidate, *, mode: SearchMode, insist: bool) -> SkipReason | None:
    if candidate.blocked in ("switched_off", "cannot_search"):
        return candidate.blocked
    if candidate.blocked is not None and not insist:
        return candidate.blocked
    # Insisting names a place, not a mode: a keystroke never decrypts a
    # library or walks a remote tree, whatever the request says (D200, D204).
    if mode == "typing":
        if candidate.cost == "costly":
            return "too_costly"
        if (
            candidate.cost == "cheap"
            and candidate.connector_id is not None
            and not candidate.in_context
        ):
            return "not_in_context"
    return None
