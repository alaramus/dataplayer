"""Catalog actions owned by PostgreSQL."""

from typing import Any, ClassVar, Protocol

from psycopg import sql
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    JsonAction,
    NodeReplacement,
)
from app.adapters.catalog import NodeKind, TableNode, ViewNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.core.access import Access


def _relation_name(value: str) -> str:
    if value == "" or value != value.strip():
        raise ValueError("A relation name cannot be empty or start or end with spaces")
    if len(value.encode("utf-8")) > 63:
        raise ValueError("A PostgreSQL relation name cannot exceed 63 bytes")
    return value


class RenameRelationParams(BaseModel):
    new_name: str = Field(title="New name")

    _check = field_validator("new_name")(_relation_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = "Rename"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    # Renaming a relation is DDL, and it is the shape of the source that
    # changes; someone who may edit rows is not thereby allowed to do it.
    requires: ClassVar[Access] = "structure"
    params_model = RenameRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: RenameRelationParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a relation to rename")
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, (TableNode, ViewNode)) or node.is_system:
            raise ActionRefused("not_applicable", "This relation cannot be renamed")
        if params.new_name == node.name:
            raise ActionRefused("conflict", "The relation already has that name")

        schema = path[0].name
        siblings = await self._catalog.list_children(schema)
        if params.new_name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict", f'{schema} already has a relation named "{params.new_name}"'
            )

        if isinstance(node, TableNode):
            command = sql.SQL("ALTER TABLE")
        elif node.is_materialized:
            command = sql.SQL("ALTER MATERIALIZED VIEW")
        else:
            command = sql.SQL("ALTER VIEW")
        statement = sql.SQL("{} {} RENAME TO {}").format(
            command,
            sql.Identifier(schema, node.name),
            sql.Identifier(params.new_name),
        )
        await self._session.schema_change(statement.as_string())
        new_node_id = f"{schema}.{params.new_name}"
        return ActionResult(
            message=f"Renamed to {params.new_name}",
            reload_node_id=schema,
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=params.new_name,
            ),
        )


class PostgresActionType(ActionType, Protocol):
    def __call__(
        self, session: PostgresSession, catalog: PostgresCatalog
    ) -> Action[Any]: ...


POSTGRES_ACTION_TYPES: tuple[PostgresActionType, ...] = (RenameRelation,)


class PostgresActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet(
            [action_type(session, catalog) for action_type in POSTGRES_ACTION_TYPES]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return []
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if isinstance(node, (TableNode, ViewNode)) and not node.is_system:
            return self._actions.for_kind(node.kind)
        return []
