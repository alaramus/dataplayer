from anyio import to_thread
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from app.users.models import User, UserCreate


async def init_db(session: AsyncSession) -> None:
    """Create the first superuser if it does not exist yet.

    Tables themselves are created by Alembic migrations. This lives in the
    users module rather than core/db.py so that core depends on nothing.
    """
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
    # Unconditional: the superuser predates personal storage, so an existing
    # one has no directory yet.
    await to_thread.run_sync(storage.create_home, user.id)
