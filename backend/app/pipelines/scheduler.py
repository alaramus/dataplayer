"""Starting pipelines when their schedules come (D179).

In the one process (D124), every half minute: a schedule whose time has
come starts the Run of D177 as the pipeline's owner, and a run Run would
refuse is noted as skipped. A time that passed while the server was off is
noted as missed when it starts again, and nothing is caught up. The notes are
rows of the pipeline's history (D180).
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings as app_settings
from app.core.db import async_session_maker
from app.jobs.runner import JobRunner
from app.pipelines.models import Pipeline, PipelineContent, content_of
from app.pipelines.runs import start_run
from app.pipelines.schedule import (
    KEPT_NOTES,
    NoteKind,
    PipelineSchedule,
    ScheduleNote,
    SchedulePublic,
    ScheduleSettings,
)
from app.pipelines.timing import next_time
from app.realtime.topics import TopicSet
from app.users.models import User

logger = logging.getLogger(__name__)

# How late a time may be when the server comes back and still run: a restart
# takes seconds, and a night's run lost to one would be a surprise.
MISSED_AFTER = timedelta(minutes=2)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _settings_of(row: PipelineSchedule) -> ScheduleSettings | None:
    try:
        return ScheduleSettings.model_validate(row.settings)
    except ValidationError:
        return None


def public(row: PipelineSchedule | None) -> SchedulePublic:
    if row is None:
        return SchedulePublic()
    return SchedulePublic(settings=_settings_of(row), next_at=row.next_at)


async def save(
    session: AsyncSession, pipeline_id: uuid.UUID, chosen: ScheduleSettings, now: datetime
) -> SchedulePublic:
    """Keep the owner's choice, and when it comes next from now."""
    row = await session.get(PipelineSchedule, pipeline_id)
    before = None if row is None else _settings_of(row)
    if row is None:
        row = PipelineSchedule(pipeline_id=pipeline_id, settings={}, counted_from=now)
    if chosen.enabled and before != chosen:
        # Switched on, or changed: an interval counts from now.
        row.counted_from = now
    row.settings = chosen.model_dump(mode="json")
    row.next_at = next_time(chosen, now, row.counted_from) if chosen.enabled else None
    session.add(row)
    await session.commit()
    return public(row)


async def _noted(
    session: AsyncSession, pipeline_id: uuid.UUID, kind: NoteKind, at: datetime, reason: str
) -> None:
    """A time that came and started nothing, kept among the last hundred; the
    caller commits."""
    session.add(ScheduleNote(pipeline_id=pipeline_id, kind=kind, at=at, reason=reason[:512]))
    await session.flush()
    about = col(ScheduleNote.pipeline_id) == pipeline_id
    newest = (
        select(ScheduleNote.id)
        .where(about)
        .order_by(col(ScheduleNote.at).desc(), col(ScheduleNote.id).desc())
        .limit(KEPT_NOTES)
    )
    stale = list((await session.exec(
        select(ScheduleNote.id).where(about, col(ScheduleNote.id).not_in(newest.scalar_subquery()))
    )).all())
    if stale:
        await session.exec(delete(ScheduleNote).where(col(ScheduleNote.id).in_(stale)))


def _why(refused: HTTPException) -> str:
    """Why Run refused, as the schedule says it skipped. No request starts a
    scheduled run, so this and what the run writes are English (D226)."""
    if refused.status_code == 409:
        return "the previous run was still going"
    if refused.status_code == 429:
        return f"{app_settings.PIPELINE_MAX_ACTIVE} pipelines were already running"
    detail = refused.detail
    said = str(detail["message"]) if isinstance(detail, dict) and "message" in detail else "it could not start"
    said = said.removeprefix("Nothing ran: ")
    return said[:1].lower() + said[1:]


class Scheduler:
    """What comes due, found and started. The clock is given, so a test can
    say what time it is."""

    def __init__(
        self, runner: JobRunner, topics: TopicSet, now: Callable[[], datetime] = _utc_now
    ) -> None:
        self._runner = runner
        self._topics = topics
        self._now = now

    async def settle_missed(self) -> int:
        """Note every time that passed while the server was off, and move on."""
        now = self._now()
        async with async_session_maker() as session:
            found = await session.exec(
                select(PipelineSchedule).where(col(PipelineSchedule.next_at) < now - MISSED_AFTER)
            )
            missed = list(found.all())
            for row in missed:
                chosen = _settings_of(row)
                if chosen is None or row.next_at is None:
                    row.next_at = None
                else:
                    await _noted(session, row.pipeline_id, "missed", row.next_at, "the server was off")
                    row.next_at = next_time(chosen, now, row.counted_from)
                session.add(row)
            await session.commit()
        return len(missed)

    async def tick(self) -> int:
        """Start every run whose time has come; how many came."""
        now = self._now()
        async with async_session_maker() as session:
            found = await session.exec(
                select(PipelineSchedule.pipeline_id).where(col(PipelineSchedule.next_at) <= now)
            )
            due = list(found.all())
        for pipeline_id in due:
            await self._due(pipeline_id, now)
        return len(due)

    async def forever(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed look is not a reason to stop looking: the next one
                # finds what this one did not start.
                logger.exception("Starting scheduled pipelines failed")
            await asyncio.sleep(app_settings.SCHEDULE_TICK_SECONDS)

    async def _due(self, pipeline_id: uuid.UUID, now: datetime) -> None:
        async with async_session_maker() as session:
            row = await session.get(PipelineSchedule, pipeline_id)
            pipeline = await session.get(Pipeline, pipeline_id)
            if row is None or row.next_at is None or row.next_at > now or pipeline is None:
                return
            chosen = _settings_of(row)
            owner = await session.get(User, pipeline.owner_id)
            came, counted_from = row.next_at, row.counted_from
        skipped: str | None = None
        if chosen is not None and owner is not None:
            # A session of its own: a refused admission rolls it back.
            async with async_session_maker() as running:
                try:
                    await start_run(
                        running,
                        owner,
                        self._runner,
                        self._topics,
                        pipeline,
                        content_of(pipeline) or PipelineContent(),
                        scheduled_for=came,
                    )
                except HTTPException as refused:
                    skipped = _why(refused)
        async with async_session_maker() as session:
            row = await session.get(PipelineSchedule, pipeline_id)
            # Changed or switched off while it was starting: that answer stands.
            if row is None or row.next_at != came:
                return
            if skipped is not None:
                await _noted(session, pipeline_id, "skipped", came, skipped)
            row.next_at = None if chosen is None else next_time(chosen, now, counted_from)
            session.add(row)
            await session.commit()


@asynccontextmanager
async def scheduling(runner: JobRunner, topics: TopicSet) -> AsyncIterator[None]:
    """Look for due schedules for as long as the application runs."""
    scheduler = Scheduler(runner, topics)
    try:
        missed = await scheduler.settle_missed()
    except Exception:
        logger.exception("Noting missed schedules failed")
    else:
        if missed:
            logger.info("Noted %d schedules missed while the server was off", missed)
    task = asyncio.create_task(scheduler.forever())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
