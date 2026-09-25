"""Asking what a clipboard can become in another connection, and doing it (D164).

The routes hang off the destination, as Paste is chosen there; the source is
named in the body because a clipboard carries its connection with it.
"""

import uuid

from fastapi import APIRouter, HTTPException

from app.adapters.cache import DataCacheDep
from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourcesDep
from app.connectors.access import adapter_for, resolve_adapter
from app.connectors.action_lookup import perform
from app.connectors.paste.kinds import refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    ClipboardOffer,
    ClipboardRequest,
    PasteOffer,
    PasteOffers,
    PastePair,
    PasteResult,
    PasteRun,
)
from app.connectors.paste.registry import KINDS, kind_named
from app.core.access import Access, at_least
from app.core.db import SessionDep
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])


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
    offers: list[PasteOffer] = []
    for kind in KINDS:
        if kind.mode != pair.mode or not kind.serves(source, destination):
            continue
        if not at_least(destination_access, "write"):
            offers.append(refused(kind, "This needs write access to this connection"))
        elif not at_least(source_access, kind.source_requires):
            offers.append(
                refused(
                    kind,
                    f"This needs {kind.source_requires} access to the copied connection",
                )
            )
        else:
            offers.append(await kind.offer(source, destination, pair))
    return PasteOffers(offers=offers)


@router.post("/{connector_id}/paste", response_model=PasteResult)
async def paste(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteResult:
    kind = kind_named(request.kind)
    if kind.mode != request.mode:
        raise HTTPException(
            status_code=422,
            detail={"message": f"{kind.title} does not take this clipboard"},
        )
    source = await adapter_for(
        session,
        request.source_connector_id,
        current_user,
        resources,
        requires=kind.source_requires,
    )
    destination = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
    if not kind.serves(source, destination):
        raise HTTPException(
            status_code=501,
            detail={"message": f"{kind.title} is not possible between these connections"},
        )
    try:
        return await perform(lambda: kind.run(source, destination, request))
    finally:
        # On failure too: earlier files of a batch may already have arrived.
        await data_cache.invalidate_connector(connector_id)
        if kind.changes_source:
            await data_cache.invalidate_connector(request.source_connector_id)


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
