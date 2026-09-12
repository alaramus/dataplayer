"""Chunk compression and decompression through the registered actions (D123).

The owned job around the units needs the application's database, which this
harness never touches, so these scenarios call the action methods the job
calls: review, admission, one unit per chunk and reading back.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused, Previews
from app.adapters.operations import OperationPlan, OperationTarget, ProducesJob
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.timescale.chunk_storage_plan import plan_chunk_storage
from app.adapters.postgres.timescale.plans import ChunkWindow
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    registry,
    reviewed,
    rows,
)
from compatibility.timescale.source import TimescaleSource

EVERYTHING: dict[str, object] = {"ends_by": "2026-02-01T00:00:00Z", "starts_from": None}
COMPRESS = "timescale_compress_chunks"
DECOMPRESS = "timescale_decompress_chunks"

_CHUNKS = """
SELECT chunk_schema, chunk_name, is_compressed, range_start, range_end
FROM timescaledb_information.chunks
WHERE hypertable_schema = %s AND hypertable_name = %s
ORDER BY range_start
"""


def chunk_action(source: TimescaleSource, name: str) -> Any:
    found = registry(source).action(name)
    assert isinstance(found, ProducesJob) and isinstance(found, Previews)
    return found


async def stored(source: TimescaleSource, target: PolicyTable) -> list[dict[str, Any]]:
    return await source.session().query(_CHUNKS, (target.schema, target.table))


async def admitted(action: Any, target: PolicyTable, params: dict[str, object]) -> OperationPlan:
    plan: OperationPlan = await action.plan_job(
        target.node_id, params, await reviewed(action, target.node_id, params),
    )
    return plan


def identity(chunk: dict[str, Any]) -> sql.Identifier:
    return sql.Identifier(chunk["chunk_schema"], chunk["chunk_name"])


async def native_compress(source: TimescaleSource, chunk: dict[str, Any]) -> None:
    await source.session().query(
        "SELECT public.compress_chunk(%s::regclass)::text AS chunk", (identity(chunk).as_string(),),
    )


@asynccontextmanager
async def locked(source: TimescaleSource, chunk: dict[str, Any]) -> AsyncIterator[None]:
    """Another session holding one chunk exclusively until the block ends."""
    async with source.session().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(identity(chunk)),
            )
            yield


async def test_compressing_and_decompressing_convert_every_chunk_and_keep_the_rows(
    source: TimescaleSource,
) -> None:
    async with disposable_hypertable(source, "chunk_storage", compressed=True) as target:
        before = await rows(source, target)
        chunks = await stored(source, target)
        assert [chunk["is_compressed"] for chunk in chunks] == [False, False]

        compress = chunk_action(source, COMPRESS)
        plan = await admitted(compress, target, EVERYTHING)
        assert [item.name for item in plan.targets] == [chunk["chunk_name"] for chunk in chunks]
        assert [
            await compress.run_unit(target.node_id, EVERYTHING, plan.unit_fingerprint, item)
            for item in plan.targets
        ] == ["completed", "completed"]
        assert [chunk["is_compressed"] for chunk in await stored(source, target)] == [True, True]
        assert await compress.observe(target.node_id, EVERYTHING, plan.targets) == [
            "as_requested", "as_requested",
        ]
        assert await rows(source, target) == before
        again = await compress.preview(target.node_id, EVERYTHING)
        assert again.blocked and "already compressed" in again.summary

        decompress = chunk_action(source, DECOMPRESS)
        back = await admitted(decompress, target, EVERYTHING)
        assert [
            await decompress.run_unit(target.node_id, EVERYTHING, back.unit_fingerprint, item)
            for item in back.targets
        ] == ["completed", "completed"]
        assert [chunk["is_compressed"] for chunk in await stored(source, target)] == [False, False]
        assert await rows(source, target) == before


async def test_the_window_selects_whole_chunks_only(source: TimescaleSource) -> None:
    async with disposable_hypertable(source, "chunk_window", compressed=True) as target:
        first, second = await stored(source, target)
        compress = chunk_action(source, COMPRESS)
        early = await admitted(compress, target, {"ends_by": first["range_end"].isoformat()})
        assert [item.name for item in early.targets] == [first["chunk_name"]]
        late = await admitted(compress, target, {
            "ends_by": "2026-02-01T00:00:00Z", "starts_from": second["range_start"].isoformat(),
        })
        assert [item.name for item in late.targets] == [second["chunk_name"]]
        inside = await compress.preview(
            target.node_id, {"ends_by": (first["range_end"] - timedelta(hours=1)).isoformat()},
        )
        assert inside.blocked and "No whole chunk" in inside.summary


async def test_a_chunk_changed_after_review_needs_a_new_review(source: TimescaleSource) -> None:
    async with disposable_hypertable(source, "chunk_stale", compressed=True) as target:
        compress = chunk_action(source, COMPRESS)
        fingerprint = await reviewed(compress, target.node_id, EVERYTHING)
        first, _ = await stored(source, target)
        await native_compress(source, first)
        with pytest.raises(ActionRefused, match="review it again"):
            await compress.plan_job(target.node_id, EVERYTHING, fingerprint)


async def test_each_unit_rechecks_the_chunk_it_was_given(source: TimescaleSource) -> None:
    async with (
        disposable_hypertable(source, "chunk_units", compressed=True) as target,
        disposable_hypertable(source, "chunk_other", compressed=True) as other,
    ):
        compress = chunk_action(source, COMPRESS)
        plan = await admitted(compress, target, EVERYTHING)
        first, _ = await stored(source, target)
        await native_compress(source, first)
        assert await compress.run_unit(
            target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[0],
        ) == "already"

        foreign_chunk = (await stored(source, other))[0]
        foreign = OperationTarget(schema_name=foreign_chunk["chunk_schema"], name=foreign_chunk["chunk_name"])
        with pytest.raises(ActionRefused, match="no longer part"):
            await compress.run_unit(target.node_id, EVERYTHING, plan.unit_fingerprint, foreign)
        assert [chunk["is_compressed"] for chunk in await stored(source, other)] == [False, False]

        with pytest.raises(ActionRefused, match="changed after review"):
            await compress.run_unit(target.node_id, EVERYTHING, "0" * 64, plan.targets[1])
        assert await compress.run_unit(
            target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[1],
        ) == "completed"


async def test_compression_disabled_after_admission_refuses_the_remaining_chunks(
    source: TimescaleSource,
) -> None:
    async with disposable_hypertable(source, "chunk_disabled", compressed=True) as target:
        compress = chunk_action(source, COMPRESS)
        plan = await admitted(compress, target, EVERYTHING)
        await source.session().schema_change(sql.SQL(
            "ALTER TABLE {} SET (timescaledb.compress = false)"
        ).format(target.identifier).as_string())
        with pytest.raises(ActionRefused, match="Enable compression"):
            await compress.run_unit(target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[0])
        assert [chunk["is_compressed"] for chunk in await stored(source, target)] == [False, False]


async def test_a_chunk_in_use_is_refused_within_the_lock_timeout(source: TimescaleSource) -> None:
    async with disposable_hypertable(source, "chunk_busy", compressed=True) as target:
        compress = chunk_action(source, COMPRESS)
        plan = await admitted(compress, target, EVERYTHING)
        first, _ = await stored(source, target)
        async with locked(source, first):
            async with asyncio.timeout(10):
                with pytest.raises(ActionRefused, match="in use"):
                    await compress.run_unit(
                        target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[0],
                    )
        assert (await stored(source, target))[0]["is_compressed"] is False


async def test_cancelling_a_conversion_rolls_it_back_and_releases_the_chunk(
    source: TimescaleSource,
) -> None:
    async with disposable_hypertable(source, "chunk_cancel", compressed=True) as target:
        compress = chunk_action(source, COMPRESS)
        plan = await admitted(compress, target, EVERYTHING)
        first, _ = await stored(source, target)
        async with locked(source, first):
            task = asyncio.create_task(compress.run_unit(
                target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[0],
            ))
            # Long enough to be waiting inside compress_chunk, well within its lock timeout.
            await asyncio.sleep(1)
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert (await stored(source, target))[0]["is_compressed"] is False
        async with asyncio.timeout(10):
            assert await compress.run_unit(
                target.node_id, EVERYTHING, plan.unit_fingerprint, plan.targets[0],
            ) == "completed"


async def test_the_installed_versions_routine_is_the_one_verified(source: TimescaleSource) -> None:
    async with disposable_hypertable(source, "chunk_shape", compressed=True) as target:
        first, second = await stored(source, target)
        async with source.session().inspection() as reader:
            planned = await plan_chunk_storage(
                reader, target.schema, target.table, "columnstore",
                ChunkWindow(ends_by=second["range_end"]),
            )
        assert planned.unit.strategy.extension_version == source.version
        assert planned.unit.strategy.function_schema == "public"
        assert [chunk.name for chunk in planned.chunks] == [first["chunk_name"], second["chunk_name"]]


async def test_a_plain_database_offers_no_chunk_commands(source: TimescaleSource) -> None:
    session = source.session(database="plain_fixture")
    names = {action.name for action in await PostgresActions(session, PostgresCatalog(session)).all_actions()}
    assert not {COMPRESS, DECOMPRESS} & names
