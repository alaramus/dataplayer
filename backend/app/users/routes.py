import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import col, func, select
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.db import SessionDep
from app.core.email import generate_new_account_email, send_email
from app.core.problems import Problem
from app.core.schemas import Message
from app.core.security import get_password_hash, verify_password
from app.core.translation import say
from app.users import crud, preferences
from app.users.deps import CurrentUser, get_current_active_superuser
from app.users.models import (
    UpdatePassword,
    User,
    UserBrief,
    UserCreate,
    UserDirectory,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
async def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
    """

    count_statement = select(func.count()).select_from(User)
    count = (await session.exec(count_statement)).one()

    statement = (
        select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    )
    users = (await session.exec(statement)).all()

    users_public = [UserPublic.model_validate(user) for user in users]
    return UsersPublic(data=users_public, count=count)


@router.get("/directory", response_model=UserDirectory)
async def read_directory(session: SessionDep, current_user: CurrentUser) -> Any:
    """Everybody an account can be shared with.

    Open to any signed-in user, because sharing a connection is not an
    administrative act and the person doing it has to name a colleague. It
    tells nobody anything they could not learn by being handed a connection:
    who has an account here. Switched-off accounts are left out — a grant to
    one would never be used.

    Declared before `/{user_id}` so the literal path is not read as an id.
    """
    statement = (
        select(User)
        .where(col(User.is_active).is_(True), User.id != current_user.id)
        .order_by(col(User.email))
    )
    users = (await session.exec(statement)).all()
    return UserDirectory(data=[UserBrief.model_validate(user) for user in users])


@router.post(
    "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
)
async def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user.
    """
    user = await crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise Problem(400, "users.email_taken")

    user = await crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        # send_email blocks on SMTP: calling it directly from an async handler
        # would stall the whole event loop.
        await run_in_threadpool(
            send_email,
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
async def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = await crud.get_user_by_email(
            session=session, email=user_in.email
        )
        if existing_user and existing_user.id != current_user.id:
            raise Problem(409, "users.email_taken")
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.patch("/me/password", response_model=Message)
async def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise Problem(400, "users.wrong_password")
    if body.current_password == body.new_password:
        raise Problem(400, "users.same_password")
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    await session.commit()
    return Message(message=say("Password updated successfully"))


@router.get("/me", response_model=UserPublic)
async def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.get("/me/preferences", response_model=preferences.PreferencesPublic)
async def read_my_preferences(session: SessionDep, current_user: CurrentUser) -> Any:
    """What this user chose, or the defaults they have not changed."""
    return await preferences.of(session, current_user.id)


@router.patch("/me/preferences", response_model=preferences.PreferencesPublic)
async def update_my_preferences(
    session: SessionDep,
    current_user: CurrentUser,
    update: preferences.PreferencesUpdate,
) -> Any:
    """Change some of them. Only a user's own: there is no route to anyone else's."""
    return await preferences.set_for(session, current_user.id, update)


@router.delete("/me", response_model=Message)
async def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise Problem(403, "users.superuser_cannot_delete_self")
    await crud.delete_user(session=session, user=current_user)
    return Message(message=say("User deleted successfully"))


@router.post("/signup", response_model=UserPublic)
async def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = await crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise Problem(400, "users.email_taken")
    user_create = UserCreate.model_validate(user_in)
    user = await crud.create_user(session=session, user_create=user_create)
    return user


@router.get("/{user_id}", response_model=UserPublic)
async def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id.
    """
    user = await session.get(User, user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise Problem(403, "auth.not_enough_privileges")
    if user is None:
        raise Problem(404, "users.not_found")
    return user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
async def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = await session.get(User, user_id)
    if not db_user:
        raise Problem(404, "users.not_found")
    if user_in.email:
        existing_user = await crud.get_user_by_email(
            session=session, email=user_in.email
        )
        if existing_user and existing_user.id != user_id:
            raise Problem(409, "users.email_taken")

    db_user = await crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
async def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    """
    Delete a user.
    """
    user = await session.get(User, user_id)
    if not user:
        raise Problem(404, "users.not_found")
    if user == current_user:
        raise Problem(403, "users.superuser_cannot_delete_self")
    await crud.delete_user(session=session, user=user)
    return Message(message=say("User deleted successfully"))
