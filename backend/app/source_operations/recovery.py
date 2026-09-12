"""What a stopped process leaves in a source operation, settled before the generic sweep (D123).

A target recorded as in progress may have committed in the source without the
answer reaching the application, so it becomes unknown rather than pending, and
its connection's cached answers are dropped. Nothing is replayed (D81).
"""

import logging
import uuid

from pydantic import ValidationError
from sqlmodel import col, select

from app.adapters.cache import DataCache
from app.core.db import async_session_maker
from app.jobs.models import TERMINAL, Job
from app.source_operations.handler import KIND
from app.source_operations.models import SourceOperation

logger = logging.getLogger(__name__)

UNCONFIRMED = "The server stopped while this target was in progress; its outcome is unknown"


async def settle_interrupted_operations(cache: DataCache) -> int:
    """Run before `settle_stranded`, which ends the jobs themselves; says how many there were."""
    stranded: list[Job] = []
    connectors: set[uuid.UUID] = set()
    try:
        async with async_session_maker() as session:
            stranded = list((await session.exec(
                select(Job).where(Job.kind == KIND).where(col(Job.state).not_in(TERMINAL))
            )).all())
            for job in stranded:
                if job.subject_id is not None:
                    connectors.add(job.subject_id)
                try:
                    operation = SourceOperation.model_validate(job.parameters)
                except ValidationError:
                    continue
                for record in operation.targets:
                    if record.outcome == "running":
                        record.outcome, record.message = "unknown", UNCONFIRMED
                job.parameters = operation.model_dump(mode="json")
                session.add(job)
            await session.commit()
        for connector_id in connectors:
            await cache.invalidate_connector(connector_id)
    except Exception:
        # A failed sweep must not stop the application from serving; the
        # generic sweep still ends the jobs.
        logger.exception("Settling interrupted source operations failed")
        return 0
    return len(stranded)
