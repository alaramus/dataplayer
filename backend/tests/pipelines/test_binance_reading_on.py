"""A link that reads a symbol's trades on, run by its pipeline, its bookmark
kept by this application (D319). Binance is the fake one."""

import uuid

import psycopg
import pytest
from httpx import AsyncClient
from sqlmodel import col, select

from app.connectors.bookmarks import ReadingBookmark
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.adapters.binance_fixture import FakeBinance, install
from tests.pipelines.canvas import Canvas, card, connector, link
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import conninfo, run

pytestmark = pytest.mark.usefixtures("clean")

NODE = "spot:symbol:BTCUSDT:trades"
COLUMNS = [
    {"source": "id", "target": "id"},
    {"source": "price", "target": "price"},
]


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
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
    fake_binance: FakeBinance,
    table: str,
) -> None:
    headers = normal_user_token_headers
    binance = await connector(client, headers, "binance", {"endpoint": "binance"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(binance, [(NODE, "Trades", "feed")], name="Binance")
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
    hour = await _count(table)
    assert first is not None and "added to trades" in first
    assert 59 <= hour <= 61
    [kept] = await _bookmarks(binance)
    assert kept.reader == f"dataplayer-link-{link_id}"
    assert kept.positions[""] == fake_binance.trades + 1

    fake_binance.trades += 3
    assert await _ran(canvas, link_id) == "3 new messages added to trades"
    assert await _count(table) == hour + 3

    assert await _ran(canvas, link_id) == "Nothing new since the last run"

    # The bookmark goes with its connection.
    deleted = await client.delete(f"/api/v1/connectors/{binance}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert await _bookmarks(binance) == []


async def test_a_link_reading_the_order_book_on_fails_in_words(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
    table: str,
) -> None:
    del fake_binance
    headers = normal_user_token_headers
    binance = await connector(client, headers, "binance", {"endpoint": "binance"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    book = "spot:symbol:BTCUSDT:book"
    source = card(binance, [(book, "Order book", "feed")], name="Binance")
    target = card(database, [(table, "trades", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = link(source, book, target, table, "rows_since_last", columns=COLUMNS)
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text

    started = await canvas.run()
    assert started.status_code == 200, started.text
    job_id = uuid.UUID(started.json()["job_id"])
    await app.state.job_runner.wait_for(job_id)
    outcome = (await canvas.outcomes())[str(drawn["id"])]
    assert outcome[1] == "Only trades and candles are read on"


async def _unique_keys(table: str) -> list[str]:
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        found = await conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'u'",
            (table,),
        )
        return [row[0] for row in await found.fetchall()]


async def test_a_table_the_link_makes_is_keyed_by_the_trade_id(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
    schema: str,
) -> None:
    headers = normal_user_token_headers
    name = f"trades_{uuid.uuid4().hex[:8]}"
    binance = await connector(client, headers, "binance", {"endpoint": "binance"})
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(binance, [(NODE, "Trades", "feed")], name="Binance")
    target = card(database, [(schema, schema, "schema")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = link(
        source,
        NODE,
        target,
        schema,
        "rows_since_last_new",
        name=name,
        start="latest",
        columns=[
            {"source": "id", "target": "trade_id", "type_code": "bigint"},
            {"source": "price", "target": "price", "type_code": "numeric"},
        ],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    link_id = str(drawn["id"])

    first = await _ran(canvas, link_id)
    assert first is not None
    assert "the table was made with a key on id, so each row is kept once" in first
    assert await _unique_keys(f"{schema}.{name}") == ["UNIQUE (trade_id)"]

    fake_binance.trades += 2
    assert await _ran(canvas, link_id) == f"2 new messages added to {name}"
    assert await _count(f"{schema}.{name}") == 2
