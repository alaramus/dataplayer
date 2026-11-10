"""What a Cassandra source can be asked to do from its catalog (D9, D348).

Cassandra keeps every structure change at once, so nothing here is rehearsed:
a preview reads `system_schema` for what a change would take with it — the
views over a table, the tables of a keyspace.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    JsonAction,
)
from app.adapters.cassandra.catalog import CassandraCatalog
from app.adapters.cassandra.cql import SQL, Composable, Identifier
from app.adapters.cassandra.design import CassandraTableDesign
from app.adapters.cassandra.inspection import Inspector, is_system_keyspace
from app.adapters.cassandra.session import CassandraSession
from app.adapters.catalog import NodeKind, SchemaNode, TableNode, ViewNode
from app.adapters.database_ids import database_id
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say

# CQL's limit on a keyspace's name, which is letters, digits and underscores.
NAME_LIMIT = 48
MAX_REPLICAS = 9


def _keyspace_name(value: str) -> str:
    if (
        not value
        or len(value) > NAME_LIMIT
        or not value[0].isalpha()
        or not all(char.isalnum() or char == "_" for char in value)
        or not value.isascii()
    ):
        raise ValueError(
            say(
                "A keyspace's name is letters, digits and underscores, starting with a letter, "
                "at most {limit}",
                limit=NAME_LIMIT,
            )
        )
    return value


async def _run(session: CassandraSession, *statements: Composable) -> None:
    """Structure statements, each waited for; a refusal is the action's."""
    try:
        for statement in statements:
            await session.page(statement.text(), wait_seconds=120)
    except ValueError as refused:
        raise ActionRefused("not_applicable", str(refused)) from None


async def create_keyspace(
    session: CassandraSession, inspector: Inspector, name: str, replicas: int = 1
) -> None:
    """A keyspace replicated in the node's own data centre (D348).

    `NetworkTopologyStrategy`, because ScyllaDB refuses `SimpleStrategy` for a
    keyspace kept in tablets and every server accepts this one.
    """
    _keyspace_name(name)
    profile = await inspector.profile()
    if is_system_keyspace(name, scylla=profile.scylla):
        raise ActionRefused(
            "not_applicable", say("That keyspace name belongs to the server")
        )
    if await inspector.keyspace(name) is not None:
        raise ActionRefused(
            "conflict", say('Keyspace "{name}" already exists', name=name)
        )
    centre = profile.data_center or "datacenter1"
    replication = (
        "{'class': 'NetworkTopologyStrategy', "
        + "'"
        + centre.replace("'", "''")
        + "': "
        + str(int(replicas))
        + "}"
    )
    await _run(
        session,
        SQL("CREATE KEYSPACE {} WITH replication = " + replication).format(
            Identifier(name)
        ),
    )


class CreateKeyspaceParams(BaseModel):
    name: str = Field(title=N_("Name"))
    replicas: int = Field(
        default=1,
        ge=1,
        le=MAX_REPLICAS,
        title=N_("Replicas"),
        description=N_("How many copies of each row the node's data centre keeps"),
    )

    _check = field_validator("name")(_keyspace_name)


class CreateKeyspace(JsonAction[CreateKeyspaceParams]):
    """A keyspace at the top of the connection, beside the others."""

    name: ClassVar[str] = "create_keyspace"
    title: ClassVar[str] = N_("New keyspace")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateKeyspaceParams

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._session = session
        self._inspector = inspector

    async def run(
        self, node_id: str | None, params: CreateKeyspaceParams
    ) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable",
                say("Keyspaces are created at the top of the connection"),
            )
        await create_keyspace(
            self._session, self._inspector, params.name, params.replicas
        )
        return ActionResult(
            message=say("Keyspace {name} created", name=params.name),
            reload_node_ids=[None, database_id(params.name)],
        )


async def _keyspace_target(
    catalog: CassandraCatalog, node_id: str | None
) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a keyspace"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", say("This keyspace cannot be dropped"))
    return node


async def _relation_target(
    catalog: CassandraCatalog, node_id: str | None, refused: str
) -> tuple[str, TableNode | ViewNode]:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a relation"))
    path = await catalog.path_to(node_id)
    node = path[-1]
    if not isinstance(node, TableNode | ViewNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return path[0].name, node


class DropKeyspaceParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything in it"),
        description=N_("Required when the keyspace still holds anything"),
    )


class DropKeyspace(JsonAction[DropKeyspaceParams]):
    """Drop a keyspace and everything in it, once it was said what that is."""

    name: ClassVar[str] = "drop_keyspace"
    title: ClassVar[str] = N_("Drop keyspace")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropKeyspaceParams

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._inspector = inspector

    async def run(
        self, node_id: str | None, params: DropKeyspaceParams
    ) -> ActionResult:
        preview = await self._preview(node_id, params)
        if preview.blocked:
            raise ActionRefused("not_applicable", preview.summary)
        node = await _keyspace_target(self._catalog, node_id)
        await _run(self._session, SQL("DROP KEYSPACE {}").format(Identifier(node.name)))
        return ActionResult(
            message=say("Keyspace {name} dropped", name=node.name),
            reload_node_ids=[None, node.id],
        )

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        return await self._preview(node_id, self._validated(raw))

    async def _preview(
        self, node_id: str | None, params: DropKeyspaceParams
    ) -> ActionPreview:
        node = await _keyspace_target(self._catalog, node_id)
        found = await self._inspector.relations(node.name, False, structure=False)
        tables = sum(1 for facts in found.values() if not facts.is_view)
        views = len(found) - tables
        held = []
        if tables:
            held.append(say("{count} tables and their rows", count=tables))
        if views:
            held.append(say("{count} views", count=views))
        if not held:
            return ActionPreview(
                summary=say("Keyspace {name} is empty", name=node.name)
            )
        if not params.cascade:
            return ActionPreview(
                summary=say("The keyspace is not empty"), items=held, blocked=True
            )
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=[say("Drop {what}", what=line) for line in held],
        )


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TruncateTable(JsonAction[NoParams]):
    """Every row of a table gone; its structure stays."""

    name: ClassVar[str] = "truncate_table"
    title: ClassVar[str] = N_("Truncate")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_("Delete every row of this table?")
    requires: ClassVar[Access] = "write"
    params_model = NoParams

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        keyspace, node = await _relation_target(
            self._catalog, node_id, say("This table cannot be truncated")
        )
        if not isinstance(node, TableNode):
            raise ActionRefused("not_applicable", say("This table cannot be truncated"))
        await _run(
            self._session, SQL("TRUNCATE {}").format(Identifier(keyspace, node.name))
        )
        return ActionResult(
            message=say("Every row of {name} deleted", name=node.name),
            reload_node_ids=[database_id(keyspace)],
        )


class DropRelation(JsonAction[NoParams]):
    """Drop tables and views together, once the views over them were named."""

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = NoParams

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._inspector = inspector

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        return await self._drop([node_id])

    async def perform_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionResult:
        self._validated(raw)
        return await self._drop(list(node_ids))

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets([node_id]))

    async def preview_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets(list(node_ids)))

    async def _targets(
        self, node_ids: Sequence[str | None]
    ) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused(
                "not_applicable", say("A relation may be dropped only once")
            )
        return [
            await _relation_target(
                self._catalog, node_id, say("This relation cannot be dropped")
            )
            for node_id in node_ids
        ]

    async def _views_over(self, keyspace: str, table: str) -> list[str]:
        found = await self._inspector.relations(keyspace, False, structure=False)
        return [
            name
            for name, facts in found.items()
            if facts.is_view and facts.base_table == table
        ]

    async def _drop(self, node_ids: Sequence[str | None]) -> ActionResult:
        targets = await self._targets(node_ids)
        dropping = {(keyspace, node.name) for keyspace, node in targets}
        statements: list[Composable] = []
        # A table goes only after the views over it, which the server insists on.
        for keyspace, node in sorted(
            targets, key=lambda target: not isinstance(target[1], ViewNode)
        ):
            if isinstance(node, TableNode):
                for view in await self._views_over(keyspace, node.name):
                    if (keyspace, view) not in dropping:
                        statements.append(
                            SQL("DROP MATERIALIZED VIEW {}").format(
                                Identifier(keyspace, view)
                            )
                        )
                        dropping.add((keyspace, view))
                statements.append(
                    SQL("DROP TABLE {}").format(Identifier(keyspace, node.name))
                )
            else:
                statements.append(
                    SQL("DROP MATERIALIZED VIEW {}").format(
                        Identifier(keyspace, node.name)
                    )
                )
        await _run(self._session, *statements)
        name = targets[0][1].name if len(targets) == 1 else None
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[
                *sorted({database_id(keyspace) for keyspace, _ in targets})
            ],
        )

    async def _preview(
        self, targets: Sequence[tuple[str, TableNode | ViewNode]]
    ) -> ActionPreview:
        dropped = {(keyspace, node.name) for keyspace, node in targets}
        items: list[str] = []
        for keyspace, node in targets:
            if isinstance(node, TableNode):
                for view in await self._views_over(keyspace, node.name):
                    if (keyspace, view) not in dropped:
                        items.append(
                            say(
                                "Materialized view {view} reads {name} and is dropped with it",
                                view=f"{keyspace}.{view}",
                                name=node.name,
                            )
                        )
        name = targets[0][1].name if len(targets) == 1 else None
        if not items:
            return ActionPreview(
                summary=(
                    say("Nothing else depends on {name}", name=name)
                    if name is not None
                    else say(
                        "Nothing else depends on {count} relations", count=len(targets)
                    )
                )
            )
        return ActionPreview(
            summary=(
                say("What dropping {name} would do:", name=name)
                if name is not None
                else say(
                    "What dropping {count} relations would do:", count=len(targets)
                )
            ),
            items=items,
        )


class CreateTableParams(BaseModel):
    # The designer is registered against this workflow, as PostgreSQL's is.
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"}
    )

    definition: TableDefinition
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table, review its statements, then create it (D117, D347)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    params_model = CreateTableParams

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._design = CassandraTableDesign(session, catalog, inspector)

    async def run(self, node_id: str | None, params: CreateTableParams) -> ActionResult:
        if node_id is None:
            raise ActionRefused(
                "not_applicable", say("Choose a keyspace to create it in")
            )
        try:
            node = await self._design.create_table(
                node_id, params.definition, params.fingerprint
            )
        except DesignRefused as refused:
            raise ActionRefused(
                "conflict" if refused.problem.kind == "conflict" else "not_applicable",
                refused.problem.message,
            ) from None
        return ActionResult(
            message=say("{name} created", name=params.definition.name),
            reload_node_ids=[node_id],
            created_node_id=node.id,
        )


class CassandraActionType(ActionType, Protocol):
    def __call__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> Action[Any]: ...


CASSANDRA_ACTION_TYPES: tuple[CassandraActionType, ...] = (
    CreateKeyspace,
    CreateTable,
    TruncateTable,
    DropRelation,
    DropKeyspace,
)


class CassandraActions:
    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._catalog = catalog
        self._actions = ActionSet(
            [
                action_type(session, catalog, inspector)
                for action_type in CASSANDRA_ACTION_TYPES
            ]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return [self._actions.get(CreateKeyspace.name)]
        node = (await self._catalog.path_to(node_id))[-1]
        if isinstance(node, SchemaNode | TableNode | ViewNode) and not node.is_system:
            # Cassandra's virtual keyspaces are the server's, and marked so.
            return self._actions.for_kind(node.kind)
        return []
