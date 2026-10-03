"""Services as the search finds them, and what this server can start (D119).

A service has no name of its own: it is found by its connection's name as it
is now (D199), and by its template's title. The owner's only, as every service
route answers.

Handed to the search at assembly: the engine sits below services and imports
no feature (D197).
"""

from collections.abc import Sequence

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
    best_of,
    name_match,
    ordered,
    recalled,
    text_match,
    uuids_of,
)
from app.search.source_types import Startable
from app.services import crud, templates
from app.services.models import ManagedService

# Far above what one person may run; a bound so that the query is bounded too.
MAX_SERVICES = 1000


def startable() -> list[Startable]:
    return [
        Startable(
            adapter_type=template.adapter_type,
            title=template.title,
            description=template.description,
        )
        for template in templates.all_templates()
    ]


class ServiceNames:
    place = ObjectsPlace(provider="services")
    title = "Services"
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"service"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        for service, name in await crud.named_for_owner(
            asked.session, asked.user.id, limit=MAX_SERVICES
        ):
            match = best_of(
                name_match(asked.words, name),
                text_match(asked.words, "details", _kind_of(service)),
            )
            if match is not None:
                hits.append(_hit(service, name, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        wanted = uuids_of(ids)
        if not wanted:
            return []
        return [
            _hit(service, name, recalled(name))
            for service, name in await crud.named_for_owner(
                asked.session, asked.user.id, limit=MAX_SERVICES, ids=wanted
            )
        ]


def _kind_of(service: ManagedService) -> str:
    try:
        return templates.template_for(service.template_key).title
    except templates.UnknownServiceTemplate:
        return service.template_key


def _hit(service: ManagedService, name: str, match: Match) -> Hit:
    target = ObjectTarget(object_type="service", object_id=str(service.id))
    return Hit(
        key=target_key(target),
        target=target,
        title=name,
        detail=f"Service · {_kind_of(service)}",
        facts=Facts(kind=service.template_key, changed_at=service.updated_at),
        match=match,
        open="service",
    )
