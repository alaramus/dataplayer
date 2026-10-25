"""What a ClickHouse source can be asked to do from its catalog (D9).

Only the designed table so far; the rest of what a database offers arrives
with the actions of a later slice.
"""

from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    JsonAction,
)
from app.adapters.catalog import NodeKind, SchemaNode
from app.adapters.clickhouse.catalog import ClickhouseCatalog
from app.adapters.clickhouse.design import ClickhouseTableDesign
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say


class CreateTableParams(BaseModel):
    # The designer is registered against this workflow, as PostgreSQL's is.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"})

    definition: TableDefinition
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table, review its statement, then create it (D117, D274)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._design = ClickhouseTableDesign(session, catalog)

    async def run(self, node_id: str | None, params: CreateTableParams) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a database to create it in"))
        try:
            node = await self._design.create_table(node_id, params.definition, params.fingerprint)
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


class ClickhouseActionType(ActionType, Protocol):
    def __call__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> Action[Any]: ...


CLICKHOUSE_ACTION_TYPES: tuple[ClickhouseActionType, ...] = (CreateTable,)


class ClickhouseActions:
    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in CLICKHOUSE_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return []
        node = (await self._catalog.path_to(node_id))[-1]
        # The server's own databases are read and never changed.
        if isinstance(node, SchemaNode) and not node.is_system:
            return self._actions.for_kind(node.kind)
        return []
