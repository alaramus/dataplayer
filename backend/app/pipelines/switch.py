"""A pipeline switched on or off with one button (D362).

On, its continuous links are carried by a follower (D315) and its scheduled
links run at the schedule's times (D179); off, nothing runs by itself. The
switch is a row beside the pipeline, as the schedule is, so turning it does
not touch the canvas's version, and a restart starts a follower from it.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.core.problems import Problem
from app.core.translation import N_
from app.jobs.models import TERMINAL
from app.jobs.runner import JobRunner
from app.pipelines.follow import (
    FollowState,
    follow_state,
    followings_of,
    start_follower,
    stop_followers,
)
from app.pipelines.models import Pipeline, PipelineContent, PipelineSwitch, content_of
from app.pipelines.runs import lacking, refuse_lacking
from app.pipelines.schedule import PipelineSchedule, ScheduleSettings
from app.pipelines.timing import next_time
from app.realtime.topics import TopicSet
from app.users.models import User


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool


# What the status line says first, in this order (D364): the screen words it.
StatusKind = Literal["empty", "lacking", "no_schedule", "retrying", "on", "ready"]


class PipelineStatus(BaseModel):
    kind: StatusKind
    # The link the sentence is about, which pressing it opens.
    link_id: uuid.UUID | None = None
    # Run's refusal for a lacking link; the last failure for a retrying one.
    message: str | None = None
    continuous: int = 0
    scheduled: int = 0
    # While on: since when, the last time anything was carried, the
    # schedule's next time.
    since: datetime | None = None
    last_at: datetime | None = None
    next_at: datetime | None = None


class SwitchState(BaseModel):
    on: bool
    status: PipelineStatus
    follow: FollowState = Field(default_factory=FollowState)


def _counts(content: PipelineContent) -> tuple[int, int]:
    continuous = sum(1 for link in content.links if link.runs == "continuous")
    return continuous, len(content.links) - continuous


async def _schedule(session: AsyncSession, pipeline_id: uuid.UUID) -> PipelineSchedule | None:
    row = await session.get(PipelineSchedule, pipeline_id)
    if row is None:
        return None
    try:
        ScheduleSettings.model_validate(row.settings)
    except ValidationError:
        return None
    return row


async def arm(session: AsyncSession, pipeline_id: uuid.UUID, on: bool, now: datetime) -> None:
    """The schedule's next time set from now as the pipeline is switched on,
    or cleared as it is switched off. The caller commits."""
    row = await session.get(PipelineSchedule, pipeline_id)
    if row is None:
        return
    try:
        chosen = ScheduleSettings.model_validate(row.settings)
    except ValidationError:
        chosen = None
    if on and chosen is not None:
        row.counted_from = now
        row.next_at = next_time(chosen, now, now)
    else:
        row.next_at = None
    session.add(row)


def status_of(
    content: PipelineContent,
    on: bool,
    since: datetime | None,
    schedule: PipelineSchedule | None,
    follow: FollowState,
) -> PipelineStatus:
    """The one thing the status line says, the first that applies."""
    continuous, scheduled = _counts(content)
    counted = PipelineStatus(kind="empty", continuous=continuous, scheduled=scheduled)
    if not content.links:
        return counted
    found = lacking(content)
    if found:
        first = found[0]
        return counted.model_copy(
            update={"kind": "lacking", "link_id": first.link_id, "message": first.sentence}
        )
    if scheduled and schedule is None:
        return counted.model_copy(update={"kind": "no_schedule"})
    if not on:
        return counted.model_copy(update={"kind": "ready"})
    drawn = {link.id for link in content.links if link.runs == "continuous"}
    if follow.running:
        retrying = next(
            (one for one in follow.links if one.link_id in drawn and one.state == "retrying"),
            None,
        )
        if retrying is not None:
            return counted.model_copy(
                update={
                    "kind": "retrying",
                    "link_id": retrying.link_id,
                    "message": retrying.last_error,
                }
            )
    carried = [one.last_at for one in follow.links if one.link_id in drawn and one.last_at]
    return counted.model_copy(
        update={
            "kind": "on",
            "since": since,
            "last_at": max(carried) if carried else None,
            "next_at": None if schedule is None else schedule.next_at,
        }
    )


async def switch_state(
    session: AsyncSession, pipeline: Pipeline, content: PipelineContent
) -> SwitchState:
    row = await session.get(PipelineSwitch, pipeline.id)
    on = row is not None and row.on
    follow = await follow_state(session, pipeline)
    schedule = await _schedule(session, pipeline.id)
    return SwitchState(
        on=on,
        status=status_of(content, on, row.changed_at if row is not None else None, schedule, follow),
        follow=follow,
    )


async def switch(
    session: AsyncSession,
    user: User,
    runner: JobRunner,
    topics: TopicSet,
    pipeline: Pipeline,
    content: PipelineContent,
    on: bool,
    now: datetime | None = None,
) -> SwitchState:
    """Switched on — refused whole, before anything starts, for what it
    lacks — or off, its follower stopped and its schedule disarmed."""
    moment = now or _utc_now()
    row = await session.get(PipelineSwitch, pipeline.id)
    if row is None:
        row = PipelineSwitch(pipeline_id=pipeline.id)
    if on:
        if not content.links:
            raise Problem(422, "pipelines.no_links")
        refuse_lacking(content, N_("Not switched on: {needs}"))
        continuous, scheduled = _counts(content)
        if scheduled and await _schedule(session, pipeline.id) is None:
            raise Problem(422, "pipelines.no_schedule")
        if continuous:
            await start_follower(session, user, runner, topics, pipeline)
    else:
        await stop_followers(session, runner, pipeline)
    await arm(session, pipeline.id, on, moment)
    if row.on != on:
        row.changed_at = moment
    row.on = on
    session.add(row)
    await session.commit()
    return await switch_state(session, pipeline, content)


async def ensure_followers(runner: JobRunner, topics: TopicSet) -> int:
    """Start a follower for every pipeline switched on with a continuous link
    and none running; how many were started. A follower its owner stopped
    from the footer since the pipeline was switched on switches it off."""
    async with async_session_maker() as session:
        switched = list(
            (await session.exec(select(PipelineSwitch).where(col(PipelineSwitch.on)))).all()
        )
    started = 0
    for row in switched:
        async with async_session_maker() as session:
            pipeline = await session.get(Pipeline, row.pipeline_id)
            if pipeline is None:
                continue
            content = content_of(pipeline) or PipelineContent()
            if not any(link.runs == "continuous" for link in content.links):
                continue
            newest = (await session.exec(followings_of(pipeline).limit(1))).first()
            if newest is not None and newest.state not in TERMINAL:
                continue
            kept = await session.get(PipelineSwitch, row.pipeline_id)
            if kept is None or not kept.on:
                continue
            if (
                newest is not None
                and newest.state == "cancelled"
                and (newest.finished_at or newest.created_at) >= kept.changed_at
            ):
                kept.on = False
                kept.changed_at = _utc_now()
                session.add(kept)
                await arm(session, pipeline.id, False, kept.changed_at)
                await session.commit()
                continue
            owner = await session.get(User, pipeline.owner_id)
            if owner is None:
                continue
            try:
                if await start_follower(session, owner, runner, topics, pipeline) is not None:
                    started += 1
                await session.commit()
            except Problem:
                # Over a bound now; the next look tries again.
                await session.rollback()
    return started
