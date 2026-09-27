"""A pipeline's history (D180): its runs and the times its schedule came and
started nothing, newest first, a hundred of each.

A run is its job (D177) and a skip or a miss is a note of the schedule
(D179); this only lays them side by side.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.jobs.models import Job, JobState
from app.pipelines.models import Pipeline
from app.pipelines.runs import KEPT_RUNS, runs_of
from app.pipelines.schedule import KEPT_NOTES, NoteKind, ScheduleNote


class _Started(BaseModel):
    """What the history reads of a run's record: whether a schedule started it."""

    model_config = ConfigDict(extra="ignore")

    scheduled_for: datetime | None = None


class HistoryRun(BaseModel):
    kind: Literal["run"] = "run"
    job_id: uuid.UUID
    state: JobState
    message: str | None
    started_at: datetime
    finished_at: datetime | None
    # Started by the schedule rather than by Run (D179).
    scheduled: bool


class HistoryNote(BaseModel):
    kind: NoteKind
    at: datetime
    reason: str


HistoryRow = Annotated[HistoryRun | HistoryNote, Field(discriminator="kind")]


class PipelineHistory(BaseModel):
    rows: list[HistoryRow]


def _scheduled(job: Job) -> bool:
    try:
        return _Started.model_validate(job.parameters or {}).scheduled_for is not None
    except ValidationError:
        return False


def _run(job: Job) -> HistoryRun:
    return HistoryRun(
        job_id=job.id,
        # The column is a string; only the runner writes it, from JobState.
        state=cast(JobState, job.state),
        message=job.message,
        started_at=job.started_at or job.created_at,
        finished_at=job.finished_at,
        scheduled=_scheduled(job),
    )


def _when(row: HistoryRun | HistoryNote) -> datetime:
    return row.started_at if isinstance(row, HistoryRun) else row.at


async def history(session: AsyncSession, pipeline: Pipeline) -> PipelineHistory:
    jobs = (await session.exec(runs_of(pipeline).limit(KEPT_RUNS))).all()
    notes = (
        await session.exec(
            select(ScheduleNote)
            .where(ScheduleNote.pipeline_id == pipeline.id)
            .order_by(col(ScheduleNote.at).desc())
            .limit(KEPT_NOTES)
        )
    ).all()
    rows: list[HistoryRun | HistoryNote] = [_run(job) for job in jobs]
    rows += [
        # The column is a string; only the scheduler writes it, from NoteKind.
        HistoryNote(kind=cast(NoteKind, note.kind), at=note.at, reason=note.reason)
        for note in notes
    ]
    return PipelineHistory(rows=sorted(rows, key=_when, reverse=True))
