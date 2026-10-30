"""Runtime PostgreSQL feature composition (D119, D120)."""

import asyncio

from app.adapters.features import (
    MAX_SOURCE_EXTENSIONS,
    SourceExtension,
    SourceFeatures,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.profile import TimescaleProfile, discover
from app.adapters.protocol import AdapterError
from app.core.schemas import get_datetime_utc

# The number and nothing else. `current_setting` hands back the build, the
# distribution and sometimes the compiler, and none of that is what a person
# reading "what am I working on" is asking.
_VERSION_SQL = "SELECT split_part(current_setting('server_version'), ' ', 1) AS version"
# plpgsql is in every database from initdb on, so naming it says nothing about
# this one.
_EXTENSIONS_SQL = """
SELECT extname AS name, extversion AS version
FROM pg_catalog.pg_extension
WHERE extname <> 'plpgsql'
ORDER BY extname
LIMIT %s
"""


class PostgresFeatures:
    def __init__(self, session: PostgresSession) -> None:
        self._session = session
        self._timescale_task: asyncio.Future[TimescaleProfile] | None = None

    async def timescale(
        self, reader: PostgresReader | None = None
    ) -> TimescaleProfile:
        """What TimescaleDB offers here, discovered once per adapter.

        A caller's `reader` is a transaction it owns and closes. Discovery on
        it runs inline and only its answer is kept: a shared task on that
        connection would outlive the transaction for every other waiter, and
        a cancelled batch would leave the task cancelled for good.
        """
        task = self._timescale_task
        if task is None and reader is not None:
            profile = await discover(reader)
            if self._timescale_task is None:
                done: asyncio.Future[TimescaleProfile] = (
                    asyncio.get_running_loop().create_future()
                )
                done.set_result(profile)
                self._timescale_task = done
            return profile
        if task is None:
            task = asyncio.ensure_future(discover(self._session))
            self._timescale_task = task
        try:
            return await asyncio.shield(task)
        except Exception:
            if self._timescale_task is task and task.done():
                self._timescale_task = None
            raise

    async def server_version(self) -> str | None:
        """What the server says it is, or nothing when it would not say.

        Not worth failing over: the version is a line on a panel, while the
        features beside it are what a screen decides anything from.
        """
        try:
            rows = await self._session.query(_VERSION_SQL, inspection=True)
        except (AdapterError, ValueError):
            return None
        version = rows[0].get("version") if rows else None
        return version if isinstance(version, str) and version else None

    async def extensions(self) -> list[SourceExtension]:
        """Every installed extension, or none when the catalog would not say."""
        try:
            rows = await self._session.query(
                _EXTENSIONS_SQL, (MAX_SOURCE_EXTENSIONS,), inspection=True
            )
        except (AdapterError, ValueError):
            return []
        return [
            SourceExtension(name=row["name"], version=row["version"])
            for row in rows
            if isinstance(row.get("name"), str)
            and isinstance(row.get("version"), str)
            and row["name"]
            and row["version"]
        ]

    async def source_features(self) -> SourceFeatures:
        # Side by side: on a distant server every round trip is felt.
        timescale, version, extensions = await asyncio.gather(
            self.timescale(), self.server_version(), self.extensions()
        )
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=version,
            features=[timescale.feature],
            extensions=extensions,
        )
