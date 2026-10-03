import asyncio
import re
import uuid

import pytest
from pydantic import SecretStr

from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.pool import PooledConnections, key_for
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.resources import BorrowingStore, Pooling, ResourceStore
from tests.utils.database import working_postgres_options


def _options() -> PostgresUserPassword:
    return PostgresUserPassword(**working_postgres_options())


@pytest.fixture
async def store() -> ResourceStore:
    return ResourceStore(max_entries=8, max_idle_seconds=300.0)


def _pooling(store: ResourceStore, connector_id: uuid.UUID | None = None) -> Pooling:
    return Pooling(store=store, connector_id=connector_id or uuid.uuid4())


async def _pid(session: PostgresSession) -> int:
    rows = await session.query("SELECT pg_backend_pid() AS pid")
    return int(rows[0]["pid"])


async def test_a_pooled_session_runs_on_one_backend(store: ResourceStore) -> None:
    session = PostgresSession(_options(), _pooling(store))

    assert await _pid(session) == await _pid(session)

    await store.aclose()


async def test_without_a_pool_every_query_is_a_new_connection() -> None:
    """What the sub-project set out to change, stated as the baseline."""
    session = PostgresSession(_options())

    assert await _pid(session) != await _pid(session)


async def test_two_connectors_do_not_share_a_pool(store: ResourceStore) -> None:
    await _pid(PostgresSession(_options(), _pooling(store)))
    await _pid(PostgresSession(_options(), _pooling(store)))

    assert await store.size() == 2

    await store.aclose()


async def test_the_same_connector_keeps_one_pool(store: ResourceStore) -> None:
    connector_id = uuid.uuid4()

    await _pid(PostgresSession(_options(), _pooling(store, connector_id)))
    await _pid(PostgresSession(_options(), _pooling(store, connector_id)))

    assert await store.size() == 1

    await store.aclose()


async def test_a_borrowing_store_lends_a_pool_and_makes_none(store: ResourceStore) -> None:
    """A search across connections uses a pool somebody has, or a connection of
    its own: a pool made for it would be closed with it (D127, D200)."""
    pooled = uuid.uuid4()
    lent = await _pid(PostgresSession(_options(), _pooling(store, pooled)))
    borrowing = BorrowingStore(store)

    again = await _pid(PostgresSession(_options(), _pooling(borrowing, pooled)))
    own = PostgresSession(_options(), _pooling(borrowing))

    assert again == lent
    assert await _pid(own) != await _pid(own)
    assert await borrowing.size() == 0
    assert await store.size() == 1

    await store.aclose()


def test_changed_options_are_a_different_pool() -> None:
    """No separate place has to remember to reset anything on an edit."""
    connector_id = uuid.uuid4()
    options = _options()
    moved = options.model_copy(update={"port": options.port + 1})

    assert key_for(connector_id, PostgresSession(options).conninfo()) != key_for(
        connector_id, PostgresSession(moved).conninfo()
    )


def test_the_key_does_not_carry_the_password() -> None:
    """The password is named here rather than taken from the environment.

    A key looks like `postgres:<uuid>:<digest>`, so with the database password
    set to "postgres" — which is what a throwaway database in CI is usually
    given — the assertion failed on the prefix and said nothing about the
    password. It has to mean the same thing wherever it runs.
    """
    password = "a-password-that-appears-nowhere-else"
    options = _options().model_copy(update={"password": SecretStr(password)})

    key = key_for(uuid.uuid4(), PostgresSession(options).conninfo())

    assert password not in key
    assert "host=" not in key


async def test_a_wrong_password_is_still_reported_as_auth(
    store: ResourceStore,
) -> None:
    """The pool only says it could not hand out a connection.

    Left at that, a typo in a password would be reported as an unreachable
    host, which is what the user would then go and check.
    """
    options = _options().model_copy(update={"password": SecretStr("wrong-one")})
    session = PostgresSession(options, _pooling(store))

    with pytest.raises(AdapterError) as caught:
        await session.query("SELECT 1")

    assert caught.value.error_kind == "auth"
    assert "wrong-one" not in caught.value.message

    await store.aclose()


async def test_an_unreachable_host_is_reported_as_a_connection_problem(
    store: ResourceStore,
) -> None:
    options = _options().model_copy(update={"host": "no-such-host-at-all"})
    session = PostgresSession(options, _pooling(store))

    with pytest.raises(AdapterError) as caught:
        await session.query("SELECT 1")

    assert caught.value.error_kind in {"network", "timeout"}

    await store.aclose()


async def test_a_failing_query_still_names_the_query(store: ResourceStore) -> None:
    session = PostgresSession(_options(), _pooling(store))

    with pytest.raises(AdapterError) as caught:
        await session.query("SELECT * FROM table_that_is_not_there")

    assert caught.value.error_kind == "unknown"
    # The sentence, and the ref of the log entry that says why (D184).
    assert re.fullmatch(r"Query failed · ref [A-Z2-9]{6}", caught.value.message)

    await store.aclose()


async def test_closing_a_pool_does_not_cut_a_query_already_running() -> None:
    """Eviction closes a pool that may have handed out a connection.

    If that cut the request holding it, the cap on the number of pools would
    turn into random failures under load.
    """
    pool = PooledConnections(PostgresSession(_options()).conninfo())
    await pool.open()

    async with pool.connection() as connection:
        closing = asyncio.create_task(pool.close())
        await asyncio.sleep(0.05)
        cursor = await connection.execute("SELECT 1")
        assert await cursor.fetchone() == (1,)

    await closing
