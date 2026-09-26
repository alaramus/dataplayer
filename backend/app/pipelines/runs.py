"""A link run, and what became of it (D176).

A link runs as the Paste it stands for, through the same door (`run_paste`),
by the choices kept with it and never by what a client sends. What the run
answered stays on the link until the next one.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.paste.models import PasteResult, PasteRun
from app.connectors.paste.registry import kind_named
from app.jobs.models import Job, JobPublic
from app.pipelines.models import (
    Link,
    LinkRun,
    Pipeline,
    PipelineContent,
    PipelineRun,
    RunOutcome,
)
from app.transfers.run import Carrying, run_paste

_JOB_OUTCOMES: Mapping[str, RunOutcome] = {
    "queued": "running",
    "running": "running",
    "succeeded": "done",
    "failed": "failed",
    "cancelled": "failed",
    "interrupted": "failed",
}

# The one door to a source says these in its own words; a link has two ends,
# so which of them it was is not known here.
_REFUSALS = {
    404: "A connection of this link is gone, or no longer shared with you",
    409: "A connection of this link is switched off",
}


class LinkRunAnswer(BaseModel):
    run: LinkRun
    # A transfer, followed from here as Paste's is (D168).
    job: JobPublic | None = None


def _said(refused: HTTPException) -> str:
    detail = refused.detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return str(detail["message"])
    return _REFUSALS.get(refused.status_code, "The link could not run")


def _public(row: PipelineRun) -> LinkRun:
    return LinkRun(
        link_id=row.link_id,
        outcome=row.outcome,
        message=row.message,
        job_id=row.job_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


async def _settled(session: AsyncSession, row: PipelineRun) -> bool:
    """Take a transfer's outcome from its job once it has one; whether it changed."""
    if row.outcome != "running" or row.job_id is None:
        return False
    job = await session.get(Job, row.job_id)
    if job is None:
        row.outcome, row.message = "failed", "The transfer is no longer known"
        row.finished_at = datetime.now(UTC)
        return True
    outcome = _JOB_OUTCOMES.get(job.state, "failed")
    if outcome == "running":
        return False
    row.outcome, row.message, row.finished_at = outcome, job.message, job.finished_at
    return True


async def runs_of(
    session: AsyncSession, pipeline: Pipeline, content: PipelineContent
) -> list[LinkRun]:
    """The last run of every link still on the pipeline."""
    kept = {link.id for link in content.links}
    found = await session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_id == pipeline.id)
    )
    rows = [row for row in found.all() if row.link_id in kept]
    changed = False
    for row in rows:
        if await _settled(session, row):
            session.add(row)
            changed = True
    if changed:
        await session.commit()
    return [_public(row) for row in rows]


async def forget_gone(
    session: AsyncSession, pipeline_id: uuid.UUID, content: PipelineContent
) -> None:
    """Drop the runs of links no longer drawn; the caller commits."""
    kept = [link.id for link in content.links]
    await session.exec(
        delete(PipelineRun)
        .where(col(PipelineRun.pipeline_id) == pipeline_id)
        .where(col(PipelineRun.link_id).not_in(kept))
    )


async def run_link(
    carrying: Carrying, pipeline: Pipeline, content: PipelineContent, link: Link
) -> LinkRunAnswer:
    """Run the link by what is kept with it, and keep what it answered."""
    source = content.card(link.source.card_id)
    target = content.card(link.target.card_id)
    # Validated with the content; said again for the types.
    if source is None or target is None or link.source.node_id is None:
        raise HTTPException(404, detail={"message": "No such link"})
    kind = kind_named(link.kind)
    request = PasteRun(
        source_connector_id=source.connector_id,
        source_node_ids=[link.source.node_id],
        mode=kind.mode,
        destination_node_id=link.target.node_id,
        target_node_id=link.target.node_id,
        kind=link.kind,
        conflict=link.conflict,
        name=link.name,
        columns=link.columns,
    )
    session = carrying.session
    started = datetime.now(UTC)
    row = PipelineRun(pipeline_id=pipeline.id, link_id=link.id, outcome="running", started_at=started)
    job: JobPublic | None = None
    try:
        answer = await run_paste(carrying, target.connector_id, request)
    except HTTPException as refused:
        row.outcome, row.message, row.finished_at = "failed", _said(refused), datetime.now(UTC)
    else:
        if isinstance(answer, PasteResult):
            row.outcome, row.message, row.finished_at = "done", answer.message, datetime.now(UTC)
        else:
            job = answer.job
            row.job_id = job.id
    await session.merge(row)
    await session.commit()
    return LinkRunAnswer(run=_public(row), job=job)
