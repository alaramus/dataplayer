"""`POST /search`: the words in the body, the answer a stream of lines (D200, D201).

The words travel in the body so that no access line carries them, and the
answer is JSON Lines — one line per cell as it finishes — so a screen draws
what is found while the rest is still being asked.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db import SessionDep
from app.jobs.models import JobPublic
from app.jobs.runner import JobRunnerDep
from app.realtime.topics import TopicsDep
from app.search import contents
from app.search.contents import ContentsAnswer, ContentsMemory, ContentsRequest
from app.search.engine import Answer, ScopeNotFound, SearchEngine
from app.search.models import SearchLine, SearchRequest
from app.users.deps import CurrentUser

router = APIRouter(prefix="/search", tags=["search"])


def _engine(request: Request) -> SearchEngine:
    engine: SearchEngine = request.app.state.search_engine
    return engine


async def _prepared(
    body: SearchRequest,
    session: SessionDep,
    current_user: CurrentUser,
    engine: Annotated[SearchEngine, Depends(_engine)],
) -> Answer:
    # A dependency rather than the first lines of the handler: the handler is
    # a generator, and a refusal has to be answered before a stream begins.
    try:
        return await engine.prepare(session, current_user, body)
    except ScopeNotFound:
        raise HTTPException(status_code=404, detail="Connector not found")


@router.post("")
async def search(
    answer: Annotated[Answer, Depends(_prepared)],
) -> AsyncIterator[SearchLine]:
    """Search everything this person may see, as a stream of lines.

    First the plan, then one line per cell as it finishes — its outcome and
    its hits — then the best matches, then a closing line. One cell failing,
    late or skipped never fails the answer; it says what happened to it.
    """
    async for line in answer.lines():
        yield line


def _memory(request: Request) -> ContentsMemory:
    memory: ContentsMemory = request.app.state.contents_memory
    return memory


ContentsMemoryDep = Annotated[ContentsMemory, Depends(_memory)]


@router.post("/contents", response_model=JobPublic)
async def search_contents(
    body: ContentsRequest,
    session: SessionDep,
    current_user: CurrentUser,
    memory: ContentsMemoryDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
) -> JobPublic:
    """Look for words inside the files of chosen connections, as a job (S7).

    The words and what is found are held in memory for a while and never
    written to the job; one at a time per person. A connection the person has
    no standing on is answered as an unknown one.
    """
    try:
        return await contents.start(
            session, current_user, body, memory=memory, runner=runner, topics=topics
        )
    except contents.PlaceNotFound:
        raise HTTPException(status_code=404, detail="Connector not found") from None
    except contents.ContentsBusy:
        raise HTTPException(
            status_code=409,
            detail={"message": "A search inside files is already running — stop it or wait for it"},
        ) from None


@router.get("/contents/{job_id}", response_model=ContentsAnswer)
async def read_search_contents(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    memory: ContentsMemoryDep,
) -> ContentsAnswer:
    """What a search inside files found, while it is held; 404 unless it is the caller's."""
    found = await contents.answer(session, current_user, job_id, memory)
    if found is None:
        raise HTTPException(status_code=404, detail={"message": "No such job"})
    return found
