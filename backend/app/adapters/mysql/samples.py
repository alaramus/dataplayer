"""Something worth looking at, put into an empty MySQL or MariaDB server (D245).

A server this application started for somebody is empty, and an empty server
demonstrates nothing, so one started with sample data is filled with the lab
PostgreSQL's samples describe, told in what both MySQL and MariaDB have:
ENUM and SET, JSON, generated columns, checks, a partitioned table, full-text
and spatial keys, binary values, foreign keys, a view, a function, a trigger
and a table with no key. It lives in a database of its own, `demo_lab`, which
the script drops first.

Not an action and not a route: it is offered only where this server has just
started the database itself (D80).
"""

from pathlib import Path

from anyio import to_thread

from app.adapters.mysql.session import MysqlSession, QuietCursor
from app.adapters.sample_scripts import statements_of
from app.core.translation import say

SAMPLE_DATABASE = "demo_lab"
SCRIPT = Path(__file__).parent / "sample_data" / "mysql_lab.sql"


class MysqlSamples:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Run the script, and say what is now there.

        On a connection of its own, closed afterwards: the script chooses its
        database with USE, which a pooled connection would keep. Each statement
        is sent without parameters, so a `%` in it is a character.
        """
        script = await to_thread.run_sync(SCRIPT.read_text, "utf-8")
        async with self._session.acquire() as connection:
            try:
                # Quiet: a fresh server notes that there was no demo_lab to
                # drop, and that a shape key without an SRID is not used.
                async with connection.cursor(QuietCursor) as cursor:
                    for statement in statements_of(script):
                        await cursor.execute(statement)
                    await cursor.execute(
                        "SELECT COUNT(*) FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
                        (SAMPLE_DATABASE,),
                    )
                    (tables,) = await cursor.fetchone()
                await connection.commit()
            finally:
                connection.close()
        return say("{schema}: {tables} tables", schema=SAMPLE_DATABASE, tables=int(tables))
