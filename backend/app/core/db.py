import asyncio
import selectors
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import User, UserCreate


def loop_factory() -> asyncio.AbstractEventLoop:
    """Цикл событий, пригодный для psycopg в асинхронном режиме.

    На Windows Python по умолчанию создаёт ProactorEventLoop, с которым psycopg 3
    работать не умеет и падает с InterfaceError. В контейнере (Linux) фабрика
    возвращает обычный цикл, поэтому поведение в развёртывании не меняется.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


engine = create_async_engine(str(settings.DATABASE_URL))

# expire_on_commit=False обязателен: иначе обращение к полю объекта после
# commit() запускает ленивую загрузку, которая в async-режиме падает.
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


async def init_db(session: AsyncSession) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    result = await session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    )
    user = result.first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = await crud.create_user(session=session, user_create=user_in)
