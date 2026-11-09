"""A keyspace of known shape on each CQL server the suite talks to (D340).

Built through the adapter's own session, which runs a statement as it is when
nothing is bound, and rebuilt by every module that asks for it. Every test runs
against Cassandra and ScyllaDB both; on a machine short of memory one runs at a
time, and the other's tests are skipped.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.cassandra.options import CassandraUserPassword
from app.adapters.cassandra.session import CassandraSession, options_from_url
from app.adapters.resources import Pooling, ResourceStore
from tests.utils.services import CASSANDRA, SCYLLA, Server

KEYSPACE = "dp_test_cql"
# A table's name is letters, digits and underscores; one in mixed case must
# be quoted, and a column's name may be anything quoted.
ODD = "OddName"
MANY_ROWS = 250


def _schema(scylla: bool) -> list[str]:
    # ScyllaDB keeps a keyspace in tablets unless told not to, and a
    # materialized view and a secondary index want the classic layout.
    tablets = " AND tablets = {'enabled': false}" if scylla else ""
    return [
        f"DROP KEYSPACE IF EXISTS {KEYSPACE}",
        f"CREATE KEYSPACE {KEYSPACE} WITH replication = "
        "{'class': 'NetworkTopologyStrategy', 'datacenter1': 1}" + tablets,
        f"CREATE TYPE {KEYSPACE}.address (street text, zip int)",
        f"""
        CREATE TABLE {KEYSPACE}.items (
            shop text,
            id int,
            at timestamp,
            label text,
            amount decimal,
            big varint,
            ratio double,
            small float,
            ok boolean,
            uid uuid,
            tid timeuuid,
            addr inet,
            day date,
            clock time,
            span duration,
            data blob,
            tags list<text>,
            uniq set<int>,
            attrs map<text, int>,
            counts map<int, text>,
            pair tuple<int, text>,
            home frozen<address>,
            note text static,
            PRIMARY KEY ((shop), id, at)
        ) WITH CLUSTERING ORDER BY (id ASC, at DESC) AND comment = 'Things'
        """,
        f"CREATE INDEX items_label ON {KEYSPACE}.items (label)",
        f"""
        CREATE MATERIALIZED VIEW {KEYSPACE}.items_by_ok AS
            SELECT shop, id, at, ok FROM {KEYSPACE}.items
            WHERE ok IS NOT NULL AND shop IS NOT NULL AND id IS NOT NULL AND at IS NOT NULL
            PRIMARY KEY ((ok), shop, id, at)
        """,
        f"CREATE TABLE {KEYSPACE}.many (p int PRIMARY KEY, v int, word text)",
        f'CREATE TABLE {KEYSPACE}."OddName" ("x y" int PRIMARY KEY)',
    ]


_ITEM = (
    f"INSERT INTO {KEYSPACE}.items (shop, id, at, label, amount, big, ratio, small, ok,"
    " uid, tid, addr, day, clock, span, data, tags, uniq, attrs, counts, pair, home, note)"
    " VALUES ('north', 1, '2024-01-02T03:04:05.120Z', 'alpha', 12345678901234567890.0123456789,"
    " 123456789012345678901234567890, 0.1, 1.5, true,"
    " 00000000-0000-0000-0000-000000000001, 50554d6e-29bb-11e5-b345-feff819cdc9f,"
    " '10.0.0.1', '2024-02-03', '12:30:00.000000001', 1mo2d3h4m5s6ms7us8ns, 0x00ff,"
    " ['a', 'b\"c'], {3, 1}, {'k': 1}, {2: 'two'}, (1, 'x'),"
    " {street: 'Main', zip: 10}, 'North shop')"
)
_ITEMS_MORE = [
    f"INSERT INTO {KEYSPACE}.items (shop, id, at, label, ok) VALUES ('north', 2, '2024-01-01T00:00:00Z', '50% off', false)",
    f"INSERT INTO {KEYSPACE}.items (shop, id, at, label, ratio) VALUES ('south', 3, '2024-01-01T00:00:00Z', 'under_score', NaN)",
]


@dataclass(frozen=True)
class Target:
    server: Server
    flavour: str

    @property
    def scylla(self) -> bool:
        return self.flavour == "scylla"

    def options(self, **override: object) -> CassandraUserPassword:
        values = {**options_from_url(self.server.require()), **override}
        return CassandraUserPassword(**values)

    def adapter(self, **override: object) -> CassandraAdapter:
        return CassandraAdapter(self.options(**override))

    def session(self, store: ResourceStore | None = None) -> CassandraSession:
        pooling = (
            None if store is None else Pooling(store=store, connector_id=uuid.uuid4())
        )
        return CassandraSession(self.options(), pooling)


TARGETS = [Target(CASSANDRA, "cassandra"), Target(SCYLLA, "scylla")]


async def run(
    target: Target, *statements: str, params: Sequence[Any] | None = None
) -> None:
    store = ResourceStore(max_entries=1, max_idle_seconds=600)
    try:
        session = target.session(store)
        for statement in statements:
            await session.page(statement, params, wait_seconds=60)
    finally:
        await store.aclose()


async def build(target: Target) -> None:
    await run(target, *_schema(target.scylla))
    await run(target, _ITEM, *_ITEMS_MORE)
    store = ResourceStore(max_entries=1, max_idle_seconds=600)
    try:
        session = target.session(store)
        for value in range(MANY_ROWS):
            await session.page(
                f"INSERT INTO {KEYSPACE}.many (p, v, word) VALUES (?, ?, ?)",
                [value, value % 10, f"w{value}"],
            )
        await session.page(f'INSERT INTO {KEYSPACE}."OddName" ("x y") VALUES (7)')
    finally:
        await store.aclose()


async def tear_down(target: Target) -> None:
    await run(target, f"DROP KEYSPACE IF EXISTS {KEYSPACE}")
