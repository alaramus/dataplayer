"""Following a foreign key of one row, in either direction (D110).

The same answer PostgreSQL gives: the source reads the key now, pairs the
columns itself and hands back a place and filters in the closed vocabulary.
The keys that point at a table are found by asking every table of the file
for its own, since SQLite keeps no list of them the other way round.
"""

from dataclasses import dataclass

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import ScalarFilter
from app.adapters.protocol import NodeNotFound
from app.adapters.references import (
    ArrivingReference,
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceTarget,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.fetch import shape_of
from app.adapters.sqlite.inspection import SCHEMA, read_relation
from app.adapters.sqlite.relation import SqliteRelation, relation_name
from app.adapters.sqlite.session import Reading, SqliteSession
from app.core.translation import say

# How many arriving keys are offered at once (D110).
MAX_ARRIVING = 50

# Every key of every table that names this one, in the order each declares
# them. The target is compared without case, as SQLite compares names.
_ARRIVING = """
SELECT m.name AS source_table, k.id AS id
FROM sqlite_schema AS m, pragma_foreign_key_list(m.name, 'main') AS k
WHERE m.type = 'table' AND k."table" = ? COLLATE NOCASE
GROUP BY m.name, k.id
ORDER BY m.name, k.id
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


def _arriving(reading: Reading, table: str) -> list[_Arriving]:
    found: list[_Arriving] = []
    for row in reading.rows(_ARRIVING, (table,)):
        if len(found) >= MAX_ARRIVING:
            break
        source = str(row["source_table"])
        facts = read_relation(reading, source, structure=False)
        if facts is None:
            continue
        for key in facts.foreign_keys:
            if (key.target_table or "").lower() != table.lower():
                continue
            arriving = _Arriving(
                name=key.name,
                columns=key.target_columns,
                source_node_id=ids.relation_id(source),
                source_title=f"{SCHEMA}.{source}",
                source_columns=key.columns,
            )
            if arriving not in found:
                found.append(arriving)
    return found[:MAX_ARRIVING]


class SqliteReferences:
    def __init__(
        self, session: SqliteSession, catalog: SqliteCatalog, relation: SqliteRelation
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

    async def _arriving(self, node_id: str) -> list[_Arriving]:
        table = relation_name(node_id)
        return await self._session.inspection(lambda reading: _arriving(reading, table))

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
        if key is None or key.target_table is None:
            raise ValueError(say('Relation has no reference "{name}"', name=request.reference))
        return await self._rows(
            request,
            node_id=ids.relation_id(key.target_table),
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
        # SQLite matches a key's target case-insensitively; the column's own
        # spelling is the one a filter names.
        columns = {column.name.lower(): column for column in shape_of(facts).columns}
        filters: list[ScalarFilter] = []
        for here, there in pairs:
            column = columns.get(there.lower())
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
