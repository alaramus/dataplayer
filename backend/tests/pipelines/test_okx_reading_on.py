"""A link that reads an OKX symbol's trades on, run by its pipeline, its
bookmark kept by this application (D434). OKX is the fake one."""

import uuid

import psycopg
import pytest
from httpx import AsyncClient
from sqlmodel import col, select

from app.connectors.bookmarks import ReadingBookmark
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.adapters.okx_fixture import FakeOkx, install
from tests.pipelines.canvas import Canvas, card, connector, link
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import conninfo, run

pytestmark = pytest.mark.usefixtures("clean")

NODE = "linear:symbol:BTC-USDT-SWAP:trades"
COLUMNS = [
    {"source": "id", "target": "id"},
    {"source": "price", "target": "price"},
]


@pytest.fixture
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


@pytest.fixture
async def table(schema: str) -> str:
    await run(f"CREATE TABLE {schema}.trades (id text, price text)")  # noqa: S608 -- the fixture's own schema
    return f"{schema}.trades"


async def _count(table: str) -> int:
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        found = await (await conn.execute(f"SELECT count(*) FROM {table}")).fetchone()  # noqa: S608 -- a test's own table
        return int(found[0]) if found else 0


async def _ran(canvas: Canvas, link_id: str) -> str | None:
    started = await canvas.run()
    assert started.status_code == 200, started.text
    job_id = uuid.UUID(started.json()["job_id"])
    await app.state.job_runner.wait_for(job_id)
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.state == "succeeded", job.message
    return (await canvas.outcomes())[link_id][1]


async def _bookmarks(connector_id: str) -> list[ReadingBookmark]:
    async with async_session_maker() as session:
        return list(
            (
                await session.exec(
                    select(ReadingBookmark).where(
                        col(ReadingBookmark.connector_id) == uuid.UUID(connector_id)
                    )
                )
            ).all()
        )


async def test_each_run_adds_only_the_trades_made_since_the_last(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_okx: FakeOkx,
    table: str,
) -> None:
    headers = normal_user_token_headers
    okx = await connector(client, headers, "okx", {"endpoint": "okx"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(okx, [(NODE, "Trades", "feed")], name="OKX")
    target = card(database, [(table, "trades", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = link(
        source,
        NODE,
        target,
        table,
        "rows_since_last",
        columns=COLUMNS,
        start="earliest",
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    link_id = str(drawn["id"])

    first = await _ran(canvas, link_id)
    assert first is not None and "added to trades" in first
    # The last hour, a trade a second.
    first_count = await _count(table)
    assert 3599 <= first_count <= 3601
    [kept] = await _bookmarks(okx)
    assert kept.positions[""] == fake_okx.trades + 1

    fake_okx.add_trades(3)
    assert await _ran(canvas, link_id) == "3 new messages added to trades"
    assert await _count(table) == first_count + 3

    assert await _ran(canvas, link_id) == "Nothing new since the last run"
