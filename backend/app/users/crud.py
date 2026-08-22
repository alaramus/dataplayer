import uuid
from typing import Any

from anyio import to_thread
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.users import storage
from app.users.models import User, UserCreate, UserUpdate


async def create_user(*, session: AsyncSession, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    # A user without their directory would have a file connector that cannot
    # reach anything. Creating files is blocking work, hence the thread.
    await to_thread.run_sync(storage.create_home, db_obj.id)
    return db_obj


async def update_user(
    *, session: AsyncSession, db_user: User, user_in: UserUpdate
) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def delete_user(*, session: AsyncSession, user: User) -> None:
    """Remove the user, the rows that belong to them and their files.

    The row goes first. If removing the files then fails, the user is gone and
    what is left is a directory nobody owns, which `app.seed_storage` sweeps up.
    The other order would risk a user who can still log in and finds their
    files missing.
    """
    user_id = user.id
    # Related rows are removed by the database-level cascade.
    await session.delete(user)
    await session.commit()
    await to_thread.run_sync(storage.remove_home, user_id)


async def get_all_user_ids(*, session: AsyncSession) -> set[uuid.UUID]:
    result = await session.exec(select(User.id))
    return set(result.all())


async def get_user_by_email(*, session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    return result.first()


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


async def authenticate(
    *, session: AsyncSession, email: str, password: str
) -> User | None:
    db_user = await get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user
        # doesn't exist. This ensures the response time is similar whether or not
        # the email exists.
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
    return db_user
