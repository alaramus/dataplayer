"""Connection vocabulary and live admission for Timescale management."""

from typing import Any

from app.adapters.actions import Action, ActionOffers, ActionUnavailability
from app.adapters.catalog import CatalogNode, SchemaNode, TableNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.postgres.timescale.interval_preview import preview_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import discover
from app.adapters.protocol import AdapterError

TIMESCALE_ACTION_TYPES = (SetChunkInterval,)


class TimescaleActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self.interval = SetChunkInterval(session, catalog)

    async def all_actions(self) -> list[Action[Any]]:
        profile = await discover(self._session)
        if profile.feature.state == "absent":
            return []
        if profile.feature.state == "unavailable":
            raise AdapterError("unknown", "TimescaleDB action vocabulary could not be inspected")
        return [self.interval]

    async def offers(self, path: list[CatalogNode]) -> ActionOffers:
        if len(path) != 2:
            return ActionOffers([])
        schema, node = path
        if not (
            isinstance(schema, SchemaNode) and not schema.is_system
            and isinstance(node, TableNode) and not node.is_system
            and node.specialization is not None
        ):
            return ActionOffers([])
        # One day admits date and timestamp dimensions without choosing the user's interval.
        preview = await preview_chunk_interval(
            self._session, schema.name, node.name, TimeDuration(amount=1, unit="day"),
        )
        if preview.blocked:
            return ActionOffers([], (ActionUnavailability(
                name=self.interval.name, reason=preview.summary,
            ),))
        return ActionOffers([self.interval])
