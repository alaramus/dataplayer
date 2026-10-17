"""Following a foreign key of one row, in either direction."""

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchColumn, ScalarFilter
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.fetch import (
    ArrivingRelationReference,
    PostgresFetch,
    RelationReference,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.references import (
    ArrivingReference,
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceTarget,
)
from app.core.translation import say


class PostgresReferences:
    """Turning "this row, this key" into a place and a predicate.

    Everything the answer is made of is read from the server at the moment of
    asking: which references the relation has, which point at it, what they
    point at now, and what the far relation's columns are called and admit.
    Nothing is taken from the request but the name of the reference, the
    direction and the values, and all three are checked against that reading
    before a single filter is built.
    """

    def __init__(self, catalog: PostgresCatalog, fetch: PostgresFetch) -> None:
        self._catalog = catalog
        self._fetch = fetch

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        """The keys of other relations that land on this one (D110).

        The relation is resolved first: an id that names nothing would
        otherwise answer with an empty list, which reads as "nothing points
        here" rather than "there is no such relation".
        """
        schema, table = self._relation(node_id)
        await self._target_node(node_id)
        return [
            ArrivingReference(
                name=_handle(found),
                columns=found.columns,
                source_title=found.source_node_id,
            )
            for found in await self._fetch.arriving(schema, table)
        ]

    async def follow_reference(
        self, request: FollowReferenceRequest
    ) -> ReferenceTarget:
        schema, table = self._relation(request.node_id)
        if request.direction == "incoming":
            arriving = await self._arriving(schema, table, request.reference)
            return await self._rows_named_by(
                request,
                node_id=arriving.source_node_id,
                pairs=list(
                    zip(arriving.columns, arriving.source_columns, strict=True)
                ),
            )
        reference = await self._reference(schema, table, request.reference)
        return await self._rows_named_by(
            request,
            node_id=reference.target_node_id,
            pairs=list(zip(reference.columns, reference.target_columns, strict=True)),
        )

    async def _rows_named_by(
        self,
        request: FollowReferenceRequest,
        *,
        node_id: str,
        pairs: list[tuple[str, str]],
    ) -> ReferenceTarget:
        """Where the values in this row lead, whichever way the key runs.

        `pairs` is this relation's column beside the far relation's, in key
        order, and it is the only thing the two directions disagree about: a
        key of this relation pairs its own columns with the target's, and a key
        landing here pairs the columns it lands on with the ones it is made of.
        """
        held = [column for column, _ in pairs]
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

        # MATCH SIMPLE and MATCH FULL agree here: a key with a missing value
        # names no row at all. The source says so rather than the screen
        # deciding it, because what an absent key means belongs to the source.
        present = {
            name: value for name, value in supplied.items() if value is not None
        }
        if len(present) != len(supplied):
            return NoReferencedRows(reason=say("This row has no value for that reference"))

        target = await self._target_node(node_id)
        target_schema, _, target_table = target.id.partition(".")
        info = await self._fetch.relation_info(target_schema, target_table)
        columns = {column.name: column for column in info.columns}

        filters: list[ScalarFilter] = []
        for here, there in pairs:
            column = columns.get(there)
            if column is None:
                # PostgreSQL does not allow a constraint to outlive the column
                # it names, so the far relation has changed under this call.
                raise NodeNotFound(target.id)
            refusal = _cannot_match(column)
            if refusal is not None:
                return NoReferencedRows(reason=refusal)
            filters.append(ScalarFilter(column=there, op="eq", value=present[here]))

        return ReferencedRows(node=target, filters=list(filters))

    def _relation(self, node_id: str) -> tuple[str, str]:
        schema, _, table = node_id.partition(".")
        if not table:
            raise ValueError(say('"{node_id}" is not a relation: expected schema.table', node_id=node_id))
        return schema, table

    async def _reference(
        self, schema: str, table: str, name: str
    ) -> RelationReference:
        """The named key of this relation, read now rather than trusted.

        The same reading the fetch result was built from, so a reference the
        caller can point at is a reference the source still has, and one it
        cannot point at is refused by name rather than by predicate.
        """
        for found in await self._fetch.references(schema, table):
            if found.name == name:
                return found
        raise ValueError(say('Relation has no reference "{name}"', name=name))

    async def _arriving(
        self, schema: str, table: str, name: str
    ) -> ArrivingRelationReference:
        """The named key landing on this relation, read now for the same reason.

        Matched on the handle rather than on the constraint's own name, which
        is not unique among arriving keys: a partitioned table and each of its
        partitions carry a constraint of the same name, all landing here, and
        three menu entries answering to one name would all open the first of
        them (D110).
        """
        for found in await self._fetch.arriving(schema, table):
            if _handle(found) == name:
                return found
        raise ValueError(say('Nothing named "{name}" points at this relation', name=name))

    async def _target_node(self, node_id: str) -> CatalogNode:
        """The relation pointed at, described exactly as the catalog does.

        Through `path_to` rather than a query of its own: that is the one place
        which turns an id of this source into a node, so a target cannot be
        described one way when walked into and another way when arrived at by
        following a key. A target dropped between reading the page and
        following the key raises `NodeNotFound` from there.
        """
        node = (await self._catalog.path_to(node_id))[-1]
        if node.kind not in ("table", "view"):
            # PostgreSQL only lets a key point at a relation, so this guards a
            # later node kind rather than anything reachable today: a schema
            # arriving here would open as a rows tab with no rows in it.
            raise NodeNotFound(node_id)
        return node


def _handle(found: ArrivingRelationReference) -> str:
    """What one arriving key is called on the wire.

    Issued by the source and read back by it, like the name of a declared
    reference (D106) and unlike a forward key's, which is the constraint's own
    name because that one is unique within the relation it belongs to. Here it
    is not: the constraint of a partitioned table is repeated on every
    partition, and all of them land on this relation. The screen shows
    `source_title` and never reads this.
    """
    return f"{found.name}@{found.source_node_id}"


def _cannot_match(column: FetchColumn) -> str | None:
    """Why the far column cannot be matched, if it cannot.

    A foreign key may stand on a type this source will not compare through the
    closed filter vocabulary — bytea is the plain example. Saying so is better
    than handing the grid a filter the very next fetch would refuse, and better
    than widening the vocabulary for a case nobody asked for.
    """
    if "eq" in column.filter_operators:
        return None
    return say(
        'This source cannot look up "{column}" values of type {type}',
        column=column.name,
        type=column.type.sql,
    )
