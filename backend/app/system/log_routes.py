from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.system.log_reader import LevelChoice, LogPage, ProcessChoice, read_page
from app.users.deps import get_current_active_superuser

# The log names every request, every connection that failed and why: the
# installation's, and a superuser's to read (D184).
router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(get_current_active_superuser)],
)


# A plain function: it reads files, and FastAPI runs a plain handler in its
# thread pool.
@router.get("/", response_model=LogPage)
def read_logs(
    level: LevelChoice = "all",
    process: ProcessChoice = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
    before: datetime | None = None,
    after: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> Any:
    """The newest entries of the server's log that match, newest first."""
    folder = settings.LOG_DIR
    if folder is None:
        return LogPage(kept=False, entries=[], more=False)
    return read_page(
        folder, level=level, process=process, text=q, before=before, after=after, limit=limit
    )
