"""Read-only TimescaleDB discovery through PostgreSQL catalogs (D120)."""

from dataclasses import dataclass

from app.adapters.features import SourceFeature
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError

_EXTENSION_SQL = """
SELECT oid, extversion AS version
FROM pg_catalog.pg_extension
WHERE extname = %s
"""

_BASELINE_API_SQL = """
SELECT relation.relname AS view_name, attribute.attname AS column_name
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = relation.oid
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
 AND dependency.objid = relation.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.refobjid = %s
 AND dependency.deptype = 'e'
WHERE namespace.nspname = 'timescaledb_information'
  AND relation.relkind IN ('v', 'm')
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped
  AND (
    (relation.relname = 'hypertables'
      AND attribute.attname IN ('hypertable_schema', 'hypertable_name'))
    OR
    (relation.relname = 'continuous_aggregates'
      AND attribute.attname IN ('view_schema', 'view_name'))
  )
"""

_BASELINE_COLUMNS = frozenset(
    {
        ("hypertables", "hypertable_schema"),
        ("hypertables", "hypertable_name"),
        ("continuous_aggregates", "view_schema"),
        ("continuous_aggregates", "view_name"),
    }
)

_INSPECTION_REFUSALS = {
    "42501": "This connection may not inspect installed extensions",
}


@dataclass(frozen=True)
class TimescaleProfile:
    feature: SourceFeature

    @property
    def available(self) -> bool:
        return self.feature.state == "available"


def _unavailable(reason: str, *, version: str | None = None) -> TimescaleProfile:
    return TimescaleProfile(
        SourceFeature(
            code="timescaledb",
            title="TimescaleDB",
            installed_version=version,
            state="unavailable",
            reason=reason,
        )
    )


def _raise_connection_failure(exc: AdapterError) -> None:
    if exc.error_kind in {"auth", "network", "timeout"}:
        raise exc


async def discover(session: PostgresSession) -> TimescaleProfile:
    """Describe Timescale without calling an extension function as a probe."""
    try:
        installed = await session.query(
            _EXTENSION_SQL,
            ("timescaledb",),
            refusals=_INSPECTION_REFUSALS,
        )
    except ValueError:
        return _unavailable("This connection may not inspect installed extensions")
    except AdapterError as exc:
        _raise_connection_failure(exc)
        return _unavailable("Installed extensions could not be inspected")

    if not installed:
        return TimescaleProfile(
            SourceFeature(
                code="timescaledb",
                title="TimescaleDB",
                state="absent",
            )
        )

    extension = installed[0]
    version = extension.get("version")
    extension_oid = extension.get("oid")
    if not isinstance(version, str) or not version:
        return _unavailable("The installed TimescaleDB version could not be read")
    if not isinstance(extension_oid, int) or isinstance(extension_oid, bool):
        return _unavailable(
            "TimescaleDB extension metadata could not be read", version=version
        )

    if version.partition(".")[0] != "2":
        return TimescaleProfile(
            SourceFeature(
                code="timescaledb",
                title="TimescaleDB",
                installed_version=version,
                state="unsupported",
                reason="This TimescaleDB major version is not supported",
            )
        )

    try:
        columns = await session.query(
            _BASELINE_API_SQL,
            (extension_oid,),
            refusals=_INSPECTION_REFUSALS,
        )
    except ValueError:
        return _unavailable(
            "This connection may not inspect TimescaleDB metadata", version=version
        )
    except AdapterError as exc:
        _raise_connection_failure(exc)
        return _unavailable(
            "TimescaleDB metadata could not be inspected", version=version
        )

    found = {
        (row.get("view_name"), row.get("column_name"))
        for row in columns
        if isinstance(row.get("view_name"), str)
        and isinstance(row.get("column_name"), str)
    }
    if not _BASELINE_COLUMNS <= found:
        return TimescaleProfile(
            SourceFeature(
                code="timescaledb",
                title="TimescaleDB",
                installed_version=version,
                state="unsupported",
                reason="The installed version lacks the supported inspection API",
            )
        )

    return TimescaleProfile(
        SourceFeature(
            code="timescaledb",
            title="TimescaleDB",
            installed_version=version,
            state="available",
        )
    )
