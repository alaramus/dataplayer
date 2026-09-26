"""A person's pipelines: listed, made, saved whole and removed (D175).

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

from app.adapters.cache import DataCacheDep
from app.adapters.resources import ResourcesDep
from app.connectors import crud as connector_crud
from app.core.db import SessionDep
from app.core.schemas import Message
from app.jobs.runner import JobRunnerDep
from app.pipelines.check import card_state
from app.pipelines.hint import Hint, HintRequest, hint
from app.pipelines.models import (
    MAX_PIPELINES,
    CardState,
    LinkRun,
    Pipeline,
    PipelineContent,
    PipelineCreate,
    PipelinePublic,
    PipelineSave,
    PipelineSummary,
    content_of,
    public,
    summary,
)
from app.pipelines.runs import LinkRunAnswer, forget_gone, run_link, runs_of
from app.realtime.topics import TopicsDep
from app.transfers.run import Carrying
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
    await forget_gone(session, pipeline.id, content)
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


@router.get("/{pipeline_id}/runs", response_model=list[LinkRun])
async def read_runs(
    session: SessionDep, current_user: CurrentUser, pipeline_id: uuid.UUID
) -> Any:
    """The last run of each link, a transfer's as its job says now (D176)."""
    pipeline, content = await _content(session, current_user, pipeline_id)
    return await runs_of(session, pipeline, content)


@router.post("/{pipeline_id}/links/{link_id}/run", response_model=LinkRunAnswer)
async def run_pipeline_link(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    pipeline_id: uuid.UUID,
    link_id: uuid.UUID,
) -> Any:
    """Run one link by what is kept with it, as Paste runs (D176).

    What the paste refuses is the run's outcome rather than this route's: it
    stays on the link, which is where the person looks for it.
    """
    pipeline, content = await _content(session, current_user, pipeline_id)
    link = content.link(link_id)
    if link is None:
        raise HTTPException(404, detail={"message": "No such link"})
    carrying = Carrying(session, current_user, resources, data_cache, runner, topics)
    return await run_link(carrying, pipeline, content, link)


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
