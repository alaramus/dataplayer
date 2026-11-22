"""The TLS block against servers that speak only TLS (D446, D447).

pg-tls accepts TLS alone, `certuser` by its client certificate and everybody
else by password; redis-tls speaks only TLS and knows the ACL user `reader`
with the default user switched off. Both are skipped without their server.
"""

import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr

from app.adapters.postgres.options import PostgresNoAuth, PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.options import RedisNoAuth, RedisPassword
from app.adapters.resources import Pooling, ResourceStore
from tests.utils import services


def _certificates() -> Path:
    return services.tls_test_certificates()


def _read(name: str) -> str:
    return (_certificates() / name).read_text(encoding="ascii")


def _postgres(**block: Any) -> dict[str, Any]:
    parts = urlsplit(services.PG_TLS.require())
    return {"host": parts.hostname, "port": parts.port, "database": "postgres", **block}


def _verified() -> dict[str, Any]:
    return {"tls_mode": "verify_full", "tls_trust": "certificate", "tls_ca_certificate": _read("ca.crt")}


async def _encrypted(session: PostgresSession) -> bool:
    rows = await session.query("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    return bool(rows[0]["ssl"])


async def test_a_password_goes_over_verified_tls() -> None:
    options = PostgresUserPassword(
        **_postgres(**_verified()), user="postgres", password=SecretStr("dataplayer")
    )
    session = PostgresSession(options)

    assert (await session.check()).ok
    assert await _encrypted(session)


async def test_a_client_certificate_is_the_identity() -> None:
    options = PostgresNoAuth(
        **_postgres(**_verified()),
        auth_method="no_auth",
        user="certuser",
        tls_client_certificate=_read("client.crt"),
        tls_client_key=SecretStr(_read("client.key")),
    )

    result = await PostgresSession(options).check()

    assert result.ok, result.message


async def test_an_encrypted_client_key_is_opened_by_its_passphrase() -> None:
    options = PostgresNoAuth(
        **_postgres(**_verified()),
        auth_method="no_auth",
        user="certuser",
        tls_client_certificate=_read("client.crt"),
        tls_client_key=SecretStr(_read("client-encrypted.key")),
        tls_client_key_passphrase=SecretStr("dataplayer"),
    )

    assert (await PostgresSession(options).check()).ok


async def test_a_wrong_passphrase_is_refused_by_the_form() -> None:
    with pytest.raises(ValueError, match="passphrase does not open"):
        PostgresNoAuth(
            **_postgres(**_verified()),
            auth_method="no_auth",
            user="certuser",
            tls_client_certificate=_read("client.crt"),
            tls_client_key=SecretStr(_read("client-encrypted.key")),
            tls_client_key_passphrase=SecretStr("wrong"),
        )


async def test_without_the_certificate_the_role_is_refused() -> None:
    options = PostgresNoAuth(**_postgres(**_verified()), auth_method="no_auth", user="certuser")

    result = await PostgresSession(options).check()

    assert not result.ok
    assert result.error_kind == "auth"


async def test_a_server_signed_by_an_unknown_authority_is_not_believed() -> None:
    """Said as what to check, not as an unreachable host."""
    options = PostgresUserPassword(
        **_postgres(tls_mode="verify_full"), user="postgres", password=SecretStr("dataplayer")
    )

    result = await PostgresSession(options).check()

    assert not result.ok
    assert result.error_kind == "config"
    assert result.message == "The server's certificate could not be verified"
    assert "dataplayer" not in result.message


async def test_plain_text_is_refused_by_this_server() -> None:
    options = PostgresUserPassword(
        **_postgres(tls_mode="disabled"), user="postgres", password=SecretStr("dataplayer")
    )

    assert not (await PostgresSession(options).check()).ok


async def test_required_encrypts_without_believing_anything() -> None:
    options = PostgresUserPassword(
        **_postgres(tls_mode="required"), user="postgres", password=SecretStr("dataplayer")
    )
    session = PostgresSession(options)

    assert (await session.check()).ok
    assert await _encrypted(session)


async def test_a_pool_keeps_its_key_files_until_it_closes() -> None:
    """libpq reads them at every connect, so they live with the pool (D447)."""
    store = ResourceStore(max_entries=4, max_idle_seconds=300.0)
    options = PostgresNoAuth(
        **_postgres(**_verified()),
        auth_method="no_auth",
        user="certuser",
        tls_client_certificate=_read("client.crt"),
        tls_client_key=SecretStr(_read("client.key")),
    )
    session = PostgresSession(options, Pooling(store=store, connector_id=uuid.uuid4()))
    try:
        assert await _encrypted(session)
        pool = next(iter(store._entries.values())).value  # noqa: SLF001 - what the store holds
        files = pool._files  # noqa: SLF001 - where the pool keeps them
        assert files is not None and files.key is not None and files.key.exists()
        written = files.key
        # A second request reuses the pool and its files.
        assert await _encrypted(session)
        assert store._entries  # noqa: SLF001
    finally:
        await store.aclose()
    assert not written.exists()
    assert not written.parent.exists()


def _redis(**block: Any) -> dict[str, Any]:
    parts = urlsplit(services.REDIS_TLS.require())
    return {"host": parts.hostname, "port": parts.port, **block}


async def test_redis_over_tls_signs_in_as_an_acl_user() -> None:
    options = RedisPassword(
        **_redis(**_verified()),
        auth_method="password",
        user="reader",
        password=SecretStr("dataplayer"),
    )
    source = RedisAdapter(options)

    result = await source.check_connection()

    assert result.ok, result.message
    assert source.connection_string().startswith("rediss://reader@")


async def test_redis_refuses_the_default_user_it_switched_off() -> None:
    options = RedisNoAuth(**_redis(**_verified()), auth_method="no_auth")

    result = await RedisAdapter(options).check_connection()

    assert not result.ok


async def test_redis_without_tls_hears_nothing() -> None:
    options = RedisPassword(
        **_redis(tls_mode="disabled"),
        auth_method="password",
        user="reader",
        password=SecretStr("dataplayer"),
    )

    assert not (await RedisAdapter(options).check_connection()).ok


async def test_a_postgres_failure_says_nothing_of_the_key() -> None:
    """Nothing of the block reaches an answer (D184)."""
    options = PostgresNoAuth(
        **_postgres(tls_mode="verify_full"),
        auth_method="no_auth",
        user="certuser",
        tls_client_certificate=_read("client.crt"),
        tls_client_key=SecretStr(_read("client.key")),
    )

    result = await PostgresSession(options).check()

    assert not result.ok
    assert "PRIVATE KEY" not in result.message
    assert "dp-tls" not in result.message


async def test_a_redis_tls_mistake_is_said_safely() -> None:
    options = RedisPassword(
        **_redis(tls_mode="verify_full"),
        auth_method="password",
        user="reader",
        password=SecretStr("dataplayer"),
    )

    result = await RedisAdapter(options).check_connection()

    assert not result.ok
    assert "dataplayer" not in result.message
