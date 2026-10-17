import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from anyio import to_thread
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.adapters.cache import DataCache, MemoryDataCache
from app.adapters.explorer.copies import copies
from app.adapters.postgres.checkpoint_pool import checkpoint_pool
from app.adapters.redis.cache import RedisDataCache
from app.adapters.resources import ResourceStore
from app.ai.catalog import catalog
from app.ai.checkpoints import checkpointer
from app.ai.providers import ProviderChatModels
from app.ai.runner import AgentRunner, settle_interrupted
from app.ai.search import ChatTitles
from app.api.main import api_router
from app.connectors.health import unreachable_of
from app.core import logs
from app.core.config import settings
from app.core.failures import RecordFailures
from app.core.translation import RequestLanguage
from app.jobs.recovery import settle_stranded
from app.jobs.runner import JobRunner
from app.metrics.holder import StoreHolder
from app.metrics.jobs import handlers as metrics_handlers
from app.metrics.search import DashboardNames
from app.pipelines.handler import handlers as pipeline_handlers
from app.pipelines.scheduler import scheduling
from app.pipelines.search import PipelineNames
from app.queries.cleanup import sweeping
from app.queries.execution import QueryRunner
from app.queries.results import QueryResults
from app.queries.search import SavedQueries
from app.queries.sessions import QuerySessions
from app.realtime import topics
from app.search import kept
from app.search.connections import ConnectionRows
from app.search.contents import ContentsMemory
from app.search.contents import handlers as contents_handlers
from app.search.engine import SearchEngine, SearchLimits
from app.search.guide import GuidePages
from app.search.nodes import ConnectionSearch
from app.search.open_tabs import OpenTabs
from app.search.source_types import SourceTypes
from app.search.ssh_keys import SshKeys
from app.services.backups import handlers as backup_handlers
from app.services.docker import DockerEngine
from app.services.engine import SWITCHED_OFF_MESSAGE, NoEngine, ServiceEngine
from app.services.jobs import handlers as service_handlers
from app.services.restore_files import remove_stranded_snapshots
from app.services.search import ServiceNames, startable
from app.source_operations.handler import handlers as source_operation_handlers
from app.source_operations.recovery import settle_interrupted_operations
from app.transfers.handler import RunTransfer
from app.transfers.handler import handlers as transfer_handlers

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
    # What renames in DataPlayer tells the search its kept list is stale (D216).
    application.state.names_changed = kept.names_changed
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
        names=kept.names_changed,
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
    transfers = RunTransfer(
        application.state.data_cache, application.state.resources, kept.names_changed
    )
    # A search inside files holds its words and matches here, never in its
    # job's row, and forgets them a while after it ends (S7, D124).
    application.state.contents_memory = ContentsMemory(settings.SEARCH_CONTENTS_HELD_SECONDS)
    application.state.job_runner = JobRunner({
        **service_handlers(engine),
        **backup_handlers(engine),
        **source_operation_handlers(application.state.data_cache),
        **transfer_handlers(transfers),
        **pipeline_handlers(application.state.data_cache, application.state.resources, transfers),
        **metrics_handlers(engine),
        **contents_handlers(application.state.contents_memory, application.state.resources),
    })
    # One search over everything a person may see, asking a provider per kind
    # of thing the application keeps; a feature hands its own in here, and the
    # engine imports none of them (D197). The connections themselves are asked
    # through the pools already open, and skipped while the person's health
    # monitor sees them down (D200).
    application.state.search_engine = SearchEngine(
        [
            OpenTabs(),
            ConnectionRows(),
            SavedQueries(),
            PipelineNames(),
            DashboardNames(),
            ChatTitles(),
            ServiceNames(),
            SshKeys(),
            GuidePages(),
            SourceTypes(startable),
        ],
        SearchLimits.from_settings(),
        inside=ConnectionSearch(
            resources=application.state.resources,
            unreachable=partial(unreachable_of, application.state.topics),
        ),
    )
    # The web process reads the metrics store and never writes points (D127).
    application.state.metrics_stores = StoreHolder()
    # What the last stop left mid-flight is ended before anything new starts.
    # Source operations first: their targets say what became unknown before
    # the generic sweep ends the jobs (D123).
    await settle_interrupted_operations(application.state.data_cache)
    await settle_stranded()
    await to_thread.run_sync(remove_stranded_snapshots)
    # Copies of remote files a previous process held are nobody's now (D152).
    await to_thread.run_sync(copies().clear)
    # Transactions held open for somebody: a connection each, so the lease is
    # what makes a forgotten one end (D66).
    application.state.query_sessions = QuerySessions(
        idle_seconds=settings.QUERY_TRANSACTION_IDLE_SECONDS
    )
    # The agent's working state and the answers being written. The model list
    # is read here, so a broken file stops the start rather than a chat (D140).
    await settle_interrupted()
    async with checkpoint_pool(
        str(settings.DATABASE_URL), max_size=settings.AI_CHECKPOINT_POOL_SIZE
    ) as pool:
        application.state.agent_runner = AgentRunner(
            checkpointer=checkpointer(pool),
            chat_models=ProviderChatModels(),
            topics=application.state.topics,
            catalog=catalog(),
            resources=application.state.resources,
            data_cache=application.state.data_cache,
            search_engine=application.state.search_engine,
        )
        # Run history retention is timer driven and belongs to the application;
        # nothing else outlives a request.
        try:
            async with (
                sweeping(application.state.query_sessions),
                scheduling(application.state.job_runner, application.state.topics),
            ):
                yield
        finally:
            await application.state.agent_runner.aclose()
            await _close_the_rest(application)


async def _close_the_rest(application: FastAPI) -> None:
    await application.state.query_sessions.aclose()
    await application.state.metrics_stores.aclose()
    await application.state.job_runner.aclose()
    await application.state.query_runner.aclose()
    await application.state.query_results.aclose()
    await application.state.topics.aclose()
    await application.state.data_cache.aclose()
    await application.state.resources.aclose()


# Before the application exists: the server configured its own loggers when it
# started, and this replaces them, so what they say reaches the file too (D184).
logs.configure("backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Added first, so it runs inside CORS and its answer carries CORS headers: the
# middleware added last is the outermost.
app.add_middleware(RecordFailures)
# Outside RecordFailures, so what it answers is in the request's language too.
app.add_middleware(RequestLanguage)
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
    expose_headers=["Content-Disposition", "X-Data-Cache", "X-Data-Cache-Age"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Serving the built frontend is enabled only when a build exists: without the
# check app.frontend raises RuntimeError and the application stops importing,
# including in tests, which do not need a build.
if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
