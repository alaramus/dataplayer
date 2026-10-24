"""Following a foreign key of one row, in either direction (D110).

The same answer PostgreSQL gives: the source reads the key now, pairs the
columns itself and hands back a place and filters in the closed vocabulary.
A key may point into another database on the server, so the target's
database is read from the catalog rather than assumed to be this one's.
"""

from dataclasses import dataclass

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import ScalarFilter
from app.adapters.mysql import ids
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.fetch import shape_of
from app.adapters.mysql.relation import MysqlRelation, relation_parts
from app.adapters.mysql.session import MysqlSession
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
SELECT CONSTRAINT_NAME AS name,
       TABLE_SCHEMA AS source_schema,
       TABLE_NAME AS source_table,
       COLUMN_NAME AS source_column,
       REFERENCED_COLUMN_NAME AS column_name
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s
ORDER BY TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION
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
        # A constraint's name is unique within its database, not across the
        # server, so the handle names where the key comes from as well.
        return f"{self.name}@{self.source_node_id}"


class MysqlReferences:
    def __init__(
        self, session: MysqlSession, catalog: MysqlCatalog, relation: MysqlRelation
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

    async def _arriving(self, node_id: str) -> list[_Arriving]:
        schema, table = relation_parts(node_id)
        grouped: dict[tuple[str, str, str], _Arriving] = {}
        for row in await self._session.query(_ARRIVING, (schema, table)):
            source = ids.relation_id(str(row["source_schema"]), str(row["source_table"]))
            place = (str(row["name"]), str(row["source_schema"]), str(row["source_table"]))
            if place not in grouped:
                if len(grouped) >= MAX_ARRIVING:
                    break
                grouped[place] = _Arriving(
                    name=place[0],
                    columns=[],
                    source_node_id=source,
                    source_title=f"{place[1]}.{place[2]}",
                    source_columns=[],
                )
            grouped[place].columns.append(str(row["column_name"]))
            grouped[place].source_columns.append(str(row["source_column"]))
        return list(grouped.values())

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        await self._target(node_id)
        return [
            ArrivingReference(
                name=found.handle,
                columns=found.columns,
                source_title=found.source_title,
            )
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
        if key is None or key.target_table is None:
            raise ValueError(say('Relation has no reference "{name}"', name=request.reference))
        return await self._rows(
            request,
            node_id=ids.relation_id(key.target_schema or facts.schema, key.target_table),
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
            filters.append(ScalarFilter(column=there, op="eq", value=present[here]))
        return ReferencedRows(node=target, filters=list(filters))

    async def _target(self, node_id: str) -> CatalogNode:
        node = (await self._catalog.path_to(node_id))[-1]
        if node.kind not in ("table", "view"):
            raise NodeNotFound(node_id)
        return node
