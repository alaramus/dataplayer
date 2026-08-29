from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.adapters.cache import DataCache
from app.adapters.resources import ResourceStore
from app.api.main import api_router
from app.core.config import settings
from app.realtime import topics

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """What outlives a request is created here and closed here.

    An adapter is built per request, so a connection pool cannot belong to
    one. It belongs to the application, and this is the only place that knows
    it exists — the container names no driver, and no driver reaches for a
    module global.
    """
    application.state.resources = ResourceStore(
        max_entries=settings.POOL_MAX_POOLS,
        max_idle_seconds=settings.POOL_MAX_IDLE_SECONDS,
    )
    application.state.data_cache = DataCache(max_entries=settings.DATA_CACHE_MAX_ENTRIES)
    application.state.topics = topics.build_all()
    try:
        yield
    finally:
        await application.state.topics.aclose()
        await application.state.data_cache.aclose()
        await application.state.resources.aclose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # A response header a browser does not safelist is invisible to the page
    # unless it is named here. In development the frontend is served from its
    # own port, so a download would silently fall back to a guessed filename
    # while working in a deployment, where the same build is same-origin.
    expose_headers=["Content-Disposition", "X-Data-Cache"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Serving the built frontend is enabled only when a build exists: without the
# check app.frontend raises RuntimeError and the application stops importing,
# including in tests, which do not need a build.
if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
