from typing import Any

from fastapi import APIRouter, Depends

from app.core.problems import Problem
from app.guide import reader
from app.users.deps import get_current_user

# Plain functions rather than coroutines: the first call reads the pages from
# disk, and FastAPI runs a plain handler in its thread pool.
router = APIRouter(
    prefix="/guide",
    tags=["guide"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/", response_model=list[reader.GuidePageInfo])
def read_guide_pages() -> Any:
    """Every page of the user's guide, by key and title."""
    return [
        reader.GuidePageInfo(key=one.key, title=one.title)
        for one in reader.pages().values()
    ]


@router.get("/{key}", response_model=reader.GuidePage)
def read_guide_page(key: str) -> Any:
    """One page of the user's guide, as Markdown."""
    found = reader.page(key)
    if found is None:
        raise Problem(404, "guide.page_not_found")
    return found
