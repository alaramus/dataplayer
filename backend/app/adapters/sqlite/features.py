"""What library this server reads SQLite files with (D120)."""

from app.adapters.features import SourceFeatures
from app.adapters.sqlite.session import library_version
from app.core.schemas import get_datetime_utc


class SqliteFeatures:
    async def source_features(self) -> SourceFeatures:
        """The library's version: a file has none of its own to state."""
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=f"SQLite {library_version()}",
            features=[],
        )
