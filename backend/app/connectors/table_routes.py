"""Declaring a table over a connection's keys, changing it, removing it (D170).

Asking reads the connection; the proposal, a declaration and its removal need
`structure`, the level that changes a table's structure elsewhere. What a
declaration may be over is the driver's answer; keeping it is the row's.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCacheDep
from app.adapters.declared_tables import (
    MAX_PLACE_ID,
    DeclareTableRequest,
    TablePlace,
    TableProposal,
)
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsDeclaredTables,
)
from app.adapters.resources import ResourcesDep
from app.connectors.access import resolve_adapter
from app.connectors.action_lookup import perform
from app.connectors.models import Connector
from app.connectors.tables import keep, tables_of, with_table, without_table
from app.core.access import at_least
from app.core.db import SessionDep
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])

NEEDS_STRUCTURE = "This needs structure access to the connection"
CHOOSE = "Select a folder to describe as a table"


class TableSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Nothing chosen is a question too: the answer says what to choose.
    node_id: str | None = Field(default=None, max_length=MAX_PLACE_ID)


class TableOffer(BaseModel):
    """Whether "Describe as table" can be used on this node, and why not."""

    available: bool
    reason: str | None = None
    declared: bool = False


class TableChanged(BaseModel):
    """What a declaration changed, for the catalog to re-read."""

    message: str
    # The level the table stands in, beside its folder.
    reload_node_ids: list[str | None]


@router.post("/{connector_id}/tables/offer", response_model=TableOffer)
async def table_offer(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    subject: TableSubject,
) -> TableOffer:
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    declaring = _declaring(adapter)
    if subject.node_id is None:
        return TableOffer(available=False, reason=CHOOSE)
    try:
        place = await declaring.table_place(subject.node_id)
    except ValueError as refusal:
        return TableOffer(available=False, reason=str(refusal) or CHOOSE)
    except NodeNotFound:
        return TableOffer(available=False, reason="This is no longer in the catalog")
    except AdapterError as failure:
        return TableOffer(available=False, reason=failure.message)
    declared = place.declared is not None
    if not at_least(access, "structure"):
        return TableOffer(available=False, reason=NEEDS_STRUCTURE, declared=declared)
    return TableOffer(available=True, declared=declared)


@router.post("/{connector_id}/tables/proposal", response_model=TableProposal)
async def table_proposal(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    subject: TableSubject,
) -> TableProposal:
    """The fields of the folder's first hashes, or the table and what else they hold."""
    adapter, _ = await resolve_adapter(
        session, connector_id, current_user, resources, requires="structure"
    )
    declaring = _declaring(adapter)
    return await perform(lambda: declaring.propose_table(subject.node_id or ""))


@router.put("/{connector_id}/tables", response_model=TableChanged)
async def declare_table(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: DeclareTableRequest,
) -> TableChanged:
    """Declare a table over a folder, or change the one declared there."""
    adapter, _ = await resolve_adapter(
        session, connector_id, current_user, resources, requires="structure"
    )
    declaring = _declaring(adapter)
    place = await perform(lambda: declaring.table_place(request.node_id))
    table = await perform(lambda: declaring.declared_table(request))
    connector = await _locked(session, connector_id)
    keep(connector, with_table(tables_of(connector), table))
    await session.commit()
    await data_cache.invalidate_connector(connector_id)
    verb = "changed" if place.declared is not None else "declared"
    return TableChanged(message=f"{table.name} {verb}", reload_node_ids=[place.listed_in])


@router.delete("/{connector_id}/tables", response_model=TableChanged)
async def remove_table(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    node_id: str = Query(max_length=MAX_PLACE_ID),
) -> TableChanged:
    """Forget a declaration. No key is touched."""
    adapter, _ = await resolve_adapter(
        session, connector_id, current_user, resources, requires="structure"
    )
    declaring = _declaring(adapter)
    place: TablePlace = await perform(lambda: declaring.table_place(node_id))
    if place.declared is None:
        raise HTTPException(
            status_code=404, detail={"message": "No table is declared here"}
        )
    connector = await _locked(session, connector_id)
    keep(connector, without_table(tables_of(connector), place.place_id))
    await session.commit()
    await data_cache.invalidate_connector(connector_id)
    return TableChanged(
        message=f"{place.declared.name} removed; its keys are as they were",
        reload_node_ids=[place.listed_in],
    )


def _declaring(adapter: DataAdapter) -> SupportsDeclaredTables:
    if not isinstance(adapter, SupportsDeclaredTables):
        raise HTTPException(
            status_code=501,
            detail={"message": "Tables cannot be declared over this source"},
        )
    return adapter


async def _locked(session: AsyncSession, connector_id: uuid.UUID) -> Connector:
    """The row, held until the commit: two declarations at once must not drop one."""
    connector = await session.get(Connector, connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    await session.refresh(connector, attribute_names=["declared_tables"], with_for_update=True)
    return connector

