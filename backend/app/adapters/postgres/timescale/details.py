"""Read one optional public-view record within a shared time budget (D121)."""

import asyncio
from dataclasses import dataclass

from psycopg import sql

from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.protocol import AdapterError
from app.adapters.relation import RelationModel
from app.adapters.timescale_metadata import (
    ContinuousAggregateFacts,
    HypertableFacts,
    TimescaleFacts,
    UnavailableTimescaleFacts,
)
from app.core.translation import say


@dataclass(frozen=True)
class DetailsReader:
    view: str
    schema_column: str
    name_column: str
    facts_type: type[HypertableFacts] | type[ContinuousAggregateFacts]


_READERS = {
    "timescale_hypertable": DetailsReader(
        "hypertables", "hypertable_schema", "hypertable_name", HypertableFacts,
    ),
    "timescale_continuous_aggregate": DetailsReader(
        "continuous_aggregates", "view_schema", "view_name", ContinuousAggregateFacts,
    ),
}


async def inspect_details(
    session: PostgresSession, model: RelationModel
) -> TimescaleFacts | None:
    if model.specialization is None:
        return None
    reader = _READERS[model.specialization.kind]
    fields = tuple(name for name in reader.facts_type.model_fields if name != "kind")
    required = tuple(dict.fromkeys((reader.schema_column, reader.name_column, *fields)))
    try:
        async with asyncio.timeout(5):
            await require_public_view(session, reader.view, required)
            selected = sql.SQL(", ").join(
                sql.SQL("{}::text AS {}").format(sql.Identifier(name), sql.Identifier(name))
                if name == "num_chunks" else sql.Identifier(name)
                for name in fields
            )
            statement = sql.SQL(
                "SELECT {} FROM {} WHERE {} = %s AND {} = %s LIMIT 2"
            ).format(
                selected, sql.Identifier("timescaledb_information", reader.view),
                sql.Identifier(reader.schema_column), sql.Identifier(reader.name_column),
            )
            rows = await session.query(
                statement.as_string(), (model.schema_name, model.name), inspection=True,
            )
            if len(rows) != 1:
                return UnavailableTimescaleFacts(
                    reason=say("TimescaleDB metadata no longer identifies this relation uniquely"),
                )
            return reader.facts_type.model_validate(rows[0])
    except TimeoutError:
        return UnavailableTimescaleFacts(reason=say("TimescaleDB metadata inspection timed out"))
    except (AdapterError, ValueError):
        return UnavailableTimescaleFacts(
            reason=say("TimescaleDB metadata could not be inspected safely"),
        )
