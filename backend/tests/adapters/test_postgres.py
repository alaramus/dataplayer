import time

from pydantic import SecretStr

from app.adapters import registry
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.session import CHECK_TIMEOUT_SECONDS
from tests.utils.database import working_postgres_options

WRONG_PASSWORD = "definitely-not-the-password"


def _working_options() -> PostgresOptions:
    return PostgresOptions(**working_postgres_options())


async def test_check_connection_succeeds() -> None:
    result = await PostgresAdapter(_working_options()).check_connection()

    assert result.ok is True
    assert result.error_kind is None
    assert result.latency_ms is not None and result.latency_ms >= 0


async def test_wrong_password_is_classified_as_auth() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


async def test_unreachable_endpoint_times_out_within_the_budget() -> None:
    options = _working_options().model_copy(update={"host": "127.0.0.1", "port": 1})

    started = time.perf_counter()
    result = await PostgresAdapter(options).check_connection()
    elapsed = time.perf_counter() - started

    assert result.ok is False
    assert result.error_kind == "timeout"
    # Unbounded, psycopg waits about two minutes on an unreachable host.
    assert elapsed < CHECK_TIMEOUT_SECONDS + 2


async def test_missing_database_is_classified_as_config() -> None:
    options = _working_options().model_copy(update={"database": "no_such_database"})

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"


async def test_unknown_user_is_classified_as_auth() -> None:
    options = _working_options().model_copy(update={"user": "no_such_role"})

    result = await PostgresAdapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "auth"


async def test_error_message_never_leaks_the_password() -> None:
    options = _working_options().model_copy(
        update={"password": SecretStr(WRONG_PASSWORD)}
    )

    result = await PostgresAdapter(options).check_connection()

    assert WRONG_PASSWORD not in result.message


async def test_adapter_type_is_registered() -> None:
    adapter_type = registry.get("postgres")

    assert adapter_type.title == "PostgreSQL"
    assert adapter_type.options_schema is PostgresOptions
