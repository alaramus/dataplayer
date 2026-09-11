"""Connection vocabulary and live admission for Timescale management."""

from typing import Any

from app.adapters.actions import Action, ActionOffers, ActionUnavailability
from app.adapters.catalog import CatalogNode, SchemaNode, TableNode, ViewNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveAgePolicy,
    RemoveCompressionPolicy,
    RemoveRetentionPolicy,
    SetAgePolicy,
    SetCompressionPolicy,
    SetRetentionPolicy,
    age_policy_admission,
)
from app.adapters.postgres.timescale.compression_settings_action import (
    ConfigureCompression,
    compression_settings_admission,
)
from app.adapters.postgres.timescale.conversion_action import (
    ConvertToHypertable,
    conversion_admission,
)
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.postgres.timescale.interval_preview import preview_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import discover
from app.adapters.postgres.timescale.refresh_action import (
    RemoveRefreshPolicy,
    SetRefreshPolicy,
    refresh_admission,
)
from app.adapters.protocol import AdapterError
from app.adapters.specializations import (
    TimescaleContinuousAggregate,
    TimescaleHypertable,
)

TIMESCALE_ACTION_TYPES = (
    SetChunkInterval, ConfigureCompression, SetRetentionPolicy, RemoveRetentionPolicy,
    SetCompressionPolicy, RemoveCompressionPolicy, SetRefreshPolicy, RemoveRefreshPolicy,
    ConvertToHypertable,
)


class TimescaleActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog
        self.interval = SetChunkInterval(session, catalog)
        self.compression_settings = ConfigureCompression(session, catalog)
        self._policies: tuple[tuple[SetAgePolicy[Any], RemoveAgePolicy], ...] = (
            (SetRetentionPolicy(session, catalog), RemoveRetentionPolicy(session, catalog)),
            (SetCompressionPolicy(session, catalog), RemoveCompressionPolicy(session, catalog)),
        )
        self.set_refresh = SetRefreshPolicy(session, catalog)
        self.remove_refresh = RemoveRefreshPolicy(session, catalog)
        self.convert = ConvertToHypertable(session, catalog)
        self.registered: tuple[Action[Any], ...] = (
            self.interval, self.compression_settings,
            *(action for pair in self._policies for action in pair),
            self.set_refresh, self.remove_refresh, self.convert,
        )

    async def all_actions(self) -> list[Action[Any]]:
        profile = await discover(self._session)
        if profile.feature.state == "absent":
            return []
        if profile.feature.state == "unavailable":
            raise AdapterError("unknown", "TimescaleDB action vocabulary could not be inspected")
        return list(self.registered)

    async def offers(self, path: list[CatalogNode]) -> ActionOffers:
        hypertable = _user_relation(path, TableNode, TimescaleHypertable)
        aggregate = _user_relation(path, ViewNode, TimescaleContinuousAggregate)
        ordinary = _user_relation(path, TableNode, None)
        if hypertable is not None:
            reasons = await self._hypertable_reasons(*hypertable)
        elif aggregate is not None:
            setting, removing = await refresh_admission(self._session, *aggregate)
            reasons = {self.set_refresh.name: setting, self.remove_refresh.name: removing}
        elif ordinary is not None:
            reasons = await self._conversion_reasons(*ordinary)
        else:
            return ActionOffers([])
        return ActionOffers(
            [action for action in self.registered if action.name in reasons and reasons[action.name] is None],
            tuple(
                ActionUnavailability(name=name, reason=reason)
                for name, reason in reasons.items() if reason is not None
            ),
        )

    async def _hypertable_reasons(self, schema: str, table: str) -> dict[str, str | None]:
        # One day admits date and timestamp dimensions without choosing the user's interval.
        interval = await preview_chunk_interval(
            self._session, schema, table, TimeDuration(amount=1, unit="day"),
        )
        reasons: dict[str, str | None] = {
            self.interval.name: interval.summary if interval.blocked else None,
            self.compression_settings.name: await compression_settings_admission(self._session, schema, table),
        }
        for setter, remover in self._policies:
            reasons[setter.name], reasons[remover.name] = await age_policy_admission(
                self._session, setter.spec, schema, table,
            )
        return reasons

    async def _conversion_reasons(self, schema: str, table: str) -> dict[str, str | None]:
        # Plain PostgreSQL answers after one catalog read, and has no such command to explain.
        if (await discover(self._session)).feature.state in {"absent", "unavailable"}:
            return {}
        reason = await self._catalog.relation_action_reason(schema, table)
        if reason is None:
            reason = await conversion_admission(self._session, schema, table)
        return {self.convert.name: reason}


def _user_relation(
    path: list[CatalogNode], node_type: type[TableNode] | type[ViewNode], specialization: type[object] | None,
) -> tuple[str, str] | None:
    """A user relation of this kind; a None specialization asks for an ordinary one."""
    if len(path) != 2:
        return None
    schema, node = path
    if not (
        isinstance(schema, SchemaNode) and not schema.is_system
        and isinstance(node, node_type) and not node.is_system
    ):
        return None
    if specialization is None:
        return (schema.name, node.name) if node.specialization is None else None
    return (schema.name, node.name) if isinstance(node.specialization, specialization) else None
