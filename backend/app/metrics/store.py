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
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.metrics.history import TierName
from app.metrics.migrations import ADVISORY_LOCK_KEY, MIGRATIONS, VERSION_TABLE
from app.metrics.protocol import HostDescription

CONNECT_TIMEOUT_SECONDS = 5

ProcessSort = Literal["pcpu", "pmem", "pid"]

_PROCESS_SELECT = """
    SELECT total, pid, ppid, username, state, pcpu, pmem, rss, started, name, command
    FROM metric_process
    WHERE source_id = :source AND host = :host AND ts = :at
"""

# One fixed statement per sort: the order is never assembled from a request.
_PROCESS_QUERIES: dict[ProcessSort, str] = {
    "pcpu": _PROCESS_SELECT + " ORDER BY pcpu DESC, pid LIMIT :limit",
    "pmem": _PROCESS_SELECT + " ORDER BY pmem DESC, pid LIMIT :limit",
    "pid": _PROCESS_SELECT + " ORDER BY pid LIMIT :limit",
}


_RAW_BUCKETS = """
    SELECT series_id,
           time_bucket(make_interval(secs => CAST(:width AS double precision)), ts) AS bucket,
           avg(value) AS mean, min(value) AS low, max(value) AS high
    FROM metric_point
    WHERE series_id = ANY(CAST(:ids AS bigint[]))
      AND ts >= :start AND ts <= :end
    GROUP BY series_id, bucket
    ORDER BY series_id, bucket
"""


def _rollup_buckets(view: str) -> str:
    # A rollup's buckets start inside the range; its own width is no wider
    # than the width asked, so at most one partial bucket is left at the start.
    # Grouped by position: `bucket` there would name the view's column, not
    # the wider one computed from it.
    return f"""
        SELECT series_id,
               time_bucket(make_interval(secs => CAST(:width AS double precision)), bucket)
                   AS bucket,
               sum(total) / sum(samples) AS mean, min(low) AS low, max(high) AS high
        FROM {view}
        WHERE series_id = ANY(CAST(:ids AS bigint[]))
          AND bucket >= :start AND bucket <= :end
        GROUP BY series_id, 2
        ORDER BY series_id, 2
    """  # noqa: S608  # the view is one of two names written below, never a request's


# One fixed statement per table: which one is read is never assembled from a request.
_BUCKET_QUERIES: dict[TierName, str] = {
    "raw": _RAW_BUCKETS,
    "5m": _rollup_buckets("metric_point_5m"),
    "1h": _rollup_buckets("metric_point_1h"),
}

ROLLUP_VIEWS: tuple[str, ...] = ("metric_point_5m", "metric_point_1h")

# "agent": a new agent process on the same boot. "host": the host booted again.
RestartCause = Literal["agent", "host"]


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
class Sample:
    metric: str
    field: str
    label: str
    unit: str
    ts: int
    value: float


@dataclass(frozen=True, slots=True)
class PointRow:
    series_id: int
    ts: int
    value: float


@dataclass(frozen=True, slots=True)
class ProcessRow:
    pid: int
    ppid: int
    user: str
    state: str
    pcpu: float
    pmem: float
    rss: int
    started: int
    name: str
    command: str


@dataclass(frozen=True, slots=True)
class ProcessPart:
    """One datagram's share of a process table. The parts of one table share
    their moment, so the table is every row written at it."""

    host: str
    ts: int
    total: int
    rows: Sequence[ProcessRow]


@dataclass(frozen=True, slots=True)
class LatestProcesses:
    ts: int
    total: int
    rows: list[ProcessRow]


@dataclass(frozen=True, slots=True)
class RestartRow:
    source_id: uuid.UUID
    host: str
    # When the new agent process started, not when that was noticed.
    ts: int
    cause: RestartCause


@dataclass(frozen=True, slots=True)
class AgentRunRow:
    """The newest agent process known to report a host."""

    source_id: uuid.UUID
    host: str
    instance: str
    version: str
    started: int
    boot: str


@dataclass(frozen=True, slots=True)
class HostRow:
    run: AgentRunRow
    # None until the agent sent what the host is.
    info: HostDescription | None
    info_at: datetime | None
    # When a series of the host was last written; None when none was.
    last_seen: datetime | None


@dataclass(frozen=True, slots=True)
class Usage:
    bytes: int
    series: int


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

    async def write_processes(self, source: Source, part: ProcessPart) -> None:
        if not part.rows:
            return
        rows = part.rows
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO metric_process
                        (source_id, host, ts, total, pid, ppid, username, state,
                         pcpu, pmem, rss, started, name, command)
                    SELECT CAST(:source AS uuid), CAST(:host AS text),
                           CAST(:moment AS timestamptz), CAST(:total AS integer),
                           * FROM unnest(
                        CAST(:pids AS integer[]), CAST(:ppids AS integer[]),
                        CAST(:users AS text[]), CAST(:states AS text[]),
                        CAST(:pcpus AS real[]), CAST(:pmems AS real[]),
                        CAST(:rss AS bigint[]), CAST(:started AS timestamptz[]),
                        CAST(:names AS text[]), CAST(:commands AS text[])
                    )
                    """
                ),
                {
                    "source": source.id,
                    "host": part.host,
                    "moment": _moment(part.ts),
                    "total": part.total,
                    "pids": [row.pid for row in rows],
                    "ppids": [row.ppid for row in rows],
                    "users": [row.user for row in rows],
                    "states": [row.state for row in rows],
                    "pcpus": [row.pcpu for row in rows],
                    "pmems": [row.pmem for row in rows],
                    "rss": [row.rss for row in rows],
                    "started": [_moment(row.started) for row in rows],
                    "names": [row.name for row in rows],
                    "commands": [row.command for row in rows],
                },
            )

    async def write_run(
        self, run: AgentRunRow, info: HostDescription | None = None, info_at: int = 0
    ) -> None:
        """Keep the newest agent process of a host, and what the host is when
        that was sent. A description already kept stays when none is given."""
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO metric_host
                        (source_id, host, instance, agent_version, agent_started, boot,
                         info, info_at)
                    VALUES (:source, :host, :instance, :version, :started, :boot,
                            CAST(:info AS jsonb), :info_at)
                    ON CONFLICT (source_id, host) DO UPDATE SET
                        instance = EXCLUDED.instance,
                        agent_version = EXCLUDED.agent_version,
                        agent_started = EXCLUDED.agent_started,
                        boot = EXCLUDED.boot,
                        info = coalesce(EXCLUDED.info, metric_host.info),
                        info_at = coalesce(EXCLUDED.info_at, metric_host.info_at)
                    """
                ),
                {
                    "source": run.source_id,
                    "host": run.host,
                    "instance": run.instance,
                    "version": run.version,
                    "started": _moment(run.started),
                    "boot": run.boot,
                    "info": None if info is None else info.model_dump_json(),
                    "info_at": None if info is None else _moment(info_at),
                },
            )

    async def runs(self) -> list[AgentRunRow]:
        """The newest agent process of every host of every agent."""
        rows = await self._fetch(
            "SELECT source_id, host, instance, agent_version, agent_started, boot FROM metric_host",
            {},
        )
        return [_run(row) for row in rows]

    async def hosts(self, sources: Sequence[uuid.UUID]) -> list[HostRow]:
        """What the hosts of these agents are, and when each was last heard."""
        if not sources:
            return []
        rows = await self._fetch(
            """
            SELECT h.source_id, h.host, h.instance, h.agent_version, h.agent_started, h.boot,
                   h.info, h.info_at,
                   (SELECT max(s.last_seen) FROM metric_series AS s
                    WHERE s.source_kind = 'agent' AND s.source_id = h.source_id
                      AND s.host = h.host) AS last_seen
            FROM metric_host AS h
            WHERE h.source_id = ANY(CAST(:sources AS uuid[]))
            ORDER BY h.host
            """,
            {"sources": list(sources)},
        )
        return [
            HostRow(
                run=_run(row),
                # Written by the collector from a checked body; read back as
                # JSON, where a tuple or a number type is not kept.
                info=None
                if row["info"] is None
                else HostDescription.model_validate(row["info"], strict=False),
                info_at=row["info_at"],
                last_seen=row["last_seen"],
            )
            for row in rows
        ]

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

    async def densest(
        self, series_ids: Sequence[int], start: int, end: int, *, cap: int
    ) -> int:
        """Points of the densest series in the range, counted no further than
        `cap`: past the budget the exact number changes nothing, and a week of
        a busy series is a long count."""
        rows = await self._fetch(
            """
            SELECT coalesce(max(counted.n), 0) AS densest
            FROM unnest(CAST(:ids AS bigint[])) AS asked(id)
            CROSS JOIN LATERAL (
                SELECT count(*) AS n FROM (
                    SELECT 1 FROM metric_point
                    WHERE series_id = asked.id AND ts >= :start AND ts <= :end
                    LIMIT :cap
                ) AS limited
            ) AS counted
            """,
            {
                "ids": list(series_ids),
                "start": _moment(start),
                "end": _moment(end),
                "cap": cap,
            },
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
        self,
        series_ids: Sequence[int],
        start: int,
        end: int,
        width: int,
        tier: TierName = "raw",
    ) -> dict[int, list[list[float]]]:
        """Buckets of `width`, read from the table `tier` names: raw samples or
        a rollup whose width divides it."""
        rows = await self._fetch(
            _BUCKET_QUERIES[tier],
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

    async def seen_series(self, series_ids: Sequence[int]) -> dict[int, int]:
        """When each of these series was last written, in seconds."""
        if not series_ids:
            return {}
        rows = await self._fetch(
            "SELECT id, last_seen FROM metric_series WHERE id = ANY(CAST(:ids AS bigint[]))",
            {"ids": list(series_ids)},
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
    ) -> LatestProcesses | None:
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
            return None
        rows = await self._fetch(
            _PROCESS_QUERIES[sort],
            {**parameters, "at": latest, "limit": limit},
        )
        return LatestProcesses(
            ts=_seconds(latest),
            total=max((int(row["total"]) for row in rows), default=0),
            rows=[
                ProcessRow(
                    pid=int(row["pid"]),
                    ppid=int(row["ppid"]),
                    user=str(row["username"]),
                    state=str(row["state"]),
                    pcpu=float(row["pcpu"]),
                    pmem=float(row["pmem"]),
                    rss=int(row["rss"]),
                    started=_seconds(row["started"]),
                    name=str(row["name"]),
                    command=str(row["command"]),
                )
                for row in rows
            ],
        )

    async def purge(self, source: Source) -> None:
        """Every sample, rollup, snapshot and restart of a source. Its series go
        with them."""
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
                for table in await _materialized(connection):
                    await connection.execute(
                        text(
                            f"DELETE FROM {table} WHERE series_id IN ("  # noqa: S608  # a name the store's catalog gave, quoted
                            "SELECT id FROM metric_series "
                            "WHERE source_kind = :kind AND source_id = :source)"
                        ),
                        ids,
                    )
                await connection.execute(
                    text("DELETE FROM metric_restart WHERE source_id = :source"),
                    {"source": source.id},
                )
                await connection.execute(
                    text("DELETE FROM metric_process WHERE source_id = :source"),
                    {"source": source.id},
                )
                await connection.execute(
                    text("DELETE FROM metric_host WHERE source_id = :source"),
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

    async def write_restart(self, restart: RestartRow) -> None:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO metric_restart (source_id, host, ts, cause) "
                        "VALUES (:source, :host, :ts, :cause)"
                    ),
                    {
                        "source": restart.source_id,
                        "host": restart.host,
                        "ts": _moment(restart.ts),
                        "cause": restart.cause,
                    },
                )
        except (SQLAlchemyError, OSError) as failure:
            raise StoreUnavailable("The metrics store did not answer") from failure

    async def restarts_since(
        self, sources: Sequence[uuid.UUID], since: int
    ) -> list[RestartRow]:
        """Restarts of these sources after a moment, oldest first."""
        if not sources:
            return []
        rows = await self._fetch(
            """
            SELECT source_id, host, ts, cause FROM metric_restart
            WHERE source_id = ANY(CAST(:sources AS uuid[])) AND ts > :since
            ORDER BY ts
            """,
            {"sources": list(sources), "since": _moment(since)},
        )
        return [
            RestartRow(
                source_id=row["source_id"],
                host=str(row["host"]),
                ts=_seconds(row["ts"]),
                cause="host" if row["cause"] == "host" else "agent",
            )
            for row in rows
        ]

    async def usage(self) -> Usage:
        """What the samples take on disk, rollups and snapshots included."""
        rows = await self._fetch(
            """
            SELECT
                (SELECT coalesce(sum(hypertable_size(format('%I.%I',
                        hypertable_schema, hypertable_name)::regclass)), 0)
                 FROM timescaledb_information.hypertables
                 WHERE hypertable_name IN ('metric_point', 'metric_process', 'metric_restart'))
                + (SELECT coalesce(sum(hypertable_size(format('%I.%I',
                        view_schema, view_name)::regclass)), 0)
                   FROM timescaledb_information.continuous_aggregates
                   WHERE view_name IN ('metric_point_5m', 'metric_point_1h'))
                    AS bytes,
                (SELECT count(*) FROM metric_series) AS series
            """,
            {},
        )
        return Usage(bytes=int(rows[0]["bytes"]), series=int(rows[0]["series"]))

    async def drop_schema(self) -> None:
        """Take away everything the migrations made, and leave the database.

        For a store somebody connected: the database is theirs, what is in it
        of the metrics is not.
        """
        statements = (
            "DROP MATERIALIZED VIEW IF EXISTS metric_point_1h CASCADE",
            "DROP MATERIALIZED VIEW IF EXISTS metric_point_5m CASCADE",
            "DROP TABLE IF EXISTS metric_host, metric_restart, metric_process, metric_point, "
            "metric_series, metrics_schema_version CASCADE",
        )
        try:
            async with self._engine.connect() as raw:
                connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
                await connection.execute(
                    text("SELECT pg_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
                )
                try:
                    for statement in statements:
                        await connection.execute(text(statement))
                finally:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"),
                        {"key": ADVISORY_LOCK_KEY},
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


async def _materialized(connection: AsyncConnection) -> list[str]:
    """The tables the rollups keep their rows in, quoted.

    A rollup cannot be deleted from through its view, and a refresh does not
    reach back past its window, so a purge deletes from these directly.
    """
    rows = await connection.execute(
        text(
            """
            SELECT format('%I.%I', materialization_hypertable_schema,
                          materialization_hypertable_name) AS name
            FROM timescaledb_information.continuous_aggregates
            WHERE view_name = ANY(CAST(:views AS text[]))
            """
        ),
        {"views": list(ROLLUP_VIEWS)},
    )
    return [str(name) for name in rows.scalars()]


def _run(row: Mapping[str, Any]) -> AgentRunRow:
    return AgentRunRow(
        source_id=row["source_id"],
        host=str(row["host"]),
        instance=str(row["instance"]),
        version=str(row["agent_version"]),
        started=_seconds(row["agent_started"]),
        boot=str(row["boot"]),
    )


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
