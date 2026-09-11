"""Reviewed interval action with live source planning at execution boundaries."""

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
)
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_execution import execute_chunk_interval
from app.adapters.postgres.timescale.interval_preview import preview_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.core.access import Access


class ChunkIntervalParams(TimeDuration):
    unit: Literal["second", "minute", "hour", "day", "week"]


class SetChunkInterval(Action[ChunkIntervalParams]):
    name: ClassVar[str] = "timescale_set_chunk_interval"
    title: ClassVar[str] = "Change chunk interval"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    params_model = ChunkIntervalParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        interval = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await preview_chunk_interval(self._session, schema.name, node.name, interval)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the interval plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        interval = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        await execute_chunk_interval(self._session, schema.name, node.name, interval, fingerprint)
        return ActionResult(
            message="Future chunk interval changed; existing chunks were not repartitioned",
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )
