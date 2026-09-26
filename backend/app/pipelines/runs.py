"""A pipeline's run: started as one job, read back as its last (D177).

The run is its job. The job keeps what each link was to run and what it
did, so the last run is the pipeline's newest `pipeline.run` job and nothing
else is stored beside it.
"""

import uuid
from datetime import datetime
from typing import cast

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.paste.models import PasteRun
from app.connectors.paste.registry import kind_named
from app.core.config import settings
from app.jobs import crud as job_crud
from app.jobs.models import TERMINAL, Job, JobKind, JobState
from app.jobs.runner import JobRunner
from app.pipelines.models import Card, Link, LinkEnd, Pipeline, PipelineContent
from app.pipelines.order import ordered
from app.pipelines.record import RunRecord, RunStep, StepOutcome
from app.pipelines.results import Foresight
from app.realtime.topics import TopicSet
from app.users.models import User

KIND: JobKind = "pipeline.run"

# What a link lacks before it can run, by the window its kind opens; the other
# workflows run with what they have.
_NEEDS = {
    "new-relation": "needs its table named and its columns chosen",
    "into-relation": "needs its columns paired",
}

_SPELLED = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")


class LinkRun(BaseModel):
    """What one link did in the last run."""

    link_id: uuid.UUID
    outcome: StepOutcome
    message: str | None = None
    finished_at: datetime | None = None
    # What it made, and what it read of what another made (D178), by name.
    made: str | None = None
    read: str | None = None


class PipelineRunPublic(BaseModel):
    """The last run of a pipeline, as its job says now."""

    job_id: uuid.UUID
    state: JobState
    message: str | None
    started_at: datetime
    finished_at: datetime | None
    links: list[LinkRun]


class LastRun(BaseModel):
    """The last run, or none before the first: an answer that is an object
    either way, where a bare null would reach a client as nothing at all."""

    run: PipelineRunPublic | None = None


def missing(link: Link) -> str | None:
    """What running the link still needs chosen, asked of its kind alone."""
    workflow = kind_named(link.kind).workflow
    if workflow == "new-relation" and (link.name is None or not link.columns):
        return _NEEDS[workflow]
    if workflow == "into-relation" and not link.columns:
        return _NEEDS[workflow]
    return None


def _named(card: Card, end: LinkEnd, foresight: Foresight) -> str:
    if end.made_by is not None:
        made = foresight.made(end.made_by)
        return f"{card.connector_name} · {made.name if made is not None else 'a result'}"
    if end.node_id is None:
        return f"{card.connector_name} (top)"
    row = next((one for one in card.rows if one.node_id == end.node_id), None)
    return f"{card.connector_name} · {row.label if row is not None else end.node_id}"


def _step(content: PipelineContent, link: Link, foresight: Foresight) -> RunStep:
    source = content.card(link.source.card_id)
    target = content.card(link.target.card_id)
    # Validated with the content; said again for the types.
    if source is None or target is None:
        raise HTTPException(422, detail={"message": "A link of this pipeline no longer joins two rows"})
    kind = kind_named(link.kind)
    # A result's node is known only once its maker has run: named here by the
    # maker, and put in by the step when it starts (D178).
    source_node = link.source.node_id or str(link.source.made_by)
    target_node = link.target.node_id if link.target.made_by is None else None
    return RunStep(
        link_id=link.id,
        title=link.title,
        source_connection=source.connector_name,
        destination_connection=target.connector_name,
        source_label=_named(source, link.source, foresight),
        target_label=_named(target, link.target, foresight),
        destination_connector_id=target.connector_id,
        changes_source=kind.changes_source,
        paste=PasteRun(
            source_connector_id=source.connector_id,
            source_node_ids=[source_node],
            mode=kind.mode,
            destination_node_id=target_node,
            target_node_id=target_node,
            kind=link.kind,
            conflict=link.conflict,
            name=link.name,
            columns=link.columns,
        ),
        reads=link.source.made_by,
        writes_into=link.target.made_by,
    )


async def start_run(
    session: AsyncSession,
    user: User,
    runner: JobRunner,
    topics: TopicSet,
    pipeline: Pipeline,
    content: PipelineContent,
) -> PipelineRunPublic:
    """Every link, in order, as one job — or nothing, and why."""
    if not content.links:
        raise HTTPException(422, detail={"message": "Draw a link first"})
    order = ordered(content)
    lacking = [(placed, needs) for placed in order if (needs := missing(placed.link))]
    if lacking:
        said = "; ".join(f"{placed.number} · {placed.link.title} {needs}" for placed, needs in lacking)
        raise HTTPException(
            422,
            detail={
                "message": f"Nothing ran: {said}",
                "link_ids": [str(placed.link.id) for placed, _ in lacking],
            },
        )
    foresight = Foresight(content)
    record = RunRecord(
        pipeline_id=pipeline.id,
        pipeline_name=pipeline.name,
        steps=[_step(content, placed.link, foresight) for placed in order],
    )
    try:
        job = await job_crud.admit_within(
            session,
            owner_id=user.id,
            kind=KIND,
            limit=settings.PIPELINE_MAX_ACTIVE,
            subject_id=pipeline.id,
            step_count=len(runner.steps_of(KIND)),
            parameters=record.model_dump(mode="json"),
            alone=True,
        )
    except job_crud.SubjectBusy:
        raise HTTPException(
            409, detail={"message": "This pipeline is running; wait for it to finish"}
        ) from None
    except job_crud.TooManyActive:
        limit = settings.PIPELINE_MAX_ACTIVE
        count = _SPELLED[limit] if limit < len(_SPELLED) else str(limit)
        raise HTTPException(
            429, detail={"message": f"{count} pipelines are running — wait for one to finish"}
        ) from None
    await runner.launch(job, topics)
    return _public(job, content)


def _outcome(step: RunStep, job: Job) -> tuple[StepOutcome, str | None]:
    """A step as it ended. A run the server stopped left its steps as they were."""
    if job.state not in TERMINAL:
        return step.outcome, step.message
    if step.outcome == "waiting":
        return "not_run", None
    if step.outcome == "running":
        return "failed", job.message
    return step.outcome, step.message


def _public(job: Job, content: PipelineContent) -> PipelineRunPublic:
    try:
        record = RunRecord.model_validate(job.parameters)
    except ValidationError:
        record = None
    kept = {link.id for link in content.links}
    links: list[LinkRun] = []
    for step in record.steps if record is not None else []:
        if step.link_id not in kept:
            continue
        outcome, message = _outcome(step, job)
        maker = None if step.reads is None or record is None else record.step_of(step.reads)
        links.append(
            LinkRun(
                link_id=step.link_id,
                outcome=outcome,
                message=message,
                finished_at=step.finished_at,
                made=step.made_name,
                read=None if maker is None or outcome not in ("done", "failed") else maker.made_name,
            )
        )
    return PipelineRunPublic(
        job_id=job.id,
        # The column is a string; only the runner writes it, from JobState.
        state=cast(JobState, job.state),
        message=job.message,
        started_at=job.started_at or job.created_at,
        finished_at=job.finished_at,
        links=links,
    )


async def last_run(
    session: AsyncSession, pipeline: Pipeline, content: PipelineContent
) -> LastRun:
    """The pipeline's newest run, the links still drawn on it only."""
    job = (
        await session.exec(
            select(Job)
            .where(Job.subject_id == pipeline.id)
            .where(Job.owner_id == pipeline.owner_id)
            .where(Job.kind == KIND)
            .order_by(col(Job.created_at).desc())
            .limit(1)
        )
    ).first()
    return LastRun(run=None if job is None else _public(job, content))
