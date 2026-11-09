"""What a Cassandra or ScyllaDB node says it is running (D120)."""

from app.adapters.cassandra.session import CassandraSession
from app.adapters.features import SourceFeatures
from app.adapters.protocol import AdapterError
from app.core.schemas import get_datetime_utc


class CassandraFeatures:
    def __init__(self, session: CassandraSession) -> None:
        self._session = session

    async def source_features(self) -> SourceFeatures:
        try:
            profile = await self._session.profile()
            version: str | None = f"{profile.product} {profile.text}"
        except AdapterError:
            version = None
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=version, features=[]
        )
