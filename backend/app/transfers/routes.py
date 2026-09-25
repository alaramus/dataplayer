"""Pasting into another connection: at once, or as a transfer job (D164, D168).

Above the jobs package, which the paste offers are not: a kind that moves
bytes is planned here and carried out by `RunTransfer`.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCacheDep
from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourcesDep
from app.connectors.access import adapter_for
from app.connectors.action_lookup import perform
from app.connectors.models import Connector
from app.connectors.paste.kinds import PastesAsJob, PastesNow
from app.connectors.paste.models import PasteResult, PasteRun
from app.connectors.paste.registry import kind_named
from app.connectors.paste.transfer import Transfer
from app.core.config import settings
from app.core.db import SessionDep
from app.jobs import crud as job_crud
from app.jobs.models import JobPublic, public
from app.jobs.runner import JobRunner, JobRunnerDep
from app.realtime.topics import TopicsDep, TopicSet
from app.transfers.handler import KIND
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/connectors", tags=["connectors"])


class PasteStarted(BaseModel):
    """A transfer accepted as a job; the footer follows it from here."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    outcome: Literal["started"] = "started"
    job: JobPublic


PasteAnswer = Annotated[PasteResult | PasteStarted, Field(discriminator="outcome")]

_SPELLED = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")


@router.post("/{connector_id}/paste", response_model=PasteAnswer)
async def paste(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteResult | PasteStarted:
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
        session,
        connector_id,
        current_user,
        resources,
        requires=kind.destination_requires,
    )
    if not kind.serves(source, destination):
        raise HTTPException(
            status_code=501,
            detail={"message": f"{kind.title} is not possible between these connections"},
        )
    if isinstance(kind, PastesAsJob):
        return await _started(
            session, current_user, runner, topics, kind, source, destination, connector_id, request
        )
    if not isinstance(kind, PastesNow):
        raise HTTPException(status_code=501, detail={"message": f"{kind.title} cannot run"})
    try:
        return await perform(lambda: kind.run(source, destination, request))
    finally:
        # On failure too: earlier rows or files may already have arrived.
        await data_cache.invalidate_connector(connector_id)
        if kind.changes_source:
            await data_cache.invalidate_connector(request.source_connector_id)


async def _started(
    session: AsyncSession,
    current_user: User,
    runner: JobRunner,
    topics: TopicSet,
    kind: PastesAsJob,
    source: DataAdapter,
    destination: DataAdapter,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteStarted:
    """Plan now — a taken name answers at once — and carry it out as a job."""
    planned = await perform(lambda: kind.plan(source, destination, request))
    source_label = await _label(session, request.source_connector_id)
    destination_label = await _label(session, connector_id)
    transfer = Transfer(
        kind=kind.name,
        title=kind.title,
        doing=kind.doing,
        done=kind.done,
        mode=kind.mode,
        conflict=request.conflict,
        source_connector_id=request.source_connector_id,
        source_label=source_label,
        destination_connector_id=connector_id,
        destination_node_id=request.destination_node_id,
        destination_label=destination_label,
        place_label=planned.place or destination_label,
        name=planned.name,
        items=planned.items,
        bytes_total=planned.bytes_total,
    )
    try:
        job = await job_crud.admit_within(
            session,
            owner_id=current_user.id,
            kind=KIND,
            limit=settings.TRANSFER_MAX_ACTIVE,
            subject_id=connector_id,
            step_count=len(runner.steps_of(KIND)),
            parameters=transfer.model_dump(mode="json"),
        )
    except job_crud.TooManyActive:
        limit = settings.TRANSFER_MAX_ACTIVE
        count = _SPELLED[limit] if limit < len(_SPELLED) else str(limit)
        raise HTTPException(
            status_code=429,
            detail={"message": f"{count} transfers are running — wait for one to finish"},
        ) from None
    await runner.launch(job, topics)
    return PasteStarted(job=public(job))


async def _label(session: AsyncSession, connector_id: uuid.UUID) -> str:
    # Already loaded by the access check, so this reads no row.
    connector = await session.get(Connector, connector_id)
    return connector.name if connector is not None else "the connection"
