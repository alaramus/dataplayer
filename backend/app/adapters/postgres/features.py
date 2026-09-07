"""Runtime PostgreSQL feature composition (D119, D120)."""

import asyncio

from app.adapters.features import SourceFeatures
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.profile import TimescaleProfile, discover
from app.core.schemas import get_datetime_utc


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

    async def source_features(self) -> SourceFeatures:
        timescale = await self.timescale()
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            features=[timescale.feature],
        )
