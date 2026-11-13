"""A pipeline following its topics (D315).

One job a pipeline, kind `pipeline.follow`, that runs until it is stopped:
every few seconds it asks each link that runs continuously (D362) whether its
source holds anything unread, and carries out that link's step when it does —
the step a run carries out, through the same code. Whether a pipeline is on is
a row beside it (`switch.py`), so a restart, which replays no job (D81),
starts a new follower from the row rather than resuming the old one.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal, TypeVar

from anyio import to_thread
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCache
from app.adapters.protocol import (
    AdapterError,
    NodeNotFound,
    SupportsOwnReader,
    SupportsReadingOn,
)
from app.adapters.resources import ResourceStore
from app.connectors.paste.kinds import PastesAsJob
from app.connectors.paste.registry import kind_named
from app.connectors.paste.transfer import TransferStopped
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.problems import Problem
from app.core.translation import N_, say
from app.jobs import crud as job_crud
from app.jobs.models import TERMINAL, Job, JobKind
from app.jobs.runner import JobFailed, JobRunner, Progress
from app.pipelines.handler import StepFailed, open_end, said_of
from app.pipelines.models import (
    Link,
    Pipeline,
    PipelineContent,
    content_of,
)
from app.pipelines.order import ordered
from app.pipelines.record import STEP_SAYS, clipped
from app.pipelines.results import Foresight
from app.pipelines.runs import KEPT_RUNS, link_step
from app.realtime.topics import TopicSet
from app.transfers.run import planned
from app.users.models import User

logger = logging.getLogger(__name__)

KIND: JobKind = "pipeline.follow"
FOLLOWING = N_("following its topics")

# How long a failing link waits before it is tried again: after its first
# failure, its second, its third, and from then on.
RETRY_SECONDS = (5, 30, 60, 300)

# A follower's record is written at most this often while links carry.
WRITE_SECONDS = 1.0

T = TypeVar("T")

LinkState = Literal["idle", "carrying", "retrying"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FollowedLink(_Strict):
    """One continuous link, and what it carried while its pipeline was on."""

    link_id: uuid.UUID
    title: str = Field(max_length=255)
    carried: int = 0
    last_at: datetime | None = None
    failures: int = 0
    last_error: str | None = Field(default=None, max_length=STEP_SAYS)
    retry_at: datetime | None = None
    state: LinkState = "idle"


class FollowRecord(_Strict):
    """A following as its job keeps it: one row of the history (D180)."""

    version: Literal[1] = 1
    pipeline_id: uuid.UUID
    pipeline_name: str = Field(max_length=255)
    links: list[FollowedLink] = Field(default_factory=list)

    def entry(self, link: Link) -> FollowedLink:
        found = next((one for one in self.links if one.link_id == link.id), None)
        if found is None:
            found = FollowedLink(link_id=link.id, title=link.title[:255])
            self.links.append(found)
        return found

    def told(self) -> str:
        carried = sum(one.carried for one in self.links)
        return say("Followed; {count} messages carried", count=carried)


def retry_after(failures: int) -> timedelta:
    return timedelta(seconds=RETRY_SECONDS[min(failures, len(RETRY_SECONDS)) - 1])


class _Quiet:
    """A transfer's report with nobody to tell: a follower writes its own record."""

    async def in_thread(self, work: Callable[[], T]) -> T:
        return await to_thread.run_sync(work)

    async def progressed(self) -> None:
        return None

    async def removing(self) -> None:
        return None


class FollowPipeline:
    kind: ClassVar[JobKind] = KIND
    steps: ClassVar[tuple[str, ...]] = (FOLLOWING,)

    def __init__(
        self,
        cache: DataCache,
        resources: ResourceStore | None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._cache = cache
        self._resources = resources
        self._now = now

    async def carry_out(self, job: Job, progress: Progress) -> str:
        record = _loaded(job)
        await progress.reached(FOLLOWING)
        written = time.monotonic()
        pending = False
        while True:
            content = await _content(record.pipeline_id)
            if content is None:
                return record.told()
            for placed in ordered(content):
                link = placed.link
                if link.runs != "continuous":
                    continue
                pending = (
                    await self._turn(job, content, link, record.entry(link)) or pending
                )
            if pending and time.monotonic() - written >= WRITE_SECONDS:
                job.parameters = record.model_dump(mode="json")
                await progress.reached(FOLLOWING)
                written, pending = time.monotonic(), False
            await asyncio.sleep(settings.PIPELINE_FOLLOW_SECONDS)

    def stopped_message(self, job: Job) -> str | None:
        try:
            return FollowRecord.model_validate(job.parameters).told()
        except ValidationError:
            return None

    async def _turn(
        self, job: Job, content: PipelineContent, link: Link, entry: FollowedLink
    ) -> bool:
        """One look at one link; whether its entry changed."""
        now = self._now()
        if entry.retry_at is not None and now < entry.retry_at:
            return False
        try:
            carried = await self.carried(job.owner_id, content, link)
        except StepFailed as failed:
            entry.failures += 1
            entry.last_error = clipped(failed.message, STEP_SAYS)
            entry.retry_at = now + retry_after(entry.failures)
            entry.state = "retrying"
            return True
        changed = (
            entry.state != ("carrying" if carried else "idle") or entry.failures > 0
        )
        entry.failures, entry.last_error, entry.retry_at = 0, None, None
        entry.state = "carrying" if carried else "idle"
        if carried:
            entry.carried += carried
            entry.last_at = now
            return True
        return changed

    async def carried(
        self, owner_id: uuid.UUID, content: PipelineContent, link: Link
    ) -> int:
        """Carry out one followed link's step if its source holds anything
        unread; how many rows it read."""
        kind = kind_named(link.kind)
        if not isinstance(kind, PastesAsJob):
            raise StepFailed(say("{kind} cannot run", kind=say(kind.title)))
        step = link_step(content, link, Foresight(content))
        async with async_session_maker() as session:
            owner = await session.get(User, owner_id)
            if owner is None:
                raise StepFailed(say("Its owner is no longer here"))
            source = await open_end(
                session,
                owner,
                self._resources,
                step.paste.source_connector_id,
                kind.source_requires,
                step.source_connection,
            )
            destination = await open_end(
                session,
                owner,
                self._resources,
                step.destination_connector_id,
                kind.destination_requires,
                step.destination_connection,
            )
            node = step.paste.source_node_ids[0]
            if not isinstance(source, SupportsReadingOn) or not source.reads_on(node):
                raise StepFailed(say("Only a link reading a topic follows it"))
            if not kind.serves(source, destination):
                raise StepFailed(
                    say(
                        "{kind} is not possible between these connections",
                        kind=say(kind.title),
                    )
                )
            try:
                if isinstance(source, SupportsOwnReader):
                    # Its queue must be there before what waits in it is asked (D337).
                    await source.prepare_reader(
                        node, step.paste.reader or "", step.paste.binding_key
                    )
                span = await source.unread(
                    node, step.paste.reader or "", step.paste.start
                )
            except AdapterError as failure:
                raise StepFailed(failure.message) from None
            except NodeNotFound:
                raise StepFailed(say("The copied node no longer exists")) from None
            except ValueError as failure:
                raise StepFailed(str(failure)) from None
            # Nothing unread: nothing to write. A reader with no bookmark runs
            # once anyway, so its start choice is kept and a table is made.
            if span.count == 0 and not span.fresh:
                return 0
            try:
                transfer = await planned(
                    session,
                    kind,
                    source,
                    destination,
                    step.destination_connector_id,
                    step.paste,
                )
            except HTTPException as refused:
                raise StepFailed(said_of(refused)) from None
        try:
            await kind.transfer(source, destination, transfer, _Quiet())
        except TransferStopped as stopped:
            raise StepFailed(kind.told(transfer, stopped.message)) from None
        finally:
            await self._cache.invalidate_connector(step.destination_connector_id)
        return transfer.items[0].rows or 0


def _loaded(job: Job) -> FollowRecord:
    try:
        return FollowRecord.model_validate(job.parameters)
    except ValidationError:
        raise JobFailed(say("This following could not be read")) from None


async def _content(pipeline_id: uuid.UUID) -> PipelineContent | None:
    """The pipeline as kept now, or nothing once it is gone or off."""
    async with async_session_maker() as session:
        pipeline = await session.get(Pipeline, pipeline_id)
        if pipeline is None:
            return None
        return content_of(pipeline) or PipelineContent()


# --- the follower's state -------------------------------------------------------


class FollowedLinkPublic(BaseModel):
    link_id: uuid.UUID
    carried: int
    last_at: datetime | None
    failures: int
    last_error: str | None
    state: LinkState


class FollowState(BaseModel):
    """What the pipeline's newest follower did, link by link."""

    job_id: uuid.UUID | None = None
    running: bool = False
    started_at: datetime | None = None
    links: list[FollowedLinkPublic] = Field(default_factory=list)


def followings_of(pipeline: Pipeline) -> Any:
    return (
        select(Job)
        .where(Job.subject_id == pipeline.id)
        .where(Job.owner_id == pipeline.owner_id)
        .where(Job.kind == KIND)
        .order_by(col(Job.created_at).desc(), col(Job.id).desc())
    )


async def follow_state(session: AsyncSession, pipeline: Pipeline) -> FollowState:
    newest = (await session.exec(followings_of(pipeline).limit(1))).first()
    if newest is None:
        return FollowState()
    try:
        record = FollowRecord.model_validate(newest.parameters)
    except ValidationError:
        record = None
    return FollowState(
        job_id=newest.id,
        running=newest.state not in TERMINAL,
        started_at=newest.started_at or newest.created_at,
        links=[
            FollowedLinkPublic(
                link_id=one.link_id,
                carried=one.carried,
                last_at=one.last_at,
                failures=one.failures,
                last_error=one.last_error,
                state=one.state,
            )
            for one in (record.links if record is not None else [])
        ],
    )


async def stop_followers(session: AsyncSession, runner: JobRunner, pipeline: Pipeline) -> None:
    running = (
        await session.exec(followings_of(pipeline).where(col(Job.state).not_in(TERMINAL)))
    ).all()
    for job in running:
        await runner.cancel(job.id)


async def start_follower(
    session: AsyncSession,
    user: User,
    runner: JobRunner,
    topics: TopicSet,
    pipeline: Pipeline,
) -> Job | None:
    """A follower for the pipeline, unless one runs already; refused past the
    bounds. Commits nothing of the caller's but the job."""
    everyone = (
        await session.exec(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == KIND)
            .where(col(Job.state).not_in(TERMINAL))
        )
    ).one()
    record = FollowRecord(pipeline_id=pipeline.id, pipeline_name=pipeline.name[:255])
    try:
        if everyone >= settings.PIPELINE_FOLLOW_SERVER_MAX:
            raise Problem(
                429,
                "pipelines.following_server_full",
                count=settings.PIPELINE_FOLLOW_SERVER_MAX,
            )
        job = await job_crud.admit_within(
            session,
            owner_id=user.id,
            kind=KIND,
            limit=settings.PIPELINE_FOLLOW_MAX,
            subject_id=pipeline.id,
            step_count=len(runner.steps_of(KIND)),
            parameters=record.model_dump(mode="json"),
            alone=True,
        )
    except job_crud.SubjectBusy:
        # Following already: switching on again changes nothing.
        return None
    except job_crud.TooManyActive:
        raise Problem(
            429, "pipelines.too_many_following", count=settings.PIPELINE_FOLLOW_MAX
        ) from None
    await runner.launch(job, topics)
    await job_crud.forget_finished(
        session, kind=KIND, subject_id=pipeline.id, keep=KEPT_RUNS
    )
    return job
