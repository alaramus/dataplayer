import asyncio
from collections.abc import Callable

import pytest

from app.core.db import loop_factory
from compatibility.timescale.source import TimescaleSource

# The matrix pinned in compose.yml: every PostgreSQL major the extension still
# ships for, and the releases where its API changed shape.
SOURCES = (
    TimescaleSource(55414, "2.14.2", 14, "heap"),
    TimescaleSource(55417, "2.17.2", 16, "heap"),
    TimescaleSource(55418, "2.18.0", 16, "hypercore"),
    TimescaleSource(55419, "2.19.3", 15, "hypercore"),
    TimescaleSource(55423, "2.23.1", 16, "heap"),
    TimescaleSource(55430, "2.30.0", 17, "heap"),
    TimescaleSource(55431, "2.30.0", 18, "heap"),
)


@pytest.fixture(scope="session")
def _asyncio_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    return loop_factory


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(target, id=f"{target.version}-pg{target.postgres_major}")
        for target in SOURCES
    ],
)
async def source(request: pytest.FixtureRequest) -> TimescaleSource:
    target: TimescaleSource = request.param
    session = target.session()
    assert await session.query("SELECT ready FROM public.fixture_marker") == [{"ready": 1}]
    rows = await session.query(
        "SELECT extversion FROM pg_catalog.pg_extension WHERE extname = 'timescaledb'",
    )
    assert rows == [{"extversion": target.version}]
    version = await session.query("SELECT current_setting('server_version_num') AS version")
    major = target.postgres_major * 10000
    assert major <= int(version[0]["version"]) < major + 10000
    assert await target.session(database="plain_fixture").query(
        "SELECT ready FROM public.fixture_marker",
    ) == [{"ready": 1}]
    return target
