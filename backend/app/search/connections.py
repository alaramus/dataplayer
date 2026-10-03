"""The person's connections: resolved once per answer, and found as rows (D199).

Connections are filtered by the one visibility predicate inside the query that
lists them — owner or grant — so a connection the person has no standing on is
never asked, never counted and never named. A superuser is nobody special here
(D34).
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.registry import UnknownAdapterType
from app.adapters.registry import get as adapter_type_of
from app.connectors import crud
from app.search.models import ConnectionsPlace, ConnectionTarget, Facts, Hit, target_key
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    VisibleConnection,
    best_of,
    name_match,
    ordered,
    text_match,
)
from app.users.models import User

# How many connections one answer resolves. Far above what one person holds;
# a bound so that the query that answers "who may see what" is bounded too.
MAX_VISIBLE = 1000

# The non-secret options a connection row is also found by.
_DETAIL_OPTIONS = ("host", "database")


async def visible(session: AsyncSession, user: User) -> list[VisibleConnection]:
    """Every connection the person may see, with their standing, in one query."""
    rows = await crud.visible_with_standing(session, user=user, limit=MAX_VISIBLE)
    return [
        VisibleConnection(
            id=connector.id,
            name=connector.name,
            adapter_type=connector.adapter_type,
            enabled=connector.enabled,
            access=access,
            owner_id=connector.owner_id,
            owner_email=owner_email,
            config=dict(connector.config or {}),
            secrets=connector.secrets,
        )
        for connector, access, owner_email in rows
    ]


def type_title(adapter_type: str) -> str:
    try:
        return adapter_type_of(adapter_type).title
    except UnknownAdapterType:
        return adapter_type


def _details(connection: VisibleConnection) -> list[str]:
    found: list[str] = []
    for option in _DETAIL_OPTIONS:
        value = connection.config.get(option)
        if isinstance(value, str | int) and not isinstance(value, bool) and str(value):
            found.append(str(value))
    return found


class ConnectionRows:
    """Connections found by their name, their source type, their host and database."""

    place = ConnectionsPlace()
    title = "Connections"

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        for connection in asked.visible:
            kind = type_title(connection.adapter_type)
            details = " · ".join([kind, *_details(connection)])
            match = best_of(
                name_match(asked.words, connection.name),
                text_match(asked.words, "details", details),
            ) or text_match(asked.words, "details", f"{connection.name} · {details}")
            if match is None:
                continue
            target = ConnectionTarget(connector_id=connection.id)
            hits.append(
                Hit(
                    key=target_key(target),
                    target=target,
                    title=connection.name,
                    detail=" · ".join(
                        part
                        for part in (
                            kind,
                            None if connection.enabled else "Switched off",
                            connection.owner_email,
                        )
                        if part
                    ),
                    facts=Facts(
                        kind=connection.adapter_type,
                        owner=connection.owner_email,
                        switched_off=not connection.enabled,
                    ),
                    match=match,
                    access=connection.access,
                    # A switched-off connection is not a source: it opens on
                    # its window, where it can be switched back on (D20).
                    open="catalog" if connection.enabled else "connection",
                )
            )
        return ordered(hits, asked.limit)
