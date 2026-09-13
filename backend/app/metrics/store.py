"""The installation's metrics store: a TimescaleDB of its own (D126).

Reached through SQLAlchemy's async engine, the way the application database is
in `app/core/db.py`: this is a second database of the application, not a source
somebody connected, so it goes neither through an adapter nor through psycopg
directly. Every statement is fixed text with bound values.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.metrics.migrations import ADVISORY_LOCK_KEY, MIGRATIONS, VERSION_TABLE
from app.metrics.packets import ProcessRow, ProcessSnapshot, Sample

CONNECT_TIMEOUT_SECONDS = 5

ProcessSort = Literal["pcpu", "pmem", "pid"]

_PROCESS_SELECT = """
    SELECT pid, ppid, username, command, pcpu, pmem, elapsed FROM metric_process
    WHERE source_id = :source AND host = :host AND ts = :at
"""

# One fixed statement per sort: the order is never assembled from a request.
_PROCESS_QUERIES: dict[ProcessSort, str] = {
    "pcpu": _PROCESS_SELECT + " ORDER BY pcpu DESC, pid LIMIT :limit",
    "pmem": _PROCESS_SELECT + " ORDER BY pmem DESC, pid LIMIT :limit",
    "pid": _PROCESS_SELECT + " ORDER BY pid LIMIT :limit",
}


class StoreUnavailable(Exception):
    """The store did not answer. Driver text stays in the log, never here."""


@dataclass(frozen=True, slots=True)
class Source:
    kind: str
    id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SeriesKey:
    host: str
    metric: str
    field: str
    label: str


@dataclass(frozen=True, slots=True)
class StoredSeries:
    id: int
    source: Source
    host: str
    metric: str
    field: str
    label: str
    unit: str
    first_seen: datetime
    last_seen: datetime


@dataclass(frozen=True, slots=True)
class PointRow:
    series_id: int
    ts: int
    value: float


def store_url(options: Mapping[str, Any]) -> URL:
    """The address of the store, from the PostgreSQL adapter's options."""
    password = options.get("password")
    return URL.create(
        "postgresql+psycopg",
        username=str(options["user"]),
        password=str(password) if password is not None else None,
        host=str(options["host"]),
        port=int(options["port"]),
        database=str(options["database"]),
    )


def _moment(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _seconds(moment: datetime) -> int:
    return int(moment.timestamp())


class MetricsStore:
    def __init__(self, url: URL) -> None:
        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_size=4,
            max_overflow=4,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": CONNECT_TIMEOUT_SECONDS,
                "application_name": "dataplayer-metrics",
            },
        )

    async def aclose(self) -> None:
        await self._engine.dispose()

    async def ping(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError):
            return False
        return True

    async def migrate(self) -> int:
        """Apply what is missing. Returns the version the store is at."""
        try:
            async with self._engine.connect() as raw:
                connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
                await connection.execute(
                    text("SELECT pg_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
                )
                try:
                    await connection.execute(text(VERSION_TABLE))
                    applied = set(
                        (
                            await connection.execute(
                                text("SELECT version FROM metrics_schema_version")
                            )
                        ).scalars()
                    )
                    for migration in MIGRATIONS:
                        if migration.version in applied:
                            continue
                        for statement in migration.statements:
                            await connection.execute(text(statement))
                        await connection.execute(
                            text(
                                "INSERT INTO metrics_schema_version (version) "
                                "VALUES (:version) ON CONFLICT DO NOTHING"
                            ),
                            {"version": migration.version},
                        )
                finally:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"),
                        {"key": ADVISORY_LOCK_KEY},
                    )
        except (SQLAlchemyError, OSError) as failure:
            raise StoreUnavailable("The metrics store could not be prepared") from failure
        return MIGRATIONS[-1].version

    async def series_ids(
        self, source: Source, samples: Sequence[tuple[SeriesKey, str, int]]
    ) -> dict[SeriesKey, int]:
        """The id of each series, minting the ones never seen.

        Insert-or-select against the unique identity, so two writers converge
        on one row. `samples` carries the unit and the moment it was seen.
        """
        ids: dict[SeriesKey, int] = {}
        statement = text(
            """
            INSERT INTO metric_series
                (source_kind, source_id, host, metric, field, label, unit,
                 first_seen, last_seen)
            VALUES (:kind, :source, :host, :metric, :field, :label, :unit, :seen, :seen)
            ON CONFLICT (source_kind, source_id, host, metric, field, label)
            DO UPDATE SET last_seen = greatest(metric_series.last_seen, EXCLUDED.last_seen)
            RETURNING id
            """
        )
        async with self._engine.begin() as connection:
            for key, unit, ts in samples:
                if key in ids:
                    continue
                result = await connection.execute(
                    statement,
                    {
                        "kind": source.kind,
                        "source": source.id,
                        "host": key.host,
                        "metric": key.metric,
                        "field": key.field,
                        "label": key.label,
                        "unit": unit,
                        "seen": _moment(ts),
                    },
                )
                ids[key] = int(result.scalar_one())
        return ids

    async def write_points(self, points: Sequence[PointRow]) -> None:
        if not points:
            return
        last: dict[int, int] = {}
        for point in points:
            last[point.series_id] = max(point.ts, last.get(point.series_id, 0))
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO metric_point (series_id, ts, value)
                    SELECT * FROM unnest(
                        CAST(:ids AS bigint[]),
                        CAST(:moments AS timestamptz[]),
                        CAST(:values AS double precision[])
                    )
                    """
                ),
                {
                    "ids": [point.series_id for point in points],
                    "moments": [_moment(point.ts) for point in points],
                    # One type for the array: psycopg refuses a list mixing int and float.
                    "values": [float(point.value) for point in points],
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE metric_series AS s
                    SET last_seen = greatest(s.last_seen, u.moment)
                    FROM unnest(CAST(:ids AS bigint[]), CAST(:moments AS timestamptz[]))
                        AS u(id, moment)
                    WHERE s.id = u.id
                    """
                ),
                {"ids": list(last), "moments": [_moment(ts) for ts in last.values()]},
            )

    async def write_processes(self, source: Source, snapshot: ProcessSnapshot) -> None:
        if not snapshot.rows:
            return
        rows = snapshot.rows
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO metric_process
                        (source_id, host, ts, pid, ppid, username, command,
                         pcpu, pmem, elapsed)
                    SELECT CAST(:source AS uuid), CAST(:host AS text),
                           CAST(:moment AS timestamptz), * FROM unnest(
                        CAST(:pids AS integer[]), CAST(:ppids AS integer[]),
                        CAST(:users AS text[]), CAST(:commands AS text[]),
                        CAST(:pcpus AS real[]), CAST(:pmems AS real[]),
                        CAST(:elapsed AS text[])
                    )
                    """
                ),
                {
                    "source": source.id,
                    "host": snapshot.host,
                    "moment": _moment(snapshot.ts),
                    "pids": [row.pid for row in rows],
                    "ppids": [row.ppid for row in rows],
                    "users": [row.user for row in rows],
                    "commands": [row.command for row in rows],
                    "pcpus": [row.pcpu for row in rows],
                    "pmems": [row.pmem for row in rows],
                    "elapsed": [row.elapsed for row in rows],
                },
            )

    async def catalog(self, sources: Sequence[uuid.UUID]) -> list[StoredSeries]:
        """Every series of the given sources, agents and connections alike."""
        if not sources:
            return []
        rows = await self._fetch(
            """
            SELECT id, source_kind, source_id, host, metric, field, label, unit,
                   first_seen, last_seen
            FROM metric_series
            WHERE source_id = ANY(CAST(:sources AS uuid[]))
            ORDER BY host, metric, field, label
            """,
            {"sources": list(sources)},
        )
        return [_stored(row) for row in rows]

    async def series(self, series_ids: Sequence[int]) -> list[StoredSeries]:
        rows = await self._fetch(
            """
            SELECT id, source_kind, source_id, host, metric, field, label, unit,
                   first_seen, last_seen
            FROM metric_series WHERE id = ANY(CAST(:ids AS bigint[]))
            """,
            {"ids": list(series_ids)},
        )
        return [_stored(row) for row in rows]

    async def last_heard(self, sources: Sequence[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        if not sources:
            return {}
        rows = await self._fetch(
            """
            SELECT source_id, max(last_seen) AS heard FROM metric_series
            WHERE source_id = ANY(CAST(:sources AS uuid[]))
            GROUP BY source_id
            """,
            {"sources": list(sources)},
        )
        return {row["source_id"]: row["heard"] for row in rows}

    async def densest(self, series_ids: Sequence[int], start: int, end: int) -> int:
        rows = await self._fetch(
            """
            SELECT coalesce(max(n), 0) AS densest FROM (
                SELECT count(*) AS n FROM metric_point
                WHERE series_id = ANY(CAST(:ids AS bigint[]))
                  AND ts >= :start AND ts <= :end
                GROUP BY series_id
            ) AS counts
            """,
            {"ids": list(series_ids), "start": _moment(start), "end": _moment(end)},
        )
        return int(rows[0]["densest"])

    async def raw_points(
        self, series_ids: Sequence[int], start: int, end: int
    ) -> dict[int, list[list[float]]]:
        rows = await self._fetch(
            """
            SELECT series_id, ts, value FROM metric_point
            WHERE series_id = ANY(CAST(:ids AS bigint[]))
              AND ts >= :start AND ts <= :end
            ORDER BY series_id, ts
            """,
            {"ids": list(series_ids), "start": _moment(start), "end": _moment(end)},
        )
        points: dict[int, list[list[float]]] = {}
        for row in rows:
            points.setdefault(int(row["series_id"]), []).append(
                [float(_seconds(row["ts"])), float(row["value"])]
            )
        return points

    async def bucketed_points(
        self, series_ids: Sequence[int], start: int, end: int, width: int
    ) -> dict[int, list[list[float]]]:
        rows = await self._fetch(
            """
            SELECT series_id,
                   time_bucket(make_interval(secs => CAST(:width AS double precision)), ts)
                       AS bucket,
                   avg(value) AS mean, min(value) AS low, max(value) AS high
            FROM metric_point
            WHERE series_id = ANY(CAST(:ids AS bigint[]))
              AND ts >= :start AND ts <= :end
            GROUP BY series_id, bucket
            ORDER BY series_id, bucket
            """,
            {
                "ids": list(series_ids),
                "start": _moment(start),
                "end": _moment(end),
                "width": width,
            },
        )
        points: dict[int, list[list[float]]] = {}
        for row in rows:
            points.setdefault(int(row["series_id"]), []).append(
                [
                    float(_seconds(row["bucket"])),
                    float(row["mean"]),
                    float(row["low"]),
                    float(row["high"]),
                ]
            )
        return points

    async def seen(self, sources: Sequence[uuid.UUID]) -> dict[int, int]:
        """When each series of these sources was last written, in seconds."""
        if not sources:
            return {}
        rows = await self._fetch(
            """
            SELECT id, last_seen FROM metric_series
            WHERE source_id = ANY(CAST(:sources AS uuid[]))
            """,
            {"sources": list(sources)},
        )
        return {int(row["id"]): _seconds(row["last_seen"]) for row in rows}

    async def points_after(
        self, series_ids: Sequence[int], after: int, limit: int
    ) -> list[PointRow]:
        """Points newer than a moment, oldest first, at most `limit` of them."""
        if not series_ids:
            return []
        rows = await self._fetch(
            """
            SELECT series_id, ts, value FROM metric_point
            WHERE series_id = ANY(CAST(:ids AS bigint[])) AND ts > :after
            ORDER BY ts
            LIMIT :limit
            """,
            {"ids": list(series_ids), "after": _moment(after), "limit": limit},
        )
        return [
            PointRow(series_id=int(row["series_id"]), ts=_seconds(row["ts"]), value=float(row["value"]))
            for row in rows
        ]

    async def process_hosts(self, sources: Sequence[uuid.UUID]) -> dict[tuple[uuid.UUID, str], datetime]:
        """Hosts of these agents that sent a process table in the last day."""
        if not sources:
            return {}
        rows = await self._fetch(
            """
            SELECT source_id, host, max(ts) AS latest FROM metric_process
            WHERE source_id = ANY(CAST(:sources AS uuid[]))
              AND ts > now() - INTERVAL '1 day'
            GROUP BY source_id, host
            """,
            {"sources": list(sources)},
        )
        return {(row["source_id"], str(row["host"])): row["latest"] for row in rows}

    async def latest_processes(
        self, source_id: uuid.UUID, host: str, sort: ProcessSort, limit: int
    ) -> tuple[int | None, list[ProcessRow]]:
        """The newest process table of a host within the last hour."""
        parameters = {"source": source_id, "host": host}
        newest = await self._fetch(
            """
            SELECT max(ts) AS latest FROM metric_process
            WHERE source_id = :source AND host = :host
              AND ts > now() - INTERVAL '1 hour'
            """,
            parameters,
        )
        latest = newest[0]["latest"] if newest else None
        if latest is None:
            return None, []
        rows = await self._fetch(
            _PROCESS_QUERIES[sort],
            {**parameters, "at": latest, "limit": limit},
        )
        return _seconds(latest), [
            ProcessRow(
                pid=int(row["pid"]),
                ppid=int(row["ppid"]),
                user=str(row["username"]),
                command=str(row["command"]),
                pcpu=float(row["pcpu"]),
                pmem=float(row["pmem"]),
                elapsed=str(row["elapsed"]),
            )
            for row in rows
        ]

    async def purge(self, source: Source) -> None:
        """Every sample and snapshot of a source. Its series go with them."""
        try:
            async with self._engine.begin() as connection:
                ids = {"kind": source.kind, "source": source.id}
                await connection.execute(
                    text(
                        """
                        DELETE FROM metric_point WHERE series_id IN (
                            SELECT id FROM metric_series
                            WHERE source_kind = :kind AND source_id = :source
                        )
                        """
                    ),
                    ids,
                )
                await connection.execute(
                    text("DELETE FROM metric_process WHERE source_id = :source"),
                    {"source": source.id},
                )
                await connection.execute(
                    text(
                        "DELETE FROM metric_series "
                        "WHERE source_kind = :kind AND source_id = :source"
                    ),
                    ids,
                )
        except (SQLAlchemyError, OSError) as failure:
            raise StoreUnavailable("The metrics store did not answer") from failure

    async def _fetch(self, sql: str, parameters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(text(sql), dict(parameters))
                return [dict(row) for row in result.mappings().all()]
        except (SQLAlchemyError, OSError) as failure:
            raise StoreUnavailable("The metrics store did not answer") from failure


def _stored(row: Mapping[str, Any]) -> StoredSeries:
    return StoredSeries(
        id=int(row["id"]),
        source=Source(kind=str(row["source_kind"]), id=row["source_id"]),
        host=str(row["host"]),
        metric=str(row["metric"]),
        field=str(row["field"]),
        label=str(row["label"]),
        unit=str(row["unit"]),
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    )


def samples_by_key(samples: Sequence[Sample], host: str) -> list[tuple[SeriesKey, str, int]]:
    return [
        (SeriesKey(host=host, metric=s.metric, field=s.field, label=s.label), s.unit, s.ts)
        for s in samples
    ]
