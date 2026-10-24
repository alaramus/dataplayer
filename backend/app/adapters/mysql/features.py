"""What a MySQL server says it is running (D120)."""

from app.adapters.features import SourceFeatures
from app.adapters.mysql.session import MysqlSession
from app.adapters.protocol import AdapterError
from app.core.schemas import get_datetime_utc


class MysqlFeatures:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def source_features(self) -> SourceFeatures:
        """The flavour and the number, and no optional features yet.

        "MariaDB 11.4.13" rather than the number alone: one source type speaks
        to both, and which one it is is the first thing a person asks (D228).
        """
        try:
            profile = await self._session.profile()
            version: str | None = (
                f"{'MariaDB' if profile.mariadb else 'MySQL'} {profile.text}"
            )
        except (AdapterError, ValueError):
            version = None
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=version, features=[]
        )
