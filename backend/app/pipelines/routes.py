"""A person's pipelines: listed, made, saved whole, removed (D175), run
(D177) and run by a schedule (D179).

Private in this step: every route answers only the owner, and anyone else is
told there is no such pipeline, as a connection nobody shared is (D33).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.resources import ResourcesDep
from app.connectors import crud as connector_crud
from app.connectors.paste.models import PasteOffers
from app.core.db import SessionDep
from app.core.schemas import Message
from app.jobs.runner import JobRunnerDep
from app.pipelines.check import card_state
from app.pipelines.hint import Hint, HintRequest, hint
from app.pipelines.models import (
    MAX_PIPELINES,
    CardState,
    LinkPlace,
    Pipeline,
    PipelineContent,
    PipelineCreate,
    PipelinePublic,
    PipelineSave,
    PipelineSummary,
    content_of,
    summary,
)
from app.pipelines.offers import Asking, LinkOffersRequest
from app.pipelines.order import ordered
from app.pipelines.results import Foresight
from app.pipelines.runs import LastRun, PipelineRunPublic, last_run, start_run
from app.pipelines.schedule import PipelineSchedule, SchedulePublic, ScheduleSettings
from app.pipelines.scheduler import public as schedule_public
from app.pipelines.scheduler import save as save_schedule
from app.realtime.topics import TopicsDep
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


async def _owned(session: AsyncSession, user: User, pipeline_id: uuid.UUID) -> Pipeline:
    pipeline = await session.get(Pipeline, pipeline_id)
    if pipeline is None or pipeline.owner_id != user.id:
        raise HTTPException(404, detail={"message": "No such pipeline"})
    return pipeline


async def _content(session: AsyncSession, user: User, pipeline_id: uuid.UUID) -> tuple[Pipeline, PipelineContent]:
    pipeline = await _owned(session, user, pipeline_id)
    # A body that no longer reads is shown empty (D175), so it holds nothing.
    return pipeline, content_of(pipeline) or PipelineContent()


def public(pipeline: Pipeline) -> PipelinePublic:
    """The pipeline as its owner reads it, each link numbered in the order a
    run takes it (D177), and what each makes as a row of its card (D178)."""
    content = content_of(pipeline)
    return PipelinePublic(
        id=pipeline.id,
        name=pipeline.name,
        version=pipeline.version,
        updated_at=pipeline.updated_at,
        cards=[] if content is None else content.cards,
        links=[] if content is None else content.links,
        broken=content is None,
        order=[]
        if content is None
        else [
            LinkPlace(link_id=placed.link.id, number=placed.number, circle=placed.circle)
            for placed in ordered(content)
        ],
        results=[] if content is None else Foresight(content).rows(),
    )


@router.get("", response_model=list[PipelineSummary])
async def read_pipelines(session: SessionDep, current_user: CurrentUser) -> Any:
    """The caller's pipelines, by name."""
    found = await session.exec(
        select(Pipeline)
        .where(Pipeline.owner_id == current_user.id)
        .order_by(func.lower(col(Pipeline.name)), col(Pipeline.created_at))
    )
    return [summary(pipeline) for pipeline in found.all()]


@router.post("", response_model=PipelinePublic)
async def create_pipeline(
    session: SessionDep, current_user: CurrentUser, body: PipelineCreate
) -> Any:
    held = await session.exec(
        select(func.count()).select_from(Pipeline).where(Pipeline.owner_id == current_user.id)
    )
    if held.one() >= MAX_PIPELINES:
        raise HTTPException(
            422, detail={"message": f"A person keeps at most {MAX_PIPELINES} pipelines"}
        )
    pipeline = Pipeline(
        owner_id=current_user.id,
        name=body.name,
        content=PipelineContent().model_dump(mode="json"),
    )
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    return public(pipeline)


@router.get("/{pipeline_id}", response_model=PipelinePublic)
async def read_pipeline(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID
) -> Any:
    return public(await _owned(session, current_user, pipeline_id))


@router.put("/{pipeline_id}", response_model=PipelinePublic)
async def save_pipeline(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID, body: PipelineSave
) -> Any:
    """The pipeline, replaced whole.

    A card already on it stays whatever happened to its connection since; a
    connection a card is added for must be one the caller can read now, or a
    stored pipeline would become a list of other people's ids.
    """
    pipeline = await _owned(session, current_user, pipeline_id)
    if body.version != pipeline.version:
        raise HTTPException(
            409, detail={"message": "This pipeline was changed somewhere else; reload it"}
        )
    stored = content_of(pipeline)
    known = set() if stored is None else {card.connector_id for card in stored.cards}
    for connector_id in {card.connector_id for card in body.cards} - known:
        if await connector_crud.get_with_access(
            session, connector_id=connector_id, user=current_user
        ) is None:
            raise HTTPException(
                422, detail={"message": "A card names a connection you cannot read"}
            )
    content = PipelineContent(cards=body.cards, links=body.links)
    pipeline.name = body.name
    pipeline.content = content.model_dump(mode="json")
    pipeline.version += 1
    pipeline.updated_at = datetime.now(UTC)
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    return public(pipeline)


@router.delete("/{pipeline_id}", response_model=Message)
async def delete_pipeline(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID
) -> Any:
    pipeline = await _owned(session, current_user, pipeline_id)
    await session.delete(pipeline)
    await session.commit()
    return Message(message=f"{pipeline.name} was removed")


@router.get("/{pipeline_id}/cards/{card_id}/state", response_model=CardState)
async def read_card_state(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    pipeline_id: uuid.UUID,
    card_id: uuid.UUID,
) -> Any:
    """Whether the card's connection can be read, and which of its rows are gone.

    The card is read from the stored pipeline rather than sent: what is asked
    of a source is what the owner kept, never what a client names.
    """
    _, content = await _content(session, current_user, pipeline_id)
    card = content.card(card_id)
    if card is None:
        raise HTTPException(404, detail={"message": "No such card"})
    return await card_state(session, current_user, resources, card)


@router.get("/{pipeline_id}/run", response_model=LastRun)
async def read_last_run(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID
) -> Any:
    """The pipeline's last run as its job says now, or nothing before the first."""
    pipeline, content = await _content(session, current_user, pipeline_id)
    return await last_run(session, pipeline, content)


@router.post("/{pipeline_id}/run", response_model=PipelineRunPublic)
async def run_pipeline(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    pipeline_id: uuid.UUID,
) -> Any:
    """Run every link of the pipeline as saved, one after another (D177).

    Refused whole, before anything runs, when a link lacks a choice its
    operation needs; each link's own refusal is its step's outcome instead.
    """
    pipeline, content = await _content(session, current_user, pipeline_id)
    return await start_run(session, current_user, runner, topics, pipeline, content)


@router.get("/{pipeline_id}/schedule", response_model=SchedulePublic)
async def read_schedule(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID
) -> Any:
    """When the pipeline runs by itself, when next, and what last came of it."""
    pipeline = await _owned(session, current_user, pipeline_id)
    return schedule_public(await session.get(PipelineSchedule, pipeline.id))


@router.put("/{pipeline_id}/schedule", response_model=SchedulePublic)
async def set_schedule(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID, body: ScheduleSettings
) -> Any:
    """The schedule, replaced; switched off, it keeps what was chosen."""
    pipeline = await _owned(session, current_user, pipeline_id)
    return await save_schedule(session, pipeline.id, body, datetime.now(UTC))


@router.post("/{pipeline_id}/offers", response_model=PasteOffers)
async def read_link_offers(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    pipeline_id: uuid.UUID,
    body: LinkOffersRequest,
) -> Any:
    """What can go from one row of the pipeline into another (D176).

    A row that is what a link makes is asked of as the link will make it
    (D178), so the pipeline as kept is what answers: a screen saves first.
    """
    _, content = await _content(session, current_user, pipeline_id)
    asking = Asking(session, current_user, resources, content, strict=True)
    return PasteOffers(offers=await asking.offers(body.source, body.target))


@router.post("/{pipeline_id}/hint", response_model=Hint)
async def read_hint(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    pipeline_id: uuid.UUID,
    body: HintRequest,
) -> Any:
    """Every link that could be drawn among the rows kept on the pipeline."""
    _, content = await _content(session, current_user, pipeline_id)
    return await hint(session, current_user, resources, content, body.card_id)
