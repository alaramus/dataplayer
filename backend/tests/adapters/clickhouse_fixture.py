"""A database of known shape on the ClickHouse server the suite talks to.

Built over the HTTP interface directly rather than through the adapter, which
cannot write yet, and rebuilt by every module that asks for it.
"""

import httpx

from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.options import ClickhouseUserPassword
from app.adapters.clickhouse.session import options_from_url, quoted_name
from tests.utils.services import CLICKHOUSE

# A dot in the name on purpose: ClickHouse allows one, and a node id must
# survive it.
DATABASE = "dp_test.clickhouse"
# A name that quotes badly and looks like a parameter, on purpose.
ODD = "odd`{p0:String}\\name"

_DB = quoted_name(DATABASE)

_SCHEMA = [
    f"DROP DATABASE IF EXISTS {_DB}",
    f"CREATE DATABASE {_DB}",
    f"""
    CREATE TABLE {_DB}.items (
        id UInt32,
        label LowCardinality(String) DEFAULT 'it''s',
        `100%` Nullable(Int32),
        amount Decimal(38, 10),
        big UInt64,
        huge Int128,
        ratio Float64,
        kind Enum8('small' = 1, 'it''s big' = 2),
        tags Array(String),
        attrs Map(String, UInt8),
        pair Tuple(a Int8, b String),
        made DateTime('Asia/Tokyo'),
        seen Nullable(DateTime64(3)),
        day Date,
        ok Bool,
        uid UUID,
        addr IPv4,
        doubled Nullable(Int64) MATERIALIZED `100%` * 2,
        INDEX items_label label TYPE bloom_filter GRANULARITY 4,
        CONSTRAINT items_amount CHECK amount >= 0
    ) ENGINE = MergeTree
    PARTITION BY toYYYYMM(day)
    ORDER BY (id, label)
    COMMENT 'Things'
    """,
    f"CREATE TABLE {_DB}.dupes (a UInt8, b String) ENGINE = MergeTree ORDER BY a",
    f"CREATE TABLE {_DB}.journal (line String) ENGINE = Log",
    f"CREATE TABLE {_DB}.{quoted_name(ODD)} (`x{{p1:Int8}}` Int8) ENGINE = Memory",
    f"CREATE VIEW {_DB}.item_labels AS SELECT id, label FROM {_DB}.items",
    f"""
    CREATE MATERIALIZED VIEW {_DB}.item_ids ENGINE = MergeTree ORDER BY id
    AS SELECT id FROM {_DB}.items
    """,
    f"""
    INSERT INTO {_DB}.items
        (id, label, `100%`, amount, big, huge, ratio, kind, tags, attrs, pair,
         made, seen, day, ok, uid, addr)
    VALUES
        (1, 'alpha', 5, 12345678901234567890.0123456789, 18446744073709551615,
         -170141183460469231731687303715884105728, 0.1, 'it''s big', ['a', 'b"c'],
         {{'k': 1}}, (1, 'x'), '2024-01-02 12:04:05', '2024-01-02 03:04:05.120',
         '2024-02-03', true, '00000000-0000-0000-0000-000000000001', '10.0.0.1'),
        (2, '50% off', NULL, 0, 1, 0, 1e300, 'small', [], {{}}, (2, ''),
         '2024-01-01 09:00:00', NULL, '2024-03-01', false,
         '00000000-0000-0000-0000-000000000002', '10.0.0.2'),
        (3, 'under_score', 1, 1, 2, 1, nan, 'small', [], {{}}, (3, ''),
         '2024-01-01 09:00:00', NULL, '2024-03-01', false,
         '00000000-0000-0000-0000-000000000003', '10.0.0.3')
    """,
    f"INSERT INTO {_DB}.dupes VALUES (1, 'b'), (1, 'a'), (1, 'b'), (0, 'z')",
    f"INSERT INTO {_DB}.journal VALUES ('one'), ('two')",
    f"INSERT INTO {_DB}.{quoted_name(ODD)} VALUES (7)",
]


def options(**override: object) -> ClickhouseUserPassword:
    values = {**options_from_url(CLICKHOUSE.require()), **override}
    return ClickhouseUserPassword(**values)


def adapter(**override: object) -> ClickhouseAdapter:
    return ClickhouseAdapter(options(**override))


async def run(*statements: str) -> None:
    chosen = options()
    async with httpx.AsyncClient(
        base_url=f"http://{chosen.host}:{chosen.port}",
        auth=(chosen.user, chosen.password.get_secret_value()),
    ) as client:
        for statement in statements:
            response = await client.post("/", content=statement.encode())
            assert response.status_code == 200, response.text


async def build() -> None:
    await run(*_SCHEMA)


async def tear_down() -> None:
    await run(f"DROP DATABASE IF EXISTS {_DB}")
