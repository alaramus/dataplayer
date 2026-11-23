from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from anyio import to_thread
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(UTC) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


# Argon2 spends about 45 ms of CPU per call. Called from a handler it stops
# the one event loop for that long: under load testing every login froze all
# other requests and logins queued one by one at ~22 a second. Argon2
# releases the GIL, so in threads they also run side by side.
async def verify_password_off_loop(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return await to_thread.run_sync(verify_password, plain_password, hashed_password)


async def get_password_hash_off_loop(password: str) -> str:
    return await to_thread.run_sync(get_password_hash, password)
