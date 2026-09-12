"""Runtime PostgreSQL feature composition (D119, D120)."""

import asyncio

from app.adapters.features import SourceFeatures
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.profile import TimescaleProfile, discover
from app.adapters.protocol import AdapterError
from app.core.schemas import get_datetime_utc

# The number and nothing else. `current_setting` hands back the build, the
# distribution and sometimes the compiler, and none of that is what a person
# reading "what am I working on" is asking.
_VERSION_SQL = "SELECT split_part(current_setting('server_version'), ' ', 1) AS version"


class PostgresFeatures:
    def __init__(self, session: PostgresSession) -> None:
        self._session = session
        self._timescale_task: asyncio.Task[TimescaleProfile] | None = None

    async def timescale(self) -> TimescaleProfile:
        task = self._timescale_task
        if task is None:
            task = asyncio.create_task(discover(self._session))
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

    async def source_features(self) -> SourceFeatures:
        timescale = await self.timescale()
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=await self.server_version(),
            features=[timescale.feature],
        )
