"""What `system_schema` says about a keyspace's tables and views (D341).

Every name is a bound value, so a keyspace or a table is looked up rather than
written into a statement. Cassandra keeps its virtual tables — `system_views`
— in `system_virtual_schema`, which has the same shape and which ScyllaDB does
not have.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.adapters.cassandra.session import CassandraSession, ServerProfile
from app.adapters.cassandra.types import build_column_type
from app.adapters.protocol import AdapterError
from app.adapters.relation import ColumnType

ColumnKind = Literal["partition_key", "clustering", "static", "regular"]
_KIND_ORDER = {"partition_key": 0, "clustering": 1, "static": 2, "regular": 3}
_KINDS: dict[str, ColumnKind] = {
    "partition_key": "partition_key",
    "clustering": "clustering",
    "static": "static",
    "regular": "regular",
}

# Keyspaces a ScyllaDB server makes for itself beside its `system_…` ones.
_SCYLLA_OWN = frozenset({"audit"})


def is_system_keyspace(name: str, *, scylla: bool) -> bool:
    """The server's own keyspaces: `system`, every `system_…`, and ScyllaDB's `audit`."""
    return (
        name == "system"
        or name.startswith("system_")
        or (scylla and name in _SCYLLA_OWN)
    )


SCHEMA = "system_schema"
VIRTUAL_SCHEMA = "system_virtual_schema"

_KEYSPACES = "SELECT keyspace_name FROM {schema}.keyspaces"
_KEYSPACE = "SELECT keyspace_name FROM {schema}.keyspaces WHERE keyspace_name = ?"
_ALL_TABLES = "SELECT keyspace_name, table_name FROM system_schema.tables"
_TABLES = "SELECT table_name, comment FROM {schema}.tables WHERE keyspace_name = ?"
_VIEWS = (
    "SELECT view_name, base_table_name, comment, where_clause "
    "FROM system_schema.views WHERE keyspace_name = ?"
)
_COLUMNS = (
    "SELECT table_name, column_name, kind, position, type, clustering_order "
    "FROM {schema}.columns WHERE keyspace_name = ?"
)
_INDEX_NAMES = "SELECT index_name FROM system_schema.indexes WHERE keyspace_name = ?"
_INDEXES = (
    "SELECT table_name, index_name, kind, options FROM system_schema.indexes "
    "WHERE keyspace_name = ?"
)


@dataclass(frozen=True)
class ColumnFacts:
    name: str
    kind: ColumnKind
    position: int
    type_text: str
    descending: bool

    @property
    def type(self) -> ColumnType:
        return build_column_type(self.type_text)

    @property
    def in_key(self) -> bool:
        return self.kind in ("partition_key", "clustering")


@dataclass(frozen=True)
class IndexFacts:
    name: str
    kind: str
    options: dict[str, str]

    @property
    def target(self) -> str:
        return self.options.get("target", "")

    @property
    def using(self) -> str:
        return self.options.get("class_name", "")


@dataclass
class RelationFacts:
    keyspace: str
    name: str
    is_system: bool = False
    is_view: bool = False
    is_virtual: bool = False
    base_table: str | None = None
    where_clause: str | None = None
    comment: str | None = None
    columns: list[ColumnFacts] = field(default_factory=list)
    indexes: list[IndexFacts] = field(default_factory=list)

    @property
    def partition_key(self) -> list[ColumnFacts]:
        return sorted(
            (column for column in self.columns if column.kind == "partition_key"),
            key=lambda column: column.position,
        )

    @property
    def clustering(self) -> list[ColumnFacts]:
        return sorted(
            (column for column in self.columns if column.kind == "clustering"),
            key=lambda column: column.position,
        )

    @property
    def primary_key(self) -> list[ColumnFacts]:
        return self.partition_key + self.clustering

    @property
    def has_counters(self) -> bool:
        return any(column.type_text == "counter" for column in self.columns)


def ordered_columns(columns: Iterable[ColumnFacts]) -> list[ColumnFacts]:
    """The order `DESCRIBE` writes: the key in its order, then the rest by name."""
    return sorted(
        columns,
        key=lambda column: (
            _KIND_ORDER.get(column.kind, 3),
            column.position if column.kind in ("partition_key", "clustering") else 0,
            column.name,
        ),
    )


def _column(row: dict[str, Any]) -> ColumnFacts:
    kind = str(row["kind"])
    return ColumnFacts(
        name=str(row["column_name"]),
        kind=_KINDS.get(kind, "regular"),
        position=int(row["position"] or 0),
        type_text=str(row["type"]),
        descending=str(row.get("clustering_order") or "").lower() == "desc",
    )


class Inspector:
    """Reads of `system_schema`, and of `system_virtual_schema` where there is one."""

    def __init__(self, session: CassandraSession) -> None:
        self._session = session
        self._virtual: bool | None = None

    async def scylla(self) -> bool:
        return (await self._session.profile()).scylla

    async def profile(self) -> ServerProfile:
        return await self._session.profile()

    async def has_virtual_schema(self) -> bool:
        if self._virtual is None:
            # ScyllaDB answers a missing keyspace's table as a refusal.
            try:
                await self._session.query(_KEYSPACES.format(schema=VIRTUAL_SCHEMA))
                self._virtual = True
            except AdapterError, ValueError:
                self._virtual = False
        return self._virtual

    async def keyspaces(self) -> list[tuple[str, bool]]:
        """Every keyspace, and whether it is a virtual one."""
        names = [
            (str(row["keyspace_name"]), False)
            for row in await self._session.query(_KEYSPACES.format(schema=SCHEMA))
        ]
        known = {name for name, _ in names}
        if await self.has_virtual_schema():
            names += [
                (str(row["keyspace_name"]), True)
                for row in await self._session.query(
                    _KEYSPACES.format(schema=VIRTUAL_SCHEMA)
                )
                if str(row["keyspace_name"]) not in known
            ]
        return names

    async def table_names(self) -> dict[str, list[str]]:
        """Every table's name by keyspace, in one read, for the frameworks they betray."""
        names: dict[str, list[str]] = {}
        for row in await self._session.query(_ALL_TABLES):
            names.setdefault(str(row["keyspace_name"]), []).append(
                str(row["table_name"])
            )
        return names

    async def keyspace(self, name: str) -> tuple[str, bool] | None:
        if await self._session.query(_KEYSPACE.format(schema=SCHEMA), [name]):
            return name, False
        if await self.has_virtual_schema() and await self._session.query(
            _KEYSPACE.format(schema=VIRTUAL_SCHEMA), [name]
        ):
            return name, True
        return None

    async def relations(
        self,
        keyspace: str,
        virtual: bool,
        *,
        structure: bool = True,
        names: list[str] | None = None,
    ) -> dict[str, RelationFacts]:
        """The tables and views of a keyspace, by name; with columns and indexes when asked.

        `names` narrows every read to those relations, for one relation's model.
        """
        schema = VIRTUAL_SCHEMA if virtual else SCHEMA

        async def read(statement: str, column: str) -> list[dict[str, Any]]:
            if names is None:
                return await self._session.query(statement, [keyspace])
            return await self._session.query(
                f"{statement} AND {column} IN ?", [keyspace, names]
            )

        found: dict[str, RelationFacts] = {}
        system = is_system_keyspace(keyspace, scylla=await self.scylla())
        for row in await read(_TABLES.format(schema=schema), "table_name"):
            name = str(row["table_name"])
            found[name] = RelationFacts(
                keyspace=keyspace,
                name=name,
                is_system=system,
                is_virtual=virtual,
                comment=str(row["comment"]) if row.get("comment") else None,
            )
        if not virtual:
            # ScyllaDB keeps a secondary index in a view named after it; the
            # index is what a person made, and it is listed on its table.
            behind_indexes = {
                f"{row['index_name']}_index"
                for row in await self._session.query(_INDEX_NAMES, [keyspace])
            }
            for row in await read(_VIEWS, "view_name"):
                name = str(row["view_name"])
                if name in behind_indexes:
                    continue
                found[name] = RelationFacts(
                    keyspace=keyspace,
                    name=name,
                    is_system=system,
                    is_view=True,
                    base_table=str(row["base_table_name"]),
                    where_clause=str(row["where_clause"])
                    if row.get("where_clause")
                    else None,
                    comment=str(row["comment"]) if row.get("comment") else None,
                )
        if not structure or not found:
            return found
        for row in await read(_COLUMNS.format(schema=schema), "table_name"):
            facts = found.get(str(row["table_name"]))
            if facts is not None:
                facts.columns.append(_column(row))
        if not virtual:
            for row in await read(_INDEXES, "table_name"):
                facts = found.get(str(row["table_name"]))
                if facts is not None:
                    options = row.get("options") or {}
                    facts.indexes.append(
                        IndexFacts(
                            name=str(row["index_name"]),
                            kind=str(row["kind"]),
                            options={
                                str(key): str(value) for key, value in options.items()
                            },
                        )
                    )
        for facts in found.values():
            facts.columns = ordered_columns(facts.columns)
        return found

    async def relation(self, keyspace: str, name: str) -> RelationFacts | None:
        place = await self.keyspace(keyspace)
        if place is None:
            return None
        return (await self.relations(keyspace, place[1], names=[name])).get(name)
