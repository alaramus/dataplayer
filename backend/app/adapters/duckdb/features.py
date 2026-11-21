"""What engine this server reads DuckDB files with (D120)."""

from app.adapters.duckdb.session import library_version
from app.adapters.features import SourceFeatures
from app.core.schemas import get_datetime_utc


class DuckdbFeatures:
    async def source_features(self) -> SourceFeatures:
        """The engine's version: a file written by a newer one may not open (D387)."""
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=f"DuckDB {library_version()}",
            features=[],
        )
