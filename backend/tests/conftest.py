import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker, init_db, loop_factory
from app.main import app
from app.models import User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session")
def _asyncio_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    """Переопределяет фабрику цикла pytest-asyncio.

    Нужна на Windows, где цикл по умолчанию несовместим с psycopg. Подменять
    политику циклов нельзя: в Python 3.14 она объявлена устаревшей.
    """
    return loop_factory


@pytest.fixture(scope="session", autouse=True)
async def db() -> AsyncGenerator[AsyncSession]:
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
