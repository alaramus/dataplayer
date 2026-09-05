import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_KEY = base64.urlsafe_b64encode(b"c" * 32).decode()


def test_memory_cache_is_the_default() -> None:
    """The declared default, not whatever this machine's `.env` happens to say.

    `Settings()` reads `../.env`, so building one here measured the developer's
    deployment and called it the default. It passed for as long as nobody
    selected Redis locally, and said nothing about the code the moment somebody
    did.
    """
    fields = Settings.model_fields

    assert fields["DATA_CACHE_BACKEND"].default == "memory"
    assert fields["DATA_CACHE_REDIS_URL"].default is None
    assert fields["DATA_CACHE_SECRET_KEY"].default is None


@pytest.mark.parametrize(
    ("url", "key", "missing"),
    [
        (None, VALID_KEY, "DATA_CACHE_REDIS_URL"),
        ("redis://cache:6379/0", None, "DATA_CACHE_SECRET_KEY"),
    ],
)
def test_redis_backend_requires_an_address_and_cache_only_key(
    url: str | None, key: str | None, missing: str
) -> None:
    with pytest.raises(ValidationError, match=missing):
        Settings(
            DATA_CACHE_BACKEND="redis",
            DATA_CACHE_REDIS_URL=url,
            DATA_CACHE_SECRET_KEY=key,
        )


@pytest.mark.parametrize(
    "url",
    [
        "redis://:password@cache:6379/0",
        "rediss://cache-user:password@cache.example.com:6380/0",
    ],
)
def test_redis_backend_accepts_authenticated_plain_or_tls_urls(url: str) -> None:
    configured = Settings(
        DATA_CACHE_BACKEND="redis",
        DATA_CACHE_REDIS_URL=url,
        DATA_CACHE_SECRET_KEY=VALID_KEY,
        DATA_CACHE_DEPLOYMENT="production-eu-1",
    )

    assert configured.DATA_CACHE_REDIS_URL is not None
    assert configured.DATA_CACHE_REDIS_URL.get_secret_value() == url


def test_non_redis_cache_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="redis:// or rediss://"):
        Settings(DATA_CACHE_REDIS_URL="https://cache.example.com")


def test_cache_entry_ceiling_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(DATA_CACHE_MAX_ENTRIES=0)
