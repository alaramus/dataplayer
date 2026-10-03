"""The agent's `search` tool: the one search, offered less (S10, D199, D135).

The engine decides what is offered: providers by their own `offered_to_agent`,
connections by their owner's transfer flag. What is asked live is decided
here: the connections of the attached tabs and those the model names, never
every connection the person holds. A named one that does not allow transfer
is refused by name and nothing else of it is read.
"""

import uuid
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.search import connections
from app.search.engine import SearchEngine
from app.search.models import (
    MAX_CONTEXT,
    CellLine,
    ConnectionTarget,
    Hit,
    NodeTarget,
    SearchRequest,
)
from app.users.models import User

# What one call hands the model, whatever the cells found.
MAX_HITS = 50

NOTHING_INSIDE = (
    "Only connection names, the guide and source types were searched. Pass "
    "connector_ids, or ask the person to attach a tab, to search inside connections."
)


async def search_for_agent(
    engine: SearchEngine,
    session: AsyncSession,
    user: User,
    *,
    words: str,
    named: Sequence[uuid.UUID],
    attached: Sequence[uuid.UUID],
    refusal: Callable[[uuid.UUID, str, str], dict[str, Any]],
) -> dict[str, Any]:
    """One answer of the engine for the agent, read whole and bounded.

    `refusal` builds D135's refusal from a connection's id, name and the
    person's level, so the refusal is the one every other tool answers with.
    """
    wanted = list(dict.fromkeys([*named, *attached]))
    if len(wanted) > MAX_CONTEXT:
        raise ValueError(f"Search inside at most {MAX_CONTEXT} connections at once")
    visible = {one.id: one for one in await connections.visible(session, user)}
    asked: list[uuid.UUID] = []
    refused: list[dict[str, Any]] = []
    unknown: list[str] = []
    for connector_id in wanted:
        connection = visible.get(connector_id)
        if connection is None:
            unknown.append(str(connector_id))
        elif not connection.allows_transfer:
            refused.append(refusal(connection.id, connection.name, connection.access))
        else:
            asked.append(connector_id)
    try:
        request = SearchRequest(words=words, mode="search", context=asked)
    except ValidationError as invalid:
        # The model's own words would be quoted back in pydantic's text.
        message = str(invalid.errors()[0]["msg"]).removeprefix("Value error, ")
        raise ValueError(message) from None
    answer = await engine.prepare(session, user, request, audience="agent")
    ranks = {one.cell.key: one.cell.group.rank for one in answer.planned}
    places = {one.cell.key: one.cell.group.title for one in answer.planned}
    found: list[tuple[int, int, Hit]] = []
    unanswered: list[dict[str, Any]] = []
    more = False
    async for line in answer.lines():
        if not isinstance(line, CellLine):
            continue
        rank = ranks.get(line.key, 0)
        found.extend((rank, len(found), hit) for hit in line.hits)
        more = more or line.outcome.more
        outcome = line.outcome
        if outcome.status != "complete":
            unanswered.append({
                key: value
                for key, value in {
                    "place": places.get(line.key, line.key),
                    "status": outcome.status,
                    "reason": outcome.reason,
                    "message": outcome.message,
                }.items()
                if value is not None
            })
    found.sort(key=lambda one: (one[0], one[1]))
    hits = [hit for _, _, hit in found]
    shown = hits[:MAX_HITS]
    result: dict[str, Any] = {
        "words": request.words,
        "searched_inside": [visible[one].name for one in asked],
        # Every connection whose names are in this result, so it is withheld
        # once one of them stops allowing transfer (D135).
        "connector_ids": sorted({str(one) for hit in shown if (one := _connector_of(hit))}),
        "hits": [_shown(hit) for hit in shown],
        "has_more": more or len(hits) > MAX_HITS,
    }
    if unanswered:
        result["not_answered"] = unanswered
    if refused:
        result["refused"] = refused
    if unknown:
        result["not_found"] = unknown
    if not asked:
        result["note"] = NOTHING_INSIDE
    return result


def _connector_of(hit: Hit) -> uuid.UUID | None:
    target = hit.target
    if isinstance(target, ConnectionTarget | NodeTarget):
        return target.connector_id
    return None


def _shown(hit: Hit) -> dict[str, Any]:
    """A hit as the model reads it: what it is and the ids that open it."""
    target = hit.target
    shown: dict[str, Any] = {"title": hit.title}
    if isinstance(target, ConnectionTarget):
        shown.update(kind="connection", connector_id=str(target.connector_id))
    elif isinstance(target, NodeTarget):
        shown.update(
            kind="node",
            connector_id=str(target.connector_id),
            node_id=target.node_id,
            node_kind=target.node_kind,
            location=target.location,
        )
    else:
        shown.update(kind=target.object_type, id=target.object_id)
    if hit.detail:
        shown["detail"] = hit.detail
    shown["matched"] = hit.match.field
    if hit.match.field != "name" and hit.match.excerpt:
        shown["excerpt"] = "".join(segment.text for segment in hit.match.excerpt)
    return shown
