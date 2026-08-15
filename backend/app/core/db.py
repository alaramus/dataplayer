import asyncio
import selectors
import sys
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings


def loop_factory() -> asyncio.AbstractEventLoop:
    """Event loop usable by psycopg in asynchronous mode.

    On Windows Python creates a ProactorEventLoop by default, which psycopg 3
    cannot work with: it fails with InterfaceError. Inside the container
    (Linux) the factory returns an ordinary loop, so deployment is unaffected.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


engine = create_async_engine(str(settings.DATABASE_URL))

# expire_on_commit=False is required: otherwise touching an attribute after
# commit() triggers a lazy load, which fails in async mode.
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]
