"""Read collaborators for source inspection on one transaction snapshot."""

from collections.abc import Mapping
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from app.adapters.protocol import AdapterError
from app.core.translation import say


class PostgresReader(Protocol):
    async def query(
        self, sql: str, params: tuple[object, ...] | None = None, *,
        refusals: Mapping[str, str] | None = None, inspection: bool = False,
    ) -> list[dict[str, Any]]: ...


class InspectionReader:
    def __init__(self, connection: psycopg.AsyncConnection[Any]) -> None:
        self._connection = connection

    async def query(
        self, sql: str, params: tuple[object, ...] | None = None, *,
        refusals: Mapping[str, str] | None = None, inspection: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            cursor = await self._connection.cursor(row_factory=dict_row).execute(sql, params)
            return await cursor.fetchall()
        except psycopg.Error as exc:
            if refusals is not None and (message := refusals.get(exc.sqlstate or "")):
                raise ValueError(say(message)) from None
            raise AdapterError("unknown", say("Source metadata could not be inspected")) from None
