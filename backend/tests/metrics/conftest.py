"""A metrics store of the tests' own, in a TimescaleDB named by the environment.

TEST_METRICS_STORE_URL names a server whose role may create databases; each
session gets a fresh database there and drops it afterwards. Without the
variable the tests that need a store are skipped, as the Redis ones are.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import delete

from app.core.db import async_session_maker
from app.metrics.models import MetricsStoreSetting
from app.metrics.store import ROLLUP_VIEWS, MetricsStore, store_url
from app.services.models import ManagedService

TEST_METRICS_STORE_URL = os.environ.get("TEST_METRICS_STORE_URL")

needs_store = pytest.mark.skipif(
    TEST_METRICS_STORE_URL is None, reason="TEST_METRICS_STORE_URL not configured"
)


def _server_options() -> dict[str, Any]:
    assert TEST_METRICS_STORE_URL is not None
    parts = urlsplit(TEST_METRICS_STORE_URL)
    return {
        "auth_method": "user_password",
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "database": parts.path.lstrip("/") or "postgres",
        "user": parts.username or "postgres",
        "password": parts.password or "",
    }


@pytest.fixture(scope="session", autouse=True)
async def keep_development_store() -> AsyncIterator[None]:
    """Put back the store setting the development stack had.

    The suite shares the development database, and these tests need a stack
    with no store and remove whatever store they set up. Unlike the superuser,
    nothing recreates a store on the next start, so it is saved here first.
    """
    async with async_session_maker() as session:
        saved = await session.get(MetricsStoreSetting, 1)
        kept = None if saved is None else saved.model_dump()
    yield
    if kept is None:
        return
    async with async_session_maker() as session:
        await session.exec(delete(MetricsStoreSetting))
        if kept["service_id"] is not None and await session.get(ManagedService, kept["service_id"]) is None:
            kept["service_id"] = None
        session.add(MetricsStoreSetting(**kept))
        await session.commit()


@pytest.fixture(scope="session")
async def store_options() -> AsyncIterator[dict[str, Any]]:
    """Options of a fresh, empty database, in the PostgreSQL adapter's shape."""
    if TEST_METRICS_STORE_URL is None:
        pytest.skip("TEST_METRICS_STORE_URL not configured")
    server = _server_options()
    name = f"metrics_test_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        make_url(store_url(server)), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin.connect() as connection:
            # A fixed prefix and a hex suffix this fixture made: nothing to quote.
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield {**server, "database": name}
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    finally:
        await admin.dispose()


async def refresh_rollups(store: MetricsStore) -> None:
    """Materialise every rollup over all time, as the policies would over theirs.

    Tests write points days in the past, outside a policy's window, so nothing
    else would put them in a rollup.
    """
    for view in ROLLUP_VIEWS:
        # The store's own policy may be refreshing the same rollup, and
        # Timescale refuses a second refresh rather than waiting for it.
        for attempt in range(50):
            try:
                async with store._engine.connect() as raw:
                    connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
                    await connection.execute(
                        text("CALL refresh_continuous_aggregate(CAST(:view AS regclass), NULL, NULL)"),
                        {"view": view},
                    )
                break
            except OperationalError as refusal:
                if "concurrent refresh" not in str(refusal) or attempt == 49:
                    raise
                await asyncio.sleep(0.2)


@pytest.fixture
async def store(store_options: dict[str, Any]) -> AsyncIterator[MetricsStore]:
    opened = MetricsStore(store_url(store_options))
    await opened.migrate()
    async with opened._engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE metric_point, metric_process, metric_restart, metric_series "
                "RESTART IDENTITY"
            )
        )
    # Series ids start from one again, so what an earlier test rolled up must go.
    await refresh_rollups(opened)
    try:
        yield opened
    finally:
        await opened.aclose()
