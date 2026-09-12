"""What a restart leaves in a source operation (D81, D123)."""

import uuid
from typing import cast
from unittest.mock import MagicMock

from app.adapters.cache import DataCache
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job
from app.jobs.runner import recover_interrupted
from app.source_operations.models import SourceOperation
from app.source_operations.recovery import UNCONFIRMED, settle_interrupted_operations
from app.users.models import User
from tests.source_operations.records import operation, read


async def _stranded(owner: User, subject: uuid.UUID, parameters: dict[str, object], state: str) -> Job:
    async with async_session_maker() as session:
        job = await crud.create(
            session, owner_id=owner.id, kind="source.operation", subject_id=subject,
            step_count=3, parameters=parameters,
        )
        job.state = state
        session.add(job)
        await session.commit()
        return job


async def test_a_target_left_in_progress_becomes_unknown_and_its_connection_is_forgotten(
    owner: User, cache: MagicMock,
) -> None:
    subject = uuid.uuid4()
    recorded = operation(["one", "two", "three"], outcomes=["completed", "running", "pending"])
    job = await _stranded(owner, subject, recorded.model_dump(mode="json"), "running")

    assert await settle_interrupted_operations(cast(DataCache, cache)) == 1
    cache.invalidate_connector.assert_awaited_once_with(subject)
    stored = await read(job.id)
    settled = SourceOperation.model_validate(stored.parameters)
    assert [record.outcome for record in settled.targets] == ["completed", "unknown", "pending"]
    assert settled.targets[1].message == UNCONFIRMED
    # Ending the job is the generic sweep's, which runs afterwards and replays nothing.
    assert stored.state == "running"
    async with async_session_maker() as session:
        await recover_interrupted(session)
    assert (await read(job.id)).state == "interrupted"


async def test_finished_jobs_are_left_and_unreadable_ones_still_forget_their_connection(
    owner: User, cache: MagicMock,
) -> None:
    finished_subject, unreadable_subject = uuid.uuid4(), uuid.uuid4()
    finished = operation(["one"], outcomes=["running"]).model_dump(mode="json")
    done = await _stranded(owner, finished_subject, finished, "succeeded")
    await _stranded(owner, unreadable_subject, {"nonsense": True}, "queued")

    assert await settle_interrupted_operations(cast(DataCache, cache)) == 1
    cache.invalidate_connector.assert_awaited_once_with(unreadable_subject)
    assert (await read(done.id)).parameters == finished
