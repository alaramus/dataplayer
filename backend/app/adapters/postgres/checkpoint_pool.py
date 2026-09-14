"""The connection pool the agent's working state is kept through (D139).

Here and not in the agent's package because it is `psycopg`, and the driver
stays inside this adapter. What the pool holds is LangGraph's business: this
module only opens it with the settings LangGraph's saver requires — autocommit,
rows as dictionaries and no prepared statements, which a pool cannot share.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

CheckpointPool = AsyncConnectionPool[AsyncConnection[DictRow]]


def libpq_url(url: str) -> str:
    """The application's SQLAlchemy URL as libpq reads it: without the driver."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def checkpoint_pool(url: str, *, max_size: int) -> AsyncIterator[CheckpointPool]:
    pool = cast(
        CheckpointPool,
        AsyncConnectionPool(
            libpq_url(url),
            min_size=1,
            max_size=max_size,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        ),
    )
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()
