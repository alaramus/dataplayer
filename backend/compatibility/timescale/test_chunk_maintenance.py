"""Chunk maintenance as reviewed jobs over fixed chunks (D208, H6)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused, OffersFieldHints
from app.adapters.postgres.timescale.chunk_maintenance_action import MaintainChunks
from app.adapters.postgres.timescale.reports import DETACHED_CHUNKS
from compatibility.timescale.policy_tables import PolicyTable, registry
from compatibility.timescale.source import TimescaleSource

_CHUNKS = """
    SELECT chunk_name, range_start::text AS range_start, range_end::text AS range_end, is_compressed
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY range_start
"""
# Six whole days in 2020, a chunk each.
_DAYS = 6


@pytest.fixture
async def table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    target = PolicyTable(f"maintain_{uuid.uuid4().hex[:12]}", "readings")
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    try:
        for statement in (
            "CREATE TABLE {} (observed_at timestamptz NOT NULL, device integer NOT NULL, value integer)",
            "SELECT create_hypertable({literal}::regclass, by_range('observed_at', interval '1 day'))",
            "INSERT INTO {} SELECT TIMESTAMPTZ '2020-01-01 00:00+00' + make_interval(hours => g), g % 3, g "
            "FROM generate_series(0, {hours}) AS g",
            "CREATE INDEX readings_device ON {} (device, observed_at)",
        ):
            await session.schema_change(sql.SQL(statement).format(
                target.identifier, literal=sql.Literal(target.identifier.as_string()),
                hours=sql.Literal(_DAYS * 24 - 1),
            ).as_string())
        yield target
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(
            sql.Identifier(target.schema),
        ).as_string())


def action(source: TimescaleSource, name: str) -> MaintainChunks[Any]:
    found = registry(source).action(name)
    assert isinstance(found, MaintainChunks)
    return found


async def run(source: TimescaleSource, target: PolicyTable, name: str, params: dict[str, Any]) -> list[str]:
    """Review, admit and carry out every unit, as the job handler does; the unit outcomes."""
    maintain = action(source, name)
    preview = await maintain.preview(target.node_id, params)
    assert not preview.blocked and preview.fingerprint is not None, preview.summary
    plan = await maintain.plan_job(target.node_id, params, preview.fingerprint)
    outcomes = [
        await maintain.run_unit(target.node_id, params, plan.unit_fingerprint, unit) for unit in plan.targets
    ]
    assert set(await maintain.observe(target.node_id, params, plan.targets)) <= {"as_requested", "unchanged"}
    return outcomes


async def refusal(source: TimescaleSource, target: PolicyTable, name: str, params: dict[str, Any]) -> str:
    preview = await action(source, name).preview(target.node_id, params)
    assert preview.blocked
    return preview.summary


async def chunks(source: TimescaleSource, target: PolicyTable) -> list[dict[str, Any]]:
    return await source.session().query(_CHUNKS, (target.schema, target.table))


def window(start_day: int | None, end_day: int) -> dict[str, Any]:
    return {
        "starts_from": None if start_day is None else f"2020-01-{start_day:02d}T00:00:00Z",
        "ends_by": f"2020-01-{end_day:02d}T00:00:00Z",
    }


async def test_drop_takes_exactly_the_reviewed_chunks(source: TimescaleSource, table: PolicyTable) -> None:
    preview = await action(source, "timescale_drop_chunks").preview(table.node_id, window(None, 3))
    assert preview.summary.startswith("Drop 2 chunks")
    assert await run(source, table, "timescale_drop_chunks", window(None, 3)) == ["completed", "completed"]

    left = await chunks(source, table)
    assert len(left) == _DAYS - 2 and left[0]["range_start"].startswith("2020-01-03")
    counted = await source.session().query(sql.SQL("SELECT count(*) AS n FROM {}").format(
        table.identifier,
    ).as_string())
    assert counted == [{"n": (_DAYS - 2) * 24}]


async def test_a_unit_whose_chunk_was_dropped_meanwhile_is_refused(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    maintain = action(source, "timescale_detach_chunks" if source.at_least("2.21.0") else "timescale_drop_chunks")
    params = window(None, 2)
    preview = await maintain.preview(table.node_id, params)
    assert preview.fingerprint is not None, preview.summary
    plan = await maintain.plan_job(table.node_id, params, preview.fingerprint)
    (first,) = plan.targets
    await source.session().schema_change(sql.SQL("DROP TABLE {}").format(
        sql.Identifier(first.schema_name, first.name),
    ).as_string())
    with pytest.raises(ActionRefused, match="no longer part of the hypertable"):
        await maintain.run_unit(table.node_id, params, plan.unit_fingerprint, first)


async def test_reorder_rewrites_uncompressed_chunks_by_an_index(source: TimescaleSource, table: PolicyTable) -> None:
    params = {**window(None, 3), "index": "readings_device"}
    assert await run(source, table, "timescale_reorder_chunks", params) == ["completed", "completed"]
    assert 'no index "missing"' in await refusal(
        source, table, "timescale_reorder_chunks", {**window(None, 3), "index": "missing"},
    )


async def test_merge_needs_adjacent_chunks_and_a_release_that_has_it(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    if not source.at_least("2.18.0"):
        assert "merge_chunks API is not usable" in await refusal(source, table, "timescale_merge_chunks", window(None, 4))
        return
    assert await run(source, table, "timescale_merge_chunks", window(None, 4)) == ["completed"]
    merged = await chunks(source, table)
    assert len(merged) == _DAYS - 2
    assert merged[0]["range_start"].startswith("2020-01-01") and merged[0]["range_end"].startswith("2020-01-04")

    # A gap: the window over the chunks either side of it is not one range.
    schema = await _chunk_schema(source, table)
    await source.session().schema_change(sql.SQL("DROP TABLE {}").format(
        sql.Identifier(schema, merged[2]["chunk_name"]),
    ).as_string())
    assert "are not adjacent" in await refusal(source, table, "timescale_merge_chunks", window(4, 7))


async def test_compressed_chunks_merge_from_2_19(source: TimescaleSource, table: PolicyTable) -> None:
    if not source.at_least("2.18.0"):
        pytest.skip("merge_chunks arrived in 2.18")
    session = source.session()
    await session.schema_change(sql.SQL(
        "ALTER TABLE {} SET (timescaledb.compress, timescaledb.compress_segmentby = '')"
    ).format(table.identifier).as_string())
    schema = await _chunk_schema(source, table)
    for row in (await chunks(source, table))[:2]:
        await session.query(
            "SELECT compress_chunk(%s::regclass)::text AS chunk",
            (sql.Identifier(schema, row["chunk_name"]).as_string(),),
        )
    if not source.at_least("2.19.0"):
        assert "cannot merge compressed chunks" in await refusal(
            source, table, "timescale_merge_chunks", window(None, 3),
        )
        return
    assert await run(source, table, "timescale_merge_chunks", window(None, 3)) == ["completed"]
    first = (await chunks(source, table))[0]
    assert first["range_end"].startswith("2020-01-03") and first["is_compressed"] is True


async def test_split_divides_the_chunk_holding_an_instant(source: TimescaleSource, table: PolicyTable) -> None:
    params = {"at": "2020-01-02T06:00:00Z"}
    if not source.at_least("2.20.0"):
        assert "split_chunk API is not usable" in await refusal(source, table, "timescale_split_chunk", params)
        return
    assert await run(source, table, "timescale_split_chunk", params) == ["completed"]
    ranges = [(row["range_start"][:16], row["range_end"][:16]) for row in await chunks(source, table)][:3]
    assert ranges == [
        ("2020-01-01 00:00", "2020-01-02 00:00"),
        ("2020-01-02 00:00", "2020-01-02 06:00"),
        ("2020-01-02 06:00", "2020-01-03 00:00"),
    ]
    assert "No chunk holds this point" in await refusal(
        source, table, "timescale_split_chunk", {"at": "2020-01-02T00:00:00Z"},
    )


async def test_a_detached_chunk_is_listed_and_attached_back(source: TimescaleSource, table: PolicyTable) -> None:
    if not source.at_least("2.21.0"):
        assert "detach_chunk API is not usable" in await refusal(
            source, table, "timescale_detach_chunks", window(None, 2),
        )
        return
    (detached,) = (await chunks(source, table))[:1]
    schema = await _chunk_schema(source, table)
    assert await run(source, table, "timescale_detach_chunks", window(None, 2)) == ["completed"]
    assert len(await chunks(source, table)) == _DAYS - 1

    listed = await source.session().query(DETACHED_CHUNKS.statement.as_string())
    assert {"table_schema": schema, "table_name": detached["chunk_name"]} in [
        {key: row[key] for key in ("table_schema", "table_name")} for row in listed
    ]

    overlapping = {
        "table_schema": schema, "table_name": detached["chunk_name"],
        "starts_from": "2020-01-01T00:00:00Z", "ends_by": "2020-01-03T00:00:00Z",
    }
    assert "already covers part of this range" in await refusal(
        source, table, "timescale_attach_chunk", overlapping,
    )
    params = {**overlapping, "ends_by": "2020-01-02T00:00:00Z"}
    assert await run(source, table, "timescale_attach_chunk", params) == ["completed"]
    assert len(await chunks(source, table)) == _DAYS
    counted = await source.session().query(sql.SQL("SELECT count(*) AS n FROM {}").format(
        table.identifier,
    ).as_string())
    assert counted == [{"n": _DAYS * 24}]


async def test_moving_chunks_places_them_in_another_tablespace(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    name = f"maintain_{uuid.uuid4().hex[:8]}"
    # CREATE TABLESPACE refuses a transaction block, and its directory must exist on the server.
    async with await psycopg.AsyncConnection.connect(
        **_connect(source), autocommit=True,
    ) as connection:
        await connection.execute(sql.SQL("COPY (SELECT 1) TO PROGRAM {}").format(
            sql.Literal(f"mkdir -p /tmp/{name}"),
        ))
        await connection.execute(sql.SQL("CREATE TABLESPACE {} LOCATION {}").format(
            sql.Identifier(name), sql.Literal(f"/tmp/{name}"),
        ))
        try:
            params = {**window(None, 3), "tablespace": name}
            assert await run(source, table, "timescale_move_chunks", params) == ["completed", "completed"]
            placed = await source.session().query(
                "SELECT chunk_tablespace::text AS place FROM timescaledb_information.chunks "
                "WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY range_start",
                (table.schema, table.table),
            )
            assert [row["place"] for row in placed[:3]] == [name, name, None]
            assert "already in" in await refusal(source, table, "timescale_move_chunks", params)
            assert 'Tablespace "nowhere" does not exist' in await refusal(
                source, table, "timescale_move_chunks", {**params, "tablespace": "nowhere"},
            )
        finally:
            await connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(table.schema)))
            await connection.execute(sql.SQL("DROP TABLESPACE {}").format(sql.Identifier(name)))
            await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(table.schema)))


def _connect(source: TimescaleSource) -> dict[str, Any]:
    options = source.options()
    return {
        "host": options.host, "port": options.port, "dbname": options.database,
        "user": options.user, "password": options.password.get_secret_value(),
    }


async def _chunk_schema(source: TimescaleSource, table: PolicyTable) -> str:
    rows = await source.session().query(
        "SELECT DISTINCT chunk_schema::text AS name FROM timescaledb_information.chunks "
        "WHERE hypertable_schema = %s AND hypertable_name = %s",
        (table.schema, table.table),
    )
    (row,) = rows
    return str(row["name"])


async def test_the_forms_offer_what_the_hypertable_has(source: TimescaleSource, table: PolicyTable) -> None:
    move = action(source, "timescale_move_chunks")
    assert isinstance(move, OffersFieldHints)
    hints = await move.field_hints(table.node_id)
    # A hypertable over time keeps its instants, and the calendar beside them.
    assert hints.integers == {}
    choices = hints.choices
    assert "pg_default" in [choice.value for choice in choices["tablespace"]]
    indexes = [choice.value for choice in choices["index"]]
    # The default stands first, then every index of the hypertable.
    assert indexes[0] == "" and "readings_device" in indexes
    reordering = action(source, "timescale_reorder_chunks")
    assert isinstance(reordering, OffersFieldHints)
    reorder = (await reordering.field_hints(table.node_id)).choices
    assert "readings_device" in [choice.value for choice in reorder["index"]]


_INTEGER_CHUNKS = """
    SELECT chunk_name, range_start_integer AS range_start, range_end_integer AS range_end
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY range_start_integer
"""


async def _made(source: TimescaleSource, prefix: str, statements: tuple[str, ...]) -> PolicyTable:
    target = PolicyTable(f"{prefix}_{uuid.uuid4().hex[:12]}", "readings")
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    for statement in statements:
        await session.schema_change(sql.SQL(statement).format(
            target.identifier, literal=sql.Literal(target.identifier.as_string()),
        ).as_string())
    return target


async def _dropped(source: TimescaleSource, target: PolicyTable) -> None:
    await source.session().schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(
        sql.Identifier(target.schema),
    ).as_string())


@pytest.fixture
async def ticks(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    """Six chunks of a hundred ticks each, cut along a bigint column."""
    target = await _made(source, "ticks", (
        "CREATE TABLE {} (tick bigint NOT NULL, value integer)",
        "SELECT create_hypertable({literal}::regclass, by_range('tick', 100))",
        "INSERT INTO {} SELECT g, g FROM generate_series(0, 599) AS g",
    ))
    try:
        yield target
    finally:
        await _dropped(source, target)


@pytest.fixture
async def hashed(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    """Three days, each in two hash partitions by device."""
    target = await _made(source, "hashed", (
        "CREATE TABLE {} (observed_at timestamptz NOT NULL, device integer NOT NULL, value integer)",
        "SELECT create_hypertable({literal}::regclass, by_range('observed_at', interval '1 day'))",
        "SELECT add_dimension({literal}::regclass, by_hash('device', 2))",
        "INSERT INTO {} SELECT TIMESTAMPTZ '2020-01-01 00:00+00' + make_interval(hours => g), g % 4, g "
        "FROM generate_series(0, 71) AS g",
    ))
    try:
        yield target
    finally:
        await _dropped(source, target)


async def integer_chunks(source: TimescaleSource, target: PolicyTable) -> list[tuple[int, int]]:
    rows = await source.session().query(_INTEGER_CHUNKS, (target.schema, target.table))
    return [(row["range_start"], row["range_end"]) for row in rows]


async def test_an_integer_hypertable_is_maintained_by_its_values(source: TimescaleSource, ticks: PolicyTable) -> None:
    drop = action(source, "timescale_drop_chunks")
    hints = await drop.field_hints(ticks.node_id)
    # The form takes numbers there, and says what they are, instead of a calendar.
    assert set(hints.integers) == {"ends_by", "starts_from"}
    assert '"tick", the bigint column' in hints.integers["ends_by"]

    assert 'integer column "tick"; give its values' in await refusal(
        source, ticks, "timescale_drop_chunks", {"ends_by": "2020-01-03T00:00:00Z"},
    )
    preview = await drop.preview(ticks.node_id, {"ends_by": "200"})
    assert preview.summary.startswith("Drop 2 chunks")
    assert "Whole chunks from the earliest chunk to 200" in preview.items
    assert await run(source, ticks, "timescale_drop_chunks", {"ends_by": "200"}) == ["completed", "completed"]
    assert (await integer_chunks(source, ticks))[0] == (200, 300)

    if source.at_least("2.18.0"):
        params = {"starts_from": "200", "ends_by": "400"}
        assert await run(source, ticks, "timescale_merge_chunks", params) == ["completed"]
        assert (await integer_chunks(source, ticks))[0] == (200, 400)
    if source.at_least("2.20.0"):
        assert await run(source, ticks, "timescale_split_chunk", {"at": "450"}) == ["completed"]
        assert (400, 450) in await integer_chunks(source, ticks)


async def test_an_integer_chunk_is_detached_and_attached_by_its_values(
    source: TimescaleSource, ticks: PolicyTable,
) -> None:
    if not source.at_least("2.21.0"):
        pytest.skip("detach_chunk and attach_chunk arrived in 2.21")
    (first, *_) = await source.session().query(_INTEGER_CHUNKS, (ticks.schema, ticks.table))
    schema = await _chunk_schema(source, ticks)
    assert await run(source, ticks, "timescale_detach_chunks", {"ends_by": "100"}) == ["completed"]
    params = {"table_schema": schema, "table_name": first["chunk_name"], "starts_from": "0", "ends_by": "100"}
    assert await run(source, ticks, "timescale_attach_chunk", params) == ["completed"]
    assert (await integer_chunks(source, ticks))[0] == (0, 100)
    counted = await source.session().query(sql.SQL("SELECT count(*) AS n FROM {}").format(
        ticks.identifier,
    ).as_string())
    assert counted == [{"n": 600}]


async def test_a_hash_partitioned_hypertable_is_maintained_chunk_by_chunk(
    source: TimescaleSource, hashed: PolicyTable,
) -> None:
    # One day is two chunks, one per partition; both are dropped, each by name.
    assert await run(source, hashed, "timescale_drop_chunks", window(None, 2)) == ["completed", "completed"]
    assert len(await chunks(source, hashed)) == 4
    assert await run(source, hashed, "timescale_reorder_chunks", {
        **window(None, 3), "index": (await action(source, "timescale_reorder_chunks").field_hints(
            hashed.node_id,
        )).choices["index"][0].value,
    }) == ["completed", "completed"]

    # Which partition a chunk is in is not public: neither a merge nor an attach could be checked.
    assert 'partitioned by hash on "device" are not merged' in await refusal(
        source, hashed, "timescale_merge_chunks", window(None, 4),
    )
    assert 'partitioned by hash on "device" are not attached' in await refusal(
        source, hashed, "timescale_attach_chunk",
        {"table_schema": hashed.schema, "table_name": "x", "starts_from": "2020-01-01T00:00:00Z",
         "ends_by": "2020-01-02T00:00:00Z"},
    )
    # TimescaleDB refuses this one itself, "cannot split chunk in multi-dimensional hypertable".
    assert "splits no chunk of a hypertable partitioned by hash" in await refusal(
        source, hashed, "timescale_split_chunk", {"at": "2020-01-02T06:00:00Z"},
    )

