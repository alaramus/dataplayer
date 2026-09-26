"""Asking what a clipboard can become in another connection (D164).

The routes hang off the destination, as Paste is chosen there; the source is
named in the body because a clipboard carries its connection with it. Doing
it is `app.transfers`', which may start a job (D168).
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourcesDep
from app.connectors.access import resolve_adapter
from app.connectors.paste.kinds import PasteKind, refused
from app.connectors.paste.map import (
    MAX_MAP_CONNECTIONS,
    InteractionMap,
    TooManyConnections,
    interaction_map,
)
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    ClipboardOffer,
    ClipboardRequest,
    PairRequest,
    PairSide,
    PasteOffer,
    PasteOffers,
    PastePair,
)
from app.connectors.paste.registry import KINDS
from app.core.access import Access, at_least
from app.core.db import SessionDep
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])
# Its own prefix: `/connectors/{connector_id}` would take a word in its place
# and refuse it as an id.
map_router = APIRouter(prefix="/interactions", tags=["connectors"])


@map_router.get("/map", response_model=InteractionMap)
async def read_interaction_map(
    session: SessionDep, current_user: CurrentUser
) -> InteractionMap:
    """What every connection of this person's can give each other (D174)."""
    try:
        return await interaction_map(session, current_user)
    except TooManyConnections:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"More than {MAX_MAP_CONNECTIONS} connections cannot be drawn"
            },
        ) from None


@router.post("/{connector_id}/paste/offers", response_model=PasteOffers)
async def paste_offers(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    pair: PastePair,
) -> PasteOffers:
    """What the clipboard can become here, each with its reason when it cannot.

    Reading both ends is enough to ask. A kind that needs more says so as its
    reason rather than as a refusal, and is checked again when it runs.
    """
    source, source_access = await resolve_adapter(
        session, pair.source_connector_id, current_user, resources, requires="read"
    )
    destination, destination_access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    return PasteOffers(
        offers=[
            await _offer(kind, source, source_access, destination, destination_access, pair)
            for kind in KINDS
            if kind.mode == pair.mode and kind.serves(source, destination)
        ]
    )


@router.post("/pair/offers", response_model=PasteOffers)
async def pair_offers(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    request: PairRequest,
) -> PasteOffers:
    """What the ticks of one catalog can become in the other, both verbs (D167).

    The destination is the other side's place, and its one tick. A source with
    nothing ticked still hears every kind the two connections could do that
    way, each saying what to tick. The other way is the same question with the
    sides swapped, as the window asks it.
    """
    if request.source.connector_id == request.destination.connector_id:
        raise HTTPException(
            status_code=422, detail={"message": "Pair two different connections"}
        )
    source, source_access = await resolve_adapter(
        session, request.source.connector_id, current_user, resources, requires="read"
    )
    destination, destination_access = await resolve_adapter(
        session, request.destination.connector_id, current_user, resources, requires="read"
    )
    return PasteOffers(
        offers=await _across(
            (request.source, source, source_access),
            (request.destination, destination, destination_access),
        )
    )


type _End = tuple[PairSide, DataAdapter, Access]


async def _across(source: _End, destination: _End) -> list[PasteOffer]:
    source_side, source_adapter, source_access = source
    destination_side, destination_adapter, destination_access = destination
    offers: list[PasteOffer] = []
    for kind in KINDS:
        if not kind.serves(source_adapter, destination_adapter):
            continue
        if not source_side.ticked:
            offers.append(refused(kind, kind.needs))
            continue
        pair = PastePair(
            source_connector_id=source_side.connector_id,
            source_node_ids=source_side.ticked,
            mode=kind.mode,
            destination_node_id=destination_side.place,
            target_node_id=(
                destination_side.ticked[0] if len(destination_side.ticked) == 1 else None
            ),
        )
        offers.append(
            await _offer(
                kind,
                source_adapter,
                source_access,
                destination_adapter,
                destination_access,
                pair,
            )
        )
    return offers


async def _offer(
    kind: PasteKind,
    source: DataAdapter,
    source_access: Access,
    destination: DataAdapter,
    destination_access: Access,
    pair: PastePair,
) -> PasteOffer:
    """One kind's answer, after what it needs of each end beyond reading."""
    if not at_least(destination_access, kind.destination_requires):
        return refused(
            kind, f"This needs {kind.destination_requires} access to this connection"
        )
    if not at_least(source_access, kind.source_requires):
        return refused(
            kind, f"This needs {kind.source_requires} access to the copied connection"
        )
    return await kind.offer(source, destination, pair)


@router.post("/{connector_id}/clipboard/offer", response_model=ClipboardOffer)
async def clipboard_offer(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: ClipboardRequest,
) -> ClipboardOffer:
    """Whether a selection here can be copied or cut to be pasted elsewhere."""
    source, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    return ClipboardOffer(
        can_copy=await _can_hold(source, access, request.node_ids, "copy"),
        can_cut=await _can_hold(source, access, request.node_ids, "move"),
    )


async def _can_hold(
    source: DataAdapter, access: Access, node_ids: list[str], mode: ClipboardMode
) -> Availability | None:
    kinds = [kind for kind in KINDS if kind.mode == mode and kind.takes_from(source)]
    if not kinds:
        return None
    if not node_ids:
        return Availability(available=False, reason="Tick a row to use this")
    reasons: list[str] = []
    for kind in kinds:
        if not at_least(access, kind.source_requires):
            reasons.append(f"This needs {kind.source_requires} access")
            continue
        answer = await kind.supply(source, node_ids)
        if answer.available:
            return answer
        reasons.append(answer.reason or f"{kind.title} does not take this selection")
    return Availability(available=False, reason=reasons[0])
