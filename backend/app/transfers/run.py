"""One paste into another connection, carried out: at once, or as a transfer
job (D164, D168).

Above the jobs package, which the paste offers are not: a kind that moves
bytes is planned here and carried out by `RunTransfer`. A pipeline's run
(D177) carries each link out through `paste_now` and `planned` as well, so a
link runs exactly as the Paste it stands for.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCache
from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourceStore
from app.connectors.access import adapter_for
from app.connectors.action_lookup import perform
from app.connectors.models import Connector
from app.connectors.paste.kinds import PastesAsJob, PastesNow
from app.connectors.paste.models import PasteResult, PasteRun
from app.connectors.paste.registry import kind_named
from app.connectors.paste.transfer import Transfer
from app.core.config import settings
from app.core.problems import Problem
from app.core.translation import say
from app.jobs import crud as job_crud
from app.jobs.models import JobPublic, public
from app.jobs.runner import JobRunner
from app.realtime.topics import TopicSet
from app.transfers.handler import KIND
from app.users.models import User


class PasteStarted(BaseModel):
    """A transfer accepted as a job; the footer follows it from here."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    outcome: Literal["started"] = "started"
    job: JobPublic


PasteAnswer = Annotated[PasteResult | PasteStarted, Field(discriminator="outcome")]

@dataclass(frozen=True)
class Carrying:
    """What carrying a paste out needs besides the request: the stores and
    the runner a route receives as dependencies."""

    session: AsyncSession
    user: User
    resources: ResourceStore
    data_cache: DataCache
    runner: JobRunner
    topics: TopicSet


async def run_paste(
    carrying: Carrying, connector_id: uuid.UUID, request: PasteRun
) -> PasteResult | PasteStarted:
    """The paste into `connector_id`, after both ends are checked again for
    what the kind needs; refusals are raised as the paste route answers them."""
    kind = kind_named(request.kind)
    if kind.mode != request.mode:
        raise Problem(422, "transfers.wrong_clipboard")
    session, user, resources = carrying.session, carrying.user, carrying.resources
    source = await adapter_for(
        session, request.source_connector_id, user, resources, requires=kind.source_requires
    )
    destination = await adapter_for(
        session, connector_id, user, resources, requires=kind.destination_requires
    )
    if not kind.serves(source, destination):
        raise Problem(501, "transfers.not_possible")
    if isinstance(kind, PastesAsJob):
        transfer = await planned(session, kind, source, destination, connector_id, request)
        return await _started(carrying, transfer, connector_id)
    if not isinstance(kind, PastesNow):
        raise Problem(501, "transfers.cannot_run")
    return await paste_now(carrying.data_cache, kind, source, destination, connector_id, request)


async def paste_now(
    data_cache: DataCache,
    kind: PastesNow,
    source: DataAdapter,
    destination: DataAdapter,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteResult:
    """A kind carried out where it is asked: in a request, or in a pipeline's job."""
    try:
        return await perform(lambda: kind.run(source, destination, request))
    finally:
        # On failure too: earlier rows or files may already have arrived.
        await data_cache.invalidate_connector(connector_id)
        if kind.changes_source:
            await data_cache.invalidate_connector(request.source_connector_id)


async def planned(
    session: AsyncSession,
    kind: PastesAsJob,
    source: DataAdapter,
    destination: DataAdapter,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> Transfer:
    """What a transfer will move, planned before anything does: a taken name
    answers here. The session is the one both ends were opened in."""
    plan = await perform(lambda: kind.plan(source, destination, request))
    source_label = await _label(session, request.source_connector_id)
    destination_label = await _label(session, connector_id)
    return Transfer(
        kind=kind.name,
        # Stored worded, in the language of whoever pasted (D226).
        title=say(kind.title),
        doing=say(kind.doing),
        done=say(kind.done),
        mode=kind.mode,
        conflict=request.conflict,
        source_connector_id=request.source_connector_id,
        source_label=source_label,
        destination_connector_id=connector_id,
        destination_node_id=request.destination_node_id,
        destination_label=destination_label,
        place_label=plan.place or destination_label,
        name=plan.name,
        tables=plan.tables,
        items=plan.items,
        bytes_total=plan.bytes_total,
    )


async def _started(
    carrying: Carrying, transfer: Transfer, connector_id: uuid.UUID
) -> PasteStarted:
    """A planned transfer, carried out as a job of its own."""
    session = carrying.session
    try:
        job = await job_crud.admit_within(
            session,
            owner_id=carrying.user.id,
            kind=KIND,
            limit=settings.TRANSFER_MAX_ACTIVE,
            subject_id=connector_id,
            step_count=len(carrying.runner.steps_of(KIND)),
            parameters=transfer.model_dump(mode="json"),
        )
    except job_crud.TooManyActive:
        raise Problem(
            429, "transfers.too_many_running", count=settings.TRANSFER_MAX_ACTIVE
        ) from None
    await carrying.runner.launch(job, carrying.topics)
    return PasteStarted(job=public(job))


async def _label(session: AsyncSession, connector_id: uuid.UUID) -> str:
    # Already loaded by the access check, so this reads no row.
    connector = await session.get(Connector, connector_id)
    return connector.name if connector is not None else say("the connection")
