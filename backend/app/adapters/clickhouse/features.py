"""What a ClickHouse server says it is running (D120)."""

from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.features import SourceFeatures
from app.adapters.protocol import AdapterError
from app.core.schemas import get_datetime_utc


class ClickhouseFeatures:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def source_features(self) -> SourceFeatures:
        try:
            version: str | None = f"ClickHouse {(await self._session.profile()).text}"
        except (AdapterError, ValueError):
            version = None
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=version, features=[]
        )
