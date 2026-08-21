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
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


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
async def db(_user_storage_root: Path) -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        await init_db(session)
        yield session
        await session.exec(delete(Connector))
        await session.exec(delete(User))
        await session.commit()


@pytest.fixture(scope="session")
async def client() -> AsyncGenerator[AsyncClient]:
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
