"""`POST /search`: the words in the body, the answer a stream of lines (D200, D201).

The words travel in the body so that no access line carries them, and the
answer is JSON Lines — one line per cell as it finishes — so a screen draws
what is found while the rest is still being asked.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db import SessionDep
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
