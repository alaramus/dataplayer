"""Dashboards, as the search finds them: by name, the person's own and those
shared with them (D129, D199).

Handed to the search at assembly: the engine sits below metrics and imports no
feature (D197). A dashboard shared with the person names its owner.
"""

from collections.abc import Sequence

from app.core.access import Access
from app.core.translation import N_, say
from app.metrics import crud
from app.metrics.dashboards import Dashboard, owner_named
from app.search.models import (
    Facts,
    Hit,
    Match,
    ObjectsPlace,
    ObjectTarget,
    ObjectType,
    target_key,
)
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    name_match,
    ordered,
    recalled,
    uuids_of,
)
from app.users.models import User

# Far above what one person holds or is shown; a bound so that the query is
# bounded too.
MAX_DASHBOARDS = 1000


class DashboardNames:
    place = ObjectsPlace(provider="dashboards")
    title = N_("Dashboards")
    # One shared with the person is somebody else's (D199).
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"dashboard"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        seen = await crud.dashboards_seen_by(
            asked.session, asked.user.id, limit=MAX_DASHBOARDS
        )
        for dashboard, held, owner in seen:
            match = name_match(asked.words, dashboard.name)
            if match is not None:
                hits.append(_hit(dashboard, held, owner, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        seen = await crud.dashboards_seen_by(
            asked.session, asked.user.id, limit=MAX_DASHBOARDS, ids=uuids_of(ids)
        )
        return [
            _hit(dashboard, held, owner, recalled(dashboard.name))
            for dashboard, held, owner in seen
        ]


def _hit(dashboard: Dashboard, held: Access, owner: User | None, match: Match) -> Hit:
    target = ObjectTarget(object_type="dashboard", object_id=str(dashboard.id))
    shared_by = None if owner is None else owner_named(owner)
    return Hit(
        key=target_key(target),
        target=target,
        title=dashboard.name,
        detail=(
            say("Dashboard")
            if shared_by is None
            else say("Dashboard · shared by {owner}", owner=shared_by)
        ),
        facts=Facts(kind="dashboard", changed_at=dashboard.updated_at, owner=shared_by),
        match=match,
        access=held,
        open="dashboard",
    )
