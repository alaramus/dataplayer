import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.adapters.cache import DataCache, MemoryDataCache
from app.adapters.redis.cache import RedisDataCache
from app.adapters.resources import ResourceStore
from app.api.main import api_router
from app.core.config import settings
from app.jobs.recovery import settle_stranded
from app.jobs.runner import JobRunner
from app.queries.cleanup import sweeping
from app.queries.execution import QueryRunner
from app.queries.results import QueryResults
from app.queries.sessions import QuerySessions
from app.realtime import topics
from app.services.backups import handlers as backup_handlers
from app.services.docker import DockerEngine
from app.services.engine import SWITCHED_OFF_MESSAGE, NoEngine, ServiceEngine
from app.services.jobs import handlers as service_handlers

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


def build_data_cache() -> DataCache:
    if settings.DATA_CACHE_BACKEND == "memory":
        return MemoryDataCache(max_entries=settings.DATA_CACHE_MAX_ENTRIES)
    url = settings.DATA_CACHE_REDIS_URL
    encoded_key = settings.DATA_CACHE_SECRET_KEY
    if url is None or encoded_key is None:
        # Settings validation normally makes this unreachable. Keeping the
        # assembly boundary explicit makes a partially constructed Settings
        # double fail closed as well.
        raise RuntimeError("Redis cache settings are incomplete")
    cache = RedisDataCache.from_url(
        url.get_secret_value(),
        deployment=settings.DATA_CACHE_DEPLOYMENT,
        encryption_key=base64.urlsafe_b64decode(encoded_key),
        timeout_seconds=settings.DATA_CACHE_REDIS_TIMEOUT_SECONDS,
        max_entries=settings.DATA_CACHE_MAX_ENTRIES,
    )
    cache.start()
    return cache


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
    application.state.data_cache = build_data_cache()
    application.state.topics = topics.build_all()
    # Captured results and the runs producing them: both process-local, both
    # holding what cannot cross a process — memory and a connection (D64).
    application.state.query_results = QueryResults(
        max_bytes=settings.QUERY_RESULT_STORE_MAX_BYTES,
        ttl_seconds=settings.QUERY_RESULT_TTL_SECONDS,
    )
    application.state.query_runner = QueryRunner(
        results=application.state.query_results,
        cache=application.state.data_cache,
    )
    # The work the server owns, and the runtime it may ask to do it. Whether
    # this installation runs services at all is decided here and nowhere else;
    # whether the runtime is actually reachable is asked of the engine when
    # somebody asks, because a daemon can go away while the server runs (D82).
    engine: ServiceEngine = (
        DockerEngine(settings.DOCKER_SOCKET)
        if settings.SERVICES_ENABLED
        else NoEngine(SWITCHED_OFF_MESSAGE)
    )
    application.state.service_engine = engine
    application.state.job_runner = JobRunner(
        {**service_handlers(engine), **backup_handlers(engine)}
    )
    # What the last stop left mid-flight is ended before anything new starts.
    await settle_stranded()
    # Transactions held open for somebody: a connection each, so the lease is
    # what makes a forgotten one end (D66).
    application.state.query_sessions = QuerySessions(
        idle_seconds=settings.QUERY_TRANSACTION_IDLE_SECONDS
    )
    # Emptying query Trash is the one thing here that is not a resource: it is
    # a timer, and it belongs to the application for the same reason a pool
    # does — nothing else outlives a request.
    try:
        async with sweeping(application.state.query_sessions):
            yield
    finally:
        await application.state.query_sessions.aclose()
        await application.state.job_runner.aclose()
        await application.state.query_runner.aclose()
        await application.state.query_results.aclose()
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
