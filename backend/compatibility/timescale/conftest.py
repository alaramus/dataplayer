import asyncio
from collections.abc import Callable

import pytest

from app.core.db import loop_factory
from compatibility.timescale.source import TimescaleSource


@pytest.fixture(scope="session")
def _asyncio_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    return loop_factory


@pytest.fixture(scope="session", params=[
    pytest.param(TimescaleSource(55417, "2.17.2", "heap"), id="legacy"),
    pytest.param(TimescaleSource(55418, "2.18.0", "hypercore"), id="columnstore"),
])
async def source(request: pytest.FixtureRequest) -> TimescaleSource:
    target: TimescaleSource = request.param
    session = target.session()
    assert await session.query("SELECT ready FROM public.fixture_marker") == [{"ready": 1}]
    rows = await session.query(
        "SELECT extversion FROM pg_catalog.pg_extension WHERE extname = 'timescaledb'",
    )
    assert rows == [{"extversion": target.version}]
    version = await session.query("SELECT current_setting('server_version_num') AS version")
    assert 160000 <= int(version[0]["version"]) < 170000
    assert await target.session(database="plain_fixture").query(
        "SELECT ready FROM public.fixture_marker",
    ) == [{"ready": 1}]
    return target
