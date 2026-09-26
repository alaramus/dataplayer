"""Pasting into another connection: at once, or as a transfer job (D164, D168).

What a paste does is `run.py`'s; this is the door Paste and the pair window
knock at.
"""

import uuid

from fastapi import APIRouter

from app.adapters.cache import DataCacheDep
from app.adapters.resources import ResourcesDep
from app.connectors.paste.models import PasteResult, PasteRun
from app.core.db import SessionDep
from app.jobs.runner import JobRunnerDep
from app.realtime.topics import TopicsDep
from app.transfers.run import Carrying, PasteAnswer, PasteStarted, run_paste
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("/{connector_id}/paste", response_model=PasteAnswer)
async def paste(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteResult | PasteStarted:
    carrying = Carrying(session, current_user, resources, data_cache, runner, topics)
    return await run_paste(carrying, connector_id, request)
