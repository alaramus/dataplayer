"""Following a foreign key of one row, in either direction (D110, D395).

The same answer PostgreSQL gives: the source reads the key now, pairs the
columns itself and hands back a place and filters in the closed vocabulary.
The keys arriving at a table are those `duckdb_constraints()` lists as naming
it, within its own schema, since DuckDB refuses a key into another (D389).
"""

from dataclasses import dataclass

from app.adapters import database_ids as ids
from app.adapters.catalog import CatalogNode
from app.adapters.duckdb.catalog import DuckdbCatalog
from app.adapters.duckdb.fetch import shape_of
from app.adapters.duckdb.relation import DuckdbRelation, relation_of
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.fetch import ScalarFilter
from app.adapters.protocol import NodeNotFound
from app.adapters.references import (
    ArrivingReference,
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceTarget,
)
from app.core.translation import say

# How many arriving keys are offered at once (D110).
MAX_ARRIVING = 50

_ARRIVING = """
SELECT table_name, constraint_name, constraint_column_names, referenced_column_names
FROM duckdb_constraints()
WHERE database_name = current_database() AND schema_name = ?
  AND constraint_type = 'FOREIGN KEY' AND referenced_table = ?
ORDER BY table_name, constraint_index
LIMIT ?
"""


@dataclass(frozen=True)
class _Arriving:
    name: str
    columns: list[str]
    source_node_id: str
    source_title: str
    source_columns: list[str]

    @property
    def handle(self) -> str:
        # A key's name is the source table's own, so the handle says whose.
        return f"{self.name}@{self.source_node_id}"


def _arriving(reading: Reading, schema: str, table: str) -> list[_Arriving]:
    return [
        _Arriving(
            name=str(row["constraint_name"]),
            columns=[str(name) for name in row["referenced_column_names"]],
            source_node_id=ids.relation_id(schema, str(row["table_name"])),
            source_title=f"{schema}.{row['table_name']}",
            source_columns=[str(name) for name in row["constraint_column_names"]],
        )
        for row in reading.rows(_ARRIVING, [schema, table, MAX_ARRIVING])
    ]


class DuckdbReferences:
    def __init__(
        self, session: DuckdbSession, catalog: DuckdbCatalog, relation: DuckdbRelation
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

    async def _arriving(self, node_id: str) -> list[_Arriving]:
        schema, table = relation_of(node_id)
        return await self._session.inspection(lambda reading: _arriving(reading, schema, table))

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        await self._target(node_id)
        return [
            ArrivingReference(name=found.handle, columns=found.columns, source_title=found.source_title)
            for found in await self._arriving(node_id)
        ]

    async def follow_reference(self, request: FollowReferenceRequest) -> ReferenceTarget:
        if request.direction == "incoming":
            arriving = next(
                (
                    found
                    for found in await self._arriving(request.node_id)
                    if found.handle == request.reference
                ),
                None,
            )
            if arriving is None:
                raise ValueError(
                    say('Nothing named "{name}" points at this relation', name=request.reference)
                )
            return await self._rows(
                request,
                node_id=arriving.source_node_id,
                pairs=list(zip(arriving.columns, arriving.source_columns, strict=True)),
            )
        facts = await self._relation.facts(request.node_id, structure=False)
        key = next((key for key in facts.foreign_keys if key.name == request.reference), None)
        if key is None or key.target_table is None or not key.target_columns:
            raise ValueError(say('Relation has no reference "{name}"', name=request.reference))
        return await self._rows(
            request,
            node_id=ids.relation_id(facts.schema, key.target_table),
            pairs=list(zip(key.columns, key.target_columns, strict=True)),
        )

    async def _rows(
        self,
        request: FollowReferenceRequest,
        *,
        node_id: str,
        pairs: list[tuple[str, str]],
    ) -> ReferenceTarget:
        held = [here for here, _ in pairs]
        supplied = {value.column: value.value for value in request.values}
        if len(supplied) != len(request.values):
            raise ValueError(say("A reference column may be supplied only once"))
        if set(supplied) != set(held):
            raise ValueError(
                say(
                    'Reference "{reference}" is over {columns}',
                    reference=request.reference,
                    columns=", ".join(held),
                )
            )
        present = {name: value for name, value in supplied.items() if value is not None}
        if len(present) != len(supplied):
            return NoReferencedRows(reason=say("This row has no value for that reference"))

        target = await self._target(node_id)
        facts = await self._relation.facts(target.id, structure=False)
        columns = {column.name: column for column in shape_of(facts).columns}
        filters: list[ScalarFilter] = []
        for here, there in pairs:
            column = columns.get(there)
            if column is None:
                raise NodeNotFound(target.id)
            if "eq" not in column.filter_operators:
                return NoReferencedRows(
                    reason=say(
                        'This source cannot look up "{column}" values of type {type}',
                        column=column.name,
                        type=column.type.sql,
                    )
                )
            filters.append(ScalarFilter(column=column.name, op="eq", value=present[here]))
        return ReferencedRows(node=target, filters=list(filters))

    async def _target(self, node_id: str) -> CatalogNode:
        node = (await self._catalog.path_to(node_id))[-1]
        if node.kind not in ("table", "view"):
            raise NodeNotFound(node_id)
        return node
