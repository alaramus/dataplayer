"""Tables declared over a connection, kept in its row (D170).

The source knows nothing of them. They are read out of the connector when an
adapter is built and handed to the driver, which shows each beside the folder
it reads; changing one is changing the row.
"""

import logging

from pydantic import TypeAdapter, ValidationError

from app.adapters.declared_tables import DeclaredTable
from app.connectors.models import Connector

logger = logging.getLogger(__name__)

_TABLES = TypeAdapter(list[DeclaredTable])


def tables_of(connector: Connector) -> tuple[DeclaredTable, ...]:
    """What the row holds; a row that no longer reads as declarations holds none."""
    try:
        return tuple(_TABLES.validate_python(connector.declared_tables or []))
    except ValidationError:
        logger.warning("Declared tables of connector %s do not read", connector.id)
        return ()


def keep(connector: Connector, tables: list[DeclaredTable]) -> None:
    connector.declared_tables = _TABLES.dump_python(tables, mode="json")


def with_table(
    tables: tuple[DeclaredTable, ...], table: DeclaredTable
) -> list[DeclaredTable]:
    """The declarations with this one in place of any over the same node."""
    if any(one.place_id == table.place_id for one in tables):
        return [table if one.place_id == table.place_id else one for one in tables]
    return [*tables, table]


def without_table(
    tables: tuple[DeclaredTable, ...], place_id: str
) -> list[DeclaredTable]:
    return [one for one in tables if one.place_id != place_id]
