"""Following one foreign key of one row to the rows it names."""

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchColumn, ScalarFilter
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.fetch import PostgresFetch, RelationReference
from app.adapters.protocol import NodeNotFound
from app.adapters.references import (
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceTarget,
)


class PostgresReferences:
    """Turning "this row, this key" into a place and a predicate.

    Everything the answer is made of is read from the server at the moment of
    asking: which references the relation has, what they point at now, and what
    the target's columns are called and admit. Nothing is taken from the
    request but the name of the reference and the values, and both are checked
    against that reading before a single filter is built.
    """

    def __init__(self, catalog: PostgresCatalog, fetch: PostgresFetch) -> None:
        self._catalog = catalog
        self._fetch = fetch

    async def follow_reference(
        self, request: FollowReferenceRequest
    ) -> ReferenceTarget:
        schema, _, table = request.node_id.partition(".")
        if not table:
            raise ValueError(
                f'"{request.node_id}" is not a relation: expected schema.table'
            )

        reference = await self._reference(schema, table, request.reference)
        supplied = {value.column: value.value for value in request.values}
        if len(supplied) != len(request.values):
            raise ValueError("A reference column may be supplied only once")
        if set(supplied) != set(reference.columns):
            raise ValueError(
                f'Reference "{reference.name}" is over {", ".join(reference.columns)}'
            )

        # MATCH SIMPLE and MATCH FULL agree here: a key with a missing value
        # names no row at all. The source says so rather than the screen
        # deciding it, because what an absent key means belongs to the source.
        present = {
            name: value for name, value in supplied.items() if value is not None
        }
        if len(present) != len(supplied):
            return NoReferencedRows(reason="This row has no value for that reference")

        target = await self._target_node(reference.target_node_id)
        target_schema, _, target_table = target.id.partition(".")
        info = await self._fetch.relation_info(target_schema, target_table)
        columns = {column.name: column for column in info.columns}

        filters: list[ScalarFilter] = []
        for local, remote in zip(
            reference.columns, reference.target_columns, strict=True
        ):
            column = columns.get(remote)
            if column is None:
                # PostgreSQL does not allow a constraint to outlive the column
                # it names, so the target has changed under this very call.
                raise NodeNotFound(target.id)
            refusal = _cannot_match(column)
            if refusal is not None:
                return NoReferencedRows(reason=refusal)
            filters.append(
                ScalarFilter(column=remote, op="eq", value=present[local])
            )

        return ReferencedRows(node=target, filters=list(filters))

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
        raise ValueError(f'Relation has no reference "{name}"')

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


def _cannot_match(column: FetchColumn) -> str | None:
    """Why the target column cannot be matched, if it cannot.

    A foreign key may stand on a type this source will not compare through the
    closed filter vocabulary — bytea is the plain example. Saying so is better
    than handing the grid a filter the very next fetch would refuse, and better
    than widening the vocabulary for a case nobody asked for.
    """
    if "eq" in column.filter_operators:
        return None
    return (
        f'This source cannot look up "{column.name}" values '
        f"of type {column.type.sql}"
    )
