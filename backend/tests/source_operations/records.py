"""A source operation record as a test writes it down."""

import uuid
from collections.abc import Sequence

from app.adapters.operations import OperationTarget
from app.core.access import Access
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.source_operations.models import SourceOperation, TargetOutcome, TargetRecord

PARAMS = {"ends_by": "2026-01-15T00:00:00Z"}
UNIT = "a" * 64


def operation(
    names: Sequence[str], *, revision: str | None = None,
    outcomes: Sequence[TargetOutcome] | None = None, requires: Access = "structure",
    action: str = "fake_convert",
) -> SourceOperation:
    settled = outcomes if outcomes is not None else ["pending"] * len(names)
    return SourceOperation(
        action=action, title="Convert things", node_id="lab.events", params=dict(PARAMS),
        requires=requires, connector_revision=revision, summary=f"Convert {len(names)} things",
        unit_fingerprint=UNIT,
        targets=[
            TargetRecord(target=OperationTarget(schema_name="lab", name=name), outcome=outcome)
            for name, outcome in zip(names, settled, strict=True)
        ],
    )


async def read(job_id: uuid.UUID) -> Job:
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job
