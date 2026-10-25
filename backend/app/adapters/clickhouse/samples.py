"""Something worth looking at, put into an empty ClickHouse server (D280).

A server this application started for somebody is empty, and an empty server
demonstrates nothing, so one started with sample data is filled with the lab
the other servers' samples describe, told in what ClickHouse has: MergeTree
with partitions, a TTL, codecs and skipping indexes; ReplacingMergeTree and
SummingMergeTree; LowCardinality, Enum, Array, Map, Tuple, IPv4 and UUID;
a materialized view feeding a table and one keeping its own rows; a view; a
Log table; and two hundred thousand page views to read and add up. It lives in
a database of its own, `demo_lab`, which the script drops first.

Not an action and not a route: it is offered only where this server has just
started the database itself (D80).
"""

from pathlib import Path

from anyio import to_thread

from app.adapters.clickhouse.columns import ALTERING
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.sample_scripts import statements_of
from app.core.translation import say

SAMPLE_DATABASE = "demo_lab"
SCRIPT = Path(__file__).parent / "sample_data" / "clickhouse_lab.sql"

_TABLES = """
    SELECT count() AS tables FROM system.tables
    WHERE database = {database:String}
      AND engine NOT IN ('View', 'MaterializedView')
      AND NOT startsWith(name, '.inner')
"""


class ClickhouseSamples:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Run the script, and say what is now there."""
        script = await to_thread.run_sync(SCRIPT.read_text, "utf-8")
        for statement in statements_of(script):
            await self._session.command(statement, {}, settings=ALTERING)
        rows = await self._session.query(_TABLES, {"database": SAMPLE_DATABASE})
        return say("{schema}: {tables} tables", schema=SAMPLE_DATABASE, tables=int(rows[0]["tables"]))
