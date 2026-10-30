import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserInvite(SQLModel):
    """A new account as a superuser makes it: no password, which the person
    chooses through the link they are given."""

    email: EmailStr = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_superuser: bool = False


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# What `hashed_password` starts with while no password has been chosen: no hash
# begins with it, so nothing verifies against it (see `invitations`).
PASSWORD_LOCK = "!"


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    @property
    def password_set(self) -> bool:
        return not self.hashed_password.startswith(PASSWORD_LOCK)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None
    # False until the person has chosen one through their link.
    password_set: bool = True


class InvitationLink(SQLModel):
    """Where the person chooses their password, and until when it works."""

    url: str
    expires_at: datetime


class UserInvited(SQLModel):
    user: UserPublic
    invitation: InvitationLink


class InvitationHolder(SQLModel):
    """Whom a link is for, as its page greets them."""

    email: EmailStr
    full_name: str | None = None


class InvitationToken(SQLModel):
    # In the body rather than the path, so it stays out of access logs.
    token: str = Field(max_length=2000)


class InvitationAccept(InvitationToken):
    new_password: str = Field(min_length=8, max_length=128)


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class UserBrief(SQLModel):
    """A person, as somebody choosing whom to share with needs to see them.

    Deliberately less than `UserPublic`: whether an account is an
    administrator, and whether it is switched on, are administrative facts and
    have no place in a picker.
    """

    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None


class UserDirectory(SQLModel):
    data: list[UserBrief]


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
