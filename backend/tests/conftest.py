import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.main import app
from app.users.bootstrap import init_db
from app.users.models import User
from tests.utils import services
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--require-services",
        action="store_true",
        help="Stop the run when a server the suite uses does not answer, "
        "instead of skipping its tests. CI passes it.",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    if session.config.getoption("--require-services"):
        services.require_all()


@pytest.fixture
def isolated_registry() -> Generator[None]:
    """Isolate the adapter registry so registrations in a test do not leak."""
    saved = dict(registry._registry)
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)


@pytest.fixture(scope="session")
def _asyncio_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    """Override the pytest-asyncio loop factory.

    Needed on Windows, where the default loop is incompatible with psycopg.
    Swapping the loop policy is not an option: Python 3.14 deprecated it.
    """
    return loop_factory


@pytest.fixture(scope="session", autouse=True)
def _user_storage_root(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path]:
    """Keep the personal directories of test users out of the real root.

    Creating a user creates their directory, so without this every run would
    leave stray directories in USER_STORAGE_ROOT.
    """
    root = tmp_path_factory.mktemp("user-storage")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "USER_STORAGE_ROOT", root)
        yield root


@pytest.fixture(scope="session", autouse=True)
def _application_database() -> None:
    services.POSTGRES.require()


@pytest.fixture(scope="session", autouse=True)
async def db(
    _user_storage_root: Path, _application_database: None
) -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        await init_db(session)
        yield session
        await session.exec(delete(Connector))
        await session.exec(delete(User))
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
def _memory_cache() -> Generator[None]:
    """The suite tests the application, not the machine it is running on.

    `Settings` reads `../.env`, so on a developer's stack — where the cache is
    Redis at a Compose hostname — the test application would build a client for
    a host nothing here can resolve, and every assertion about a hit or a miss
    would become an assertion about DNS. The shared backend is exercised where
    it can actually be reached, in `tests/adapters/test_redis_cache_backend.py`.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "DATA_CACHE_BACKEND", "memory")
        yield


@pytest.fixture(scope="session")
def _quiet_schedules() -> Generator[None]:
    """The suite drives the scheduler's clock itself (D179).

    The application's own loop looks once when it starts and then not for an
    hour, so a schedule a test puts in the past is started by the test's
    `tick`, never by the loop in between.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "SCHEDULE_TICK_SECONDS", 3600)
        yield


@pytest.fixture(scope="session")
async def client(_memory_cache: None, _quiet_schedules: None) -> AsyncGenerator[AsyncClient]:
    # The lifespan is entered explicitly: ASGITransport does not run it, and
    # without it the application has no resource store, so every request would
    # quietly fall back to opening its own connection — the very thing the
    # pooling tests are there to catch.
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


@pytest.fixture(scope="session")
async def superuser_token_headers(client: AsyncClient) -> dict[str, str]:
    return await get_superuser_token_headers(client)


@pytest.fixture(scope="session")
async def normal_user_token_headers(
    client: AsyncClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
