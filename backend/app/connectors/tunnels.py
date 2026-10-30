"""The SSH connections a database of their owner's goes through (D282).

Handed to every source as `AdapterContext.tunnels`, the way `OwnerKeys` is
(D146), and asked only by one whose options name a tunnel. Always the owner's:
a grantee reading the database goes through the owner's SSH connection without
being able to open that connection itself (D33).
"""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as options_schema
from app.adapters import registry
from app.adapters.protocol import AdapterError
from app.adapters.registry import AdapterContext
from app.adapters.tunnels import ForwardsPorts, tunnel_of
from app.connectors import service
from app.connectors.models import Connector
from app.connectors.ssh_keys import OwnerKeys, SshKeyUse
from app.core.db import async_session_maker
from app.core.translation import say
from app.users import storage


class OwnerTunnels:
    """One person's SSH connections, opened as tunnels for their databases."""

    def __init__(self, owner_id: uuid.UUID) -> None:
        self._owner_id = owner_id

    async def endpoint(
        self, connection_id: uuid.UUID, host: str, port: int
    ) -> tuple[str, int]:
        async with async_session_maker() as session:
            connector = await session.get(Connector, connection_id)
        if connector is None or connector.owner_id != self._owner_id:
            raise AdapterError(
                "config",
                say("The SSH connection this goes through is gone; choose another"),
            )
        if not connector.enabled:
            raise AdapterError(
                "config", say("The SSH connection this goes through is switched off")
            )
        try:
            adapter_type = registry.get(connector.adapter_type)
        except registry.UnknownAdapterType:
            adapter_type = None
        # No tunnels in this context: a tunnel does not go through another.
        adapter = (
            None
            if adapter_type is None
            else service.build_adapter(
                adapter_type,
                service.merge_options(connector.config, connector.secrets),
                AdapterContext(
                    home_dir=storage.home_dir(self._owner_id),
                    keys=OwnerKeys(self._owner_id),
                ),
            )
        )
        if not isinstance(adapter, ForwardsPorts):
            raise AdapterError(
                "config", say("{name} cannot carry a tunnel", name=connector.name)
            )
        return await adapter.forward(host, port)


async def uses(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, list[SshKeyUse]]:
    """Which of the owner's connections go through which SSH connection.

    Read off the schemas and the stored options, as the uses of a key are, so
    there is no second record of it to fall out of step.
    """
    names_of = {
        adapter_type.name: options_schema.tunnel_reference_names(adapter_type.options_schema)
        for adapter_type in registry.all_types()
    }
    rows = await session.exec(select(Connector).where(Connector.owner_id == owner_id))
    found: dict[uuid.UUID, list[SshKeyUse]] = {}
    for connector in rows.all():
        for name in names_of.get(connector.adapter_type, set()):
            value = connector.config.get(name)
            try:
                tunnel = tunnel_of(str(value or ""))
            except ValueError:
                continue
            if tunnel is not None:
                found.setdefault(tunnel, []).append(
                    SshKeyUse(id=connector.id, name=connector.name)
                )
    return found
