"""Catalog actions owned by PostgreSQL."""

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, ClassVar, Protocol

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionDownload,
    ActionDownloadMetadata,
    ActionOffers,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActionUnavailability,
    ActsOn,
    FileAction,
    FilePayload,
    JsonAction,
    NodeReplacement,
)
from app.adapters.catalog import (
    CatalogNode,
    NodeKind,
    ReportNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.csv_load import LoadCsvParams as SharedLoadCsvParams
from app.adapters.csv_load import chosen_rows, read_upload, table_name
from app.adapters.hypertable_design import HypertableDesignState
from app.adapters.model_code import (
    DIALECT_SUFFIX,
    DIALECT_TITLE,
    CodeDialect,
    render,
)
from app.adapters.postgres.catalog import PostgresCatalog, is_system_schema
from app.adapters.postgres.names import name_check
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.roles import CreateRole
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import ROLES_REPORT_ID, TABLESPACES_REPORT_ID
from app.adapters.postgres.table_design import PostgresTableDesign
from app.adapters.postgres.tablespaces import TABLESPACE_ACTION_TYPES
from app.adapters.postgres.timescale.actions import TimescaleActions
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say

_relation_name = name_check("relation")
_schema_name = name_check("schema")


SCHEMA_CHANGE_REFUSALS = {
    # insufficient_privilege.
    "42501": N_("This connection may not change schemas"),
    # reserved_name: PostgreSQL reserves pg_ for its own schemas.
    "42939": N_("That schema name is reserved by PostgreSQL"),
}


async def _existing_schema(session: PostgresSession, name: str) -> str | None:
    """The server's exact spelling of one schema, or nothing."""
    rows = await session.query(
        "SELECT nspname AS name FROM pg_catalog.pg_namespace WHERE nspname = %s",
        (name,),
    )
    return None if not rows else str(rows[0]["name"])


async def _schema_target(
    catalog: PostgresCatalog, node_id: str | None, *, choose: str, refused: str
) -> SchemaNode:
    """The schema an action is on; `choose` and `refused` are its own
    sentences, already worded, for no schema and for one it cannot touch."""
    if node_id is None:
        raise ActionRefused("not_applicable", choose)
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    reason = await catalog.schema_action_reason(node.name)
    if reason is None:
        reason = await catalog.cascade_reason(node.name)
    if reason is not None:
        raise ActionRefused("not_applicable", reason)
    return node


async def _guard_relation_action(
    catalog: PostgresCatalog, schema: str, node: TableNode | ViewNode
) -> None:
    reason = await catalog.relation_action_reason(schema, node.name)
    if reason is not None:
        raise ActionRefused("not_applicable", reason)


class CreateSchemaParams(BaseModel):
    name: str = Field(title=N_("Name"))

    _check = field_validator("name")(_schema_name)


class CreateSchema(JsonAction[CreateSchemaParams]):
    """Create a grouping at the current catalog level, not inside one."""

    name: ClassVar[str] = "create_schema"
    title: ClassVar[str] = N_("New schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session

    async def run(
        self, node_id: str | None, params: CreateSchemaParams
    ) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable", say("Schemas are created at the top of the connection")
            )
        if is_system_schema(params.name):
            raise ActionRefused(
                "not_applicable", say("That schema name belongs to the server")
            )
        if await _existing_schema(self._session, params.name) is not None:
            raise ActionRefused(
                "conflict", say('Schema "{name}" already exists', name=params.name)
            )
        statement = sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(params.name))
        await self._session.schema_change(
            statement.as_string(), refusals=SCHEMA_CHANGE_REFUSALS
        )
        return ActionResult(
            message=say("Schema {name} created", name=params.name),
            # Clear a branch left under the same opaque id by an earlier drop,
            # as well as the root that gained this grouping.
            reload_node_ids=[None, params.name],
        )


class RenameSchemaParams(BaseModel):
    new_name: str = Field(
        title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_schema_name)


class RenameSchema(JsonAction[RenameSchemaParams]):
    name: ClassVar[str] = "rename_schema"
    title: ClassVar[str] = N_("Rename schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    requires: ClassVar[Access] = "structure"
    params_model = RenameSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: RenameSchemaParams
    ) -> ActionResult:
        node = await _schema_target(
            self._catalog,
            node_id,
            choose=say("Choose a schema to rename"),
            refused=say("This schema cannot be renamed"),
        )
        if params.new_name == node.name:
            raise ActionRefused("conflict", say("The schema already has that name"))
        if is_system_schema(params.new_name):
            raise ActionRefused(
                "not_applicable", say("That schema name belongs to the server")
            )
        if await _existing_schema(self._session, params.new_name) is not None:
            raise ActionRefused(
                "conflict", say('Schema "{name}" already exists', name=params.new_name)
            )
        statement = sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(
            sql.Identifier(node.name), sql.Identifier(params.new_name)
        )
        await self._session.schema_change(
            statement.as_string(), refusals=SCHEMA_CHANGE_REFUSALS
        )
        return ActionResult(
            message=say(
                "Schema {name} renamed to {new_name}",
                name=node.name,
                new_name=params.new_name,
            ),
            reload_node_ids=[None, node.name, params.new_name],
            replacement=NodeReplacement(
                old_node_id=node.name,
                new_node_id=params.new_name,
                title=params.new_name,
            ),
        )


class RenameRelationParams(BaseModel):
    new_name: str = Field(
        title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_relation_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = N_("Rename")
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
            raise ActionRefused("not_applicable", say("Choose a relation to rename"))
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, (TableNode, ViewNode)) or node.is_system:
            raise ActionRefused("not_applicable", say("This relation cannot be renamed"))
        if params.new_name == node.name:
            raise ActionRefused("conflict", say("The relation already has that name"))

        schema = path[0].name
        await _guard_relation_action(self._catalog, schema, node)
        siblings = await self._catalog.list_children(schema)
        if params.new_name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say(
                    '{schema} already has a relation named "{name}"',
                    schema=schema,
                    name=params.new_name,
                ),
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
            message=say("Renamed to {name}", name=params.new_name),
            reload_node_ids=[schema],
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=params.new_name,
            ),
        )


class MoveRelationParams(BaseModel):
    # The destinations are the source's own groupings, and only the source can
    # list them. The hint says the value is one of their ids, so the form
    # offers what this connection actually has instead of asking for a name
    # that has to be spelled exactly right to be accepted.
    target_schema: str = Field(
        title=N_("Target schema"), json_schema_extra={"x-ui-purpose": "grouping"}
    )

    _check = field_validator("target_schema")(_schema_name)


class MoveRelation(JsonAction[MoveRelationParams]):
    """Move one source-issued relation and name both changed branches."""

    name: ClassVar[str] = "move_relation"
    title: ClassVar[str] = N_("Move to schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    bulk: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = MoveRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: MoveRelationParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a relation to move"))
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, TableNode | ViewNode) or node.is_system:
            raise ActionRefused("not_applicable", say("This relation cannot be moved"))

        source_schema = path[0].name
        await _guard_relation_action(self._catalog, source_schema, node)
        if params.target_schema == source_schema:
            raise ActionRefused(
                "conflict", say("The relation is already in {schema}", schema=source_schema)
            )
        target_name = await _existing_schema(self._session, params.target_schema)
        if target_name is None:
            raise ActionRefused(
                "not_applicable",
                say('Schema "{name}" does not exist', name=params.target_schema),
            )
        if is_system_schema(target_name):
            raise ActionRefused(
                "not_applicable", say("Relations cannot be moved into a system schema")
            )
        reason = await self._catalog.schema_action_reason(
            target_name, include_relations=False
        )
        if reason is not None:
            raise ActionRefused("not_applicable", reason)
        siblings = await self._catalog.list_children(target_name)
        if node.name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say(
                    '{schema} already has a relation named "{name}"',
                    schema=target_name,
                    name=node.name,
                ),
            )

        if isinstance(node, TableNode):
            command = sql.SQL("ALTER TABLE")
        elif node.is_materialized:
            command = sql.SQL("ALTER MATERIALIZED VIEW")
        else:
            command = sql.SQL("ALTER VIEW")
        statement = sql.SQL("{} {} SET SCHEMA {}").format(
            command,
            sql.Identifier(source_schema, node.name),
            sql.Identifier(target_name),
        )
        await self._session.schema_change(
            statement.as_string(),
            refusals={"42501": say("This connection may not move that relation")},
        )
        new_node_id = f"{target_name}.{node.name}"
        return ActionResult(
            message=say("{name} moved to {schema}", name=node.name, schema=target_name),
            reload_node_ids=[source_schema, target_name],
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=node.name,
            ),
        )


class CreateTableParams(BaseModel):
    # A screen of its own rather than a form: what a table is cannot be asked
    # for with a list of fields, and the editor that asks for it is registered
    # against this workflow rather than against the name of the action (D73).
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"}
    )

    definition: TableDefinition
    # What the reviewer was looking at. The statements are composed again here
    # from the definition, and a definition that no longer composes to the
    # reviewed plan is refused rather than run.
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table object by object, review the SQL, then create it.

    Distinct from `load_csv` and from keeping rows as a table: both of those
    make a relation out of data that already exists and take their columns from
    it. This one starts from nothing, so the keys, the indexes and the checks
    are part of what is being asked for (D117).
    """

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    # It makes something inside the schema rather than changing the schema, as
    # loading a file does.
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    # One design is one table. Applying a draft to every selected schema would
    # be creating things nobody looked at a plan for.
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._design = PostgresTableDesign(session, catalog, PostgresRelation(session))

    async def run(
        self, node_id: str | None, params: CreateTableParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a schema to create it in"))
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


class LoadCsvParams(SharedLoadCsvParams):
    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else _relation_name(value)


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a table of the schema being read.

    An action rather than a route of its own, so the button for it appears in
    the catalog without the screen learning anything about PostgreSQL: what a
    source offers, what its form holds and whether it carries a file are all
    read off this declaration (D9, D13).
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    # It makes something inside the schema rather than changing the schema, so
    # it belongs to the place being looked at rather than to what is ticked.
    acts_on: ClassVar[ActsOn] = "destination"
    # Creating a relation is DDL: someone who may edit rows may not do it.
    requires: ClassVar[Access] = "structure"
    # One file is one table. Loading it into three schemas at once is not the
    # same kind of thing as deleting three files with one form.
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog
        self._relations = PostgresRelationChanges(session, catalog)

    async def run(
        self, node_id: str | None, params: LoadCsvParams, payload: FilePayload
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a schema to load into"))
        schema = params.schema_name or node_id
        if params.create_schema:
            await self._create_schema(schema)
        else:
            schemas = await self._catalog.list_children(None)
            if schema not in {node.id for node in schemas if isinstance(node, SchemaNode)}:
                raise ActionRefused(
                    "not_applicable", say('Schema "{name}" does not exist', name=schema)
                )

        name = table_name(params, payload, _relation_name)
        siblings = await self._catalog.list_children(schema)
        if name in {sibling.name for sibling in siblings}:
            raise ActionRefused("conflict", say("{name} is already there", name=name))
        targets, rows = chosen_rows(await read_upload(payload), params, _relation_name)

        result = await self._relations.create_relation(
            CreateRelationRequest(
                parent_node_id=schema,
                name=name,
                # Every column is text, because a delimited file states no
                # types and one read off its rows would depend on how many of
                # them were looked at. A column takes another type afterwards
                # through the change that counts the rows in its way (D38).
                columns=[NewColumn(name=target, type_code="text") for target in targets],
                rows=rows,
            )
        )
        if not isinstance(result, RelationCreated):
            # Unreachable while every column is text, and answered rather than
            # ignored: what a value may be is the source's to say, not this
            # action's to assume.
            cell = result.cells[0]
            raise ActionRefused(
                "not_applicable",
                say(
                    "Row {row}, column {column}: that value cannot be read",
                    row=cell.row + 1,
                    column=cell.column,
                ),
            )
        return ActionResult(
            message=say(
                "{name} created with {count} rows", name=name, count=result.inserted
            ),
            # A new schema itself is a child of the root. Existing schemas only
            # gain the relation below them.
            reload_node_ids=[None, schema] if params.create_schema else [schema],
        )

    async def _create_schema(self, schema: str) -> None:
        _schema_name(schema)
        schemas = await self._catalog.list_children(None)
        if schema in {node.id for node in schemas if isinstance(node, SchemaNode)}:
            raise ActionRefused(
                "conflict", say('Schema "{name}" already exists', name=schema)
            )
        await self._session.schema_change(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)).as_string(),
            refusals={"42501": say("This connection may not create schemas")},
        )


# What a refused drop means, by SQLSTATE. The code is safe to look at and the
# message beside it is not, so the wording is ours; the DETAIL of the first of
# them is the list of what stands in the way, and that is passed on.
def drop_refusals(targets: Sequence[tuple[str, TableNode | ViewNode]]) -> dict[str, str]:
    """The same three refusals, about whatever is being dropped.

    Written per call rather than as one constant because the subject is a
    relation when one is selected and a count when several are: "something
    else is built on this relation" is the wrong sentence about five of them.
    """
    name = _one_name(targets)
    if name is not None:
        return {
            # dependent_objects_still_exist.
            "2BP01": say("Something else is built on {name}", name=name),
            # lock_not_available: somebody is reading or writing it right now.
            "55P03": say("Something is using {name}; try again in a moment", name=name),
            # insufficient_privilege.
            "42501": say("This connection may not drop {name}", name=name),
        }
    count = len(targets)
    return {
        "2BP01": say("Something else is built on {count} relations", count=count),
        "55P03": say(
            "Something is using {count} relations; try again in a moment", count=count
        ),
        "42501": say("This connection may not drop {count} relations", count=count),
    }


class DropRelationParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything built on it"),
        description=N_("Required when a view or a reference depends on this relation"),
    )


# What a relation is dropped by, and the order the commands are issued in.
# A view is dropped before the table it reads, so that selecting both succeeds
# without a cascade; the other order would refuse a set the user meant.
DROP_COMMANDS: tuple[tuple[str, sql.SQL], ...] = (
    ("view", sql.SQL("DROP VIEW")),
    ("materialized view", sql.SQL("DROP MATERIALIZED VIEW")),
    ("table", sql.SQL("DROP TABLE")),
)


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations, with or without what stands on them.

    Previewable, and that is the point of it: what a cascade takes with it is
    written in `pg_depend`, and the only answer worth showing somebody about to
    destroy something is PostgreSQL's own. So the preview is the drop itself,
    rolled back, and what it lists cannot disagree with what happens.

    A selection is dropped together rather than one relation at a time. Three
    relations that depend on each other are dropped by one transaction and
    refused by three separate requests, in whatever order the client happened
    to send them in — and somebody who ticked all three meant the set.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: DropRelationParams
    ) -> ActionResult:
        return await self._drop([node_id], params)

    async def perform_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionResult:
        return await self._drop(list(node_ids), self._validated(raw))

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        return await self._rehearse([node_id], self._validated(raw))

    async def preview_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionPreview:
        return await self._rehearse(list(node_ids), self._validated(raw))

    async def _drop(
        self, node_ids: Sequence[str | None], params: DropRelationParams
    ) -> ActionResult:
        targets = await self._targets(node_ids)
        await self._guard_cascades(targets, cascade=params.cascade)
        statements = self._statements(targets, cascade=params.cascade)
        # One transaction, so a selection that cannot be dropped whole leaves
        # every relation in it standing. Half a drop is not a partial success,
        # it is a schema nobody asked for.
        async with self._session.transaction(
            refusals=drop_refusals(targets)
        ) as change:
            for statement in statements:
                await change.schema_change(statement)
        name = _one_name(targets)
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[*sorted({schema for schema, _ in targets})],
        )

    async def _rehearse(
        self, node_ids: Sequence[str | None], params: DropRelationParams
    ) -> ActionPreview:
        """What this drop would take with it, as the server itself reports it.

        The same statements the form describes, so ticking the box changes the
        answer: without a cascade a relation something is built on refuses, and
        the refusal names what is in the way; with one, the server lists what
        it would drop as it goes.
        """
        targets = await self._targets(node_ids)
        await self._guard_cascades(targets, cascade=params.cascade)
        rehearsal = await self._session.rehearse(
            *self._statements(targets, cascade=params.cascade),
            refusals=drop_refusals(targets),
        )
        if rehearsal.refused is not None:
            # An answer rather than a failure: the question was "what would
            # happen", and what would happen is that it would be refused.
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        name = _one_name(targets)
        count = len(targets)
        if not rehearsal.said:
            return ActionPreview(
                summary=(
                    say("Nothing else depends on {name}", name=name)
                    if name is not None
                    else say("Nothing else depends on {count} relations", count=count)
                )
            )
        # The lines are the server's own sentences, so the summary leaves room
        # for them to say what they say rather than repeating half of it.
        return ActionPreview(
            summary=(
                say("What dropping {name} would do:", name=name)
                if name is not None
                else say("What dropping {count} relations would do:", count=count)
            ),
            items=rehearsal.said,
        )

    async def _guard_cascades(
        self, targets: Sequence[tuple[str, TableNode | ViewNode]], *, cascade: bool
    ) -> None:
        if not cascade:
            return
        for schema, node in targets:
            reason = await self._catalog.cascade_reason(schema, node.name)
            if reason is not None:
                raise ActionRefused("not_applicable", reason)

    async def _targets(
        self, node_ids: Sequence[str | None]
    ) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused(
                "not_applicable", say("A relation may be dropped only once")
            )
        return [await self._target(node_id) for node_id in node_ids]

    async def _target(self, node_id: str | None) -> tuple[str, TableNode | ViewNode]:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a relation to drop"))
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, TableNode | ViewNode) or node.is_system:
            raise ActionRefused("not_applicable", say("This relation cannot be dropped"))
        await _guard_relation_action(self._catalog, path[0].name, node)
        return path[0].name, node

    @staticmethod
    def _statements(
        targets: Sequence[tuple[str, TableNode | ViewNode]], *, cascade: bool
    ) -> list[str]:
        """One statement per kind of relation, naming every target of that kind.

        Composed from the catalog's description rather than from a guess: a
        materialized view is not dropped by DROP VIEW, and PostgreSQL says so
        with an error that names neither. Grouping rather than one statement
        each is what lets a table and the view over it go together: everything
        named in one DROP is already gone when the server checks what depends
        on the rest of it.
        """
        by_kind: dict[str, list[sql.Composable]] = {}
        for schema, node in targets:
            by_kind.setdefault(_kind_of(node), []).append(
                sql.Identifier(schema, node.name)
            )
        statements: list[str] = []
        for kind, command in DROP_COMMANDS:
            named = by_kind.get(kind)
            if not named:
                continue
            statement = sql.SQL("{} {}").format(command, sql.SQL(", ").join(named))
            if cascade:
                statement += sql.SQL(" CASCADE")
            statements.append(statement.as_string())
        return statements


def _kind_of(node: TableNode | ViewNode) -> str:
    if isinstance(node, TableNode):
        return "table"
    return "materialized view" if node.is_materialized else "view"


def _one_name(targets: Sequence[tuple[str, TableNode | ViewNode]]) -> str | None:
    """The name a message about this drop is about, or None when it counts.

    One relation is called by its name, because that is what the person is
    looking at. Several are counted: five names in a toast is a list nobody
    reads, and the catalog is about to show which ones went.
    """
    if len(targets) == 1:
        return targets[0][1].name
    return None


DROP_SCHEMA_REFUSALS = {
    # dependent_objects_still_exist.
    "2BP01": N_("The schema is not empty"),
    # lock_not_available.
    "55P03": N_("Something is using this schema; try again in a moment"),
    # insufficient_privilege.
    "42501": N_("This connection may not drop that schema"),
}


class DropSchemaParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything in it"),
        description=N_("Required when the schema still contains objects"),
    )


class DropSchema(JsonAction[DropSchemaParams]):
    """Drop one user schema after rehearsing PostgreSQL's exact statement."""

    name: ClassVar[str] = "drop_schema"
    title: ClassVar[str] = N_("Drop schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: DropSchemaParams
    ) -> ActionResult:
        node = await _schema_target(
            self._catalog,
            node_id,
            choose=say("Choose a schema to drop"),
            refused=say("This schema cannot be dropped"),
        )
        await self._guard_cascade(node.name, cascade=params.cascade)
        await self._session.schema_change(
            self._statement(node.name, cascade=params.cascade),
            refusals=DROP_SCHEMA_REFUSALS,
        )
        return ActionResult(
            message=say("Schema {name} dropped", name=node.name),
            reload_node_ids=[None, node.name],
        )

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        node = await _schema_target(
            self._catalog,
            node_id,
            choose=say("Choose a schema to drop"),
            refused=say("This schema cannot be dropped"),
        )
        await self._guard_cascade(node.name, cascade=params.cascade)
        rehearsal = await self._session.rehearse(
            self._statement(node.name, cascade=params.cascade),
            refusals=DROP_SCHEMA_REFUSALS,
        )
        if rehearsal.refused is not None:
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        if not rehearsal.said:
            return ActionPreview(summary=say("Schema {name} is empty", name=node.name))
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=rehearsal.said,
        )

    async def _guard_cascade(self, schema: str, *, cascade: bool) -> None:
        if cascade:
            reason = await self._catalog.cascade_reason(schema)
            if reason is not None:
                raise ActionRefused("not_applicable", reason)

    @staticmethod
    def _statement(schema: str, *, cascade: bool) -> str:
        statement = sql.SQL("DROP SCHEMA {}").format(sql.Identifier(schema))
        if cascade:
            statement += sql.SQL(" CASCADE")
        return statement.as_string()


class DescribeModelParams(BaseModel):
    # A screen of its own rather than a form: the answer is a document, and
    # what somebody does with it — read it, copy it, take it to a website —
    # is not a thing a generic form has anywhere to put (D73).
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "model-as-code"}
    )

    dialect: CodeDialect = Field(
        default="dbml",
        title=N_("Written as"),
        description=N_("What the file is for: an ORM, or a diagram"),
        # The names are the source's, so the three buttons say what a person
        # recognises rather than the value behind them.
        json_schema_extra={
            "x-ui-choices": [
                {"value": dialect, "label": title}
                for dialect, title in DIALECT_TITLE.items()
            ]
        },
    )


class DescribeModel(Action[DescribeModelParams]):
    """Write the model of what was selected as code, and hand it over.

    A download rather than a view, because what comes out is meant to be
    taken somewhere else: pasted into dbdiagram.io, or dropped into a
    project. The bytes are produced from the model the source already
    publishes (D22), so nothing here reads the catalog a second time.

    Offered on a schema as well as on a relation, and that is the useful
    case: a diagram of one table is a rectangle, while a diagram of a schema
    is the thing people draw.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"schema", "table", "view"}
    )
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._relation = PostgresRelation(session)
        self._catalog = catalog

    async def download(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionDownload:
        params = self._validated(raw)
        models = await self._models(node_ids)
        if not models:
            raise ActionRefused(
                "not_applicable", say("There is nothing here to describe")
            )
        try:
            text = render(models, params.dialect)
        except ValueError as exc:
            raise ActionRefused("too_large", str(exc)) from None
        body = text.encode("utf-8")
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=_model_filename(node_ids, params.dialect),
                media_type="text/plain; charset=utf-8",
                size_bytes=len(body),
            ),
            body=_one_chunk(body),
        )

    async def _models(self, node_ids: Sequence[str]) -> list[RelationModel]:
        """Every relation the selection names, each described once.

        A schema stands for its contents, which is what makes selecting one
        the way to draw a whole database; a relation stands for itself.
        """
        gathered: dict[str, RelationModel] = {}
        for node_id in node_ids:
            path = await self._catalog.path_to(node_id)
            node = path[-1]
            if isinstance(node, SchemaNode):
                reason = await self._catalog.schema_action_reason(node.name)
                if reason is not None:
                    raise ActionRefused("not_applicable", reason)
                for model in await self._relation.relation_models(node.name):
                    gathered.setdefault(model.node_id, model)
                continue
            if not isinstance(node, TableNode | ViewNode):
                raise ActionRefused(
                    "not_applicable",
                    say("{name} has no model to write out", name=node.name),
                )
            await _guard_relation_action(self._catalog, path[0].name, node)
            model = await self._relation.relation_model(node_id)
            gathered.setdefault(model.node_id, model)
        return list(gathered.values())


def _model_filename(node_ids: Sequence[str], dialect: CodeDialect) -> str:
    """What the file is called: after the one thing selected, or "model"."""
    suffix = DIALECT_SUFFIX[dialect]
    if len(node_ids) == 1:
        stem = node_ids[0].replace(".", "_")
        return f"{stem}{suffix}"
    return f"model{suffix}"


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class PostgresActionType(ActionType, Protocol):
    def __call__(
        self, session: PostgresSession, catalog: PostgresCatalog
    ) -> Action[Any]: ...


POSTGRES_ACTION_TYPES: tuple[PostgresActionType, ...] = (
    CreateSchema,
    RenameSchema,
    RenameRelation,
    MoveRelation,
    LoadCsv,
    CreateTable,
    DropRelation,
    DropSchema,
    CreateRole,
    DescribeModel,
    *TABLESPACE_ACTION_TYPES,
)

# Which report admits which commands. `applies_to` speaks about kinds, and
# every report is a report: one of them is about extensions and another about
# roles, and neither offers the other's commands. A table rather than a chain
# of comparisons, so that a report gaining a command is an entry here.
REPORT_COMMANDS: dict[str, tuple[str, ...]] = {
    ROLES_REPORT_ID: (CreateRole.name,),
    TABLESPACES_REPORT_ID: tuple(kind.name for kind in TABLESPACE_ACTION_TYPES),
}


class PostgresActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._catalog = catalog
        self._relations = PostgresRelationChanges(session, catalog)
        self._timescale = TimescaleActions(session, catalog)
        self._actions = ActionSet(
            [action_type(session, catalog) for action_type in POSTGRES_ACTION_TYPES]
        )
        self._registered = ActionSet([*self._actions, *self._timescale.registered])

    def action(self, name: str) -> Action[Any]:
        return self._registered.get(name)

    async def hypertable_design_state(self, node_id: str) -> HypertableDesignState:
        return await self._timescale.design.state(node_id)

    async def all_actions(self) -> list[Action[Any]]:
        return [*self._actions, *(await self._timescale.all_actions())]

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return list((await self.action_offers(node_id)).actions)

    def _offers(
        self,
        actions: Sequence[Action[Any]],
        reason: str | None = None,
        refused: Sequence[Action[Any]] = (),
    ) -> ActionOffers:
        return ActionOffers(
            actions=actions,
            refusals=(
                tuple(
                    ActionUnavailability(name=action.name, reason=reason)
                    for action in refused
                )
                if reason is not None else ()
            ),
        )

    async def action_offers(self, node_id: str | None) -> ActionOffers:
        if node_id is None:
            return ActionOffers([self._actions.get(CreateSchema.name)])
        path = await self._catalog.path_to(node_id)
        ordinary = await self._ordinary_offers(node_id, path)
        extension = await self._timescale.offers(path)
        return ActionOffers(
            [*ordinary.actions, *extension.actions],
            (*ordinary.refusals, *extension.refusals),
        )

    async def _ordinary_offers(self, node_id: str, path: list[CatalogNode]) -> ActionOffers:
        node = path[-1]
        if isinstance(node, SchemaNode):
            # Whether a schema will take a new relation is the schema's own
            # answer, asked here so that the rule is not stated a second time.
            options = await self._relations.new_relation_options(node_id)
            if not options.supported:
                return self._offers([], options.reason, self._actions.for_kind(node.kind))
            actions = self._actions.for_kind(node.kind)
            reason = await self._catalog.schema_action_reason(node.name)
            if reason is not None:
                member_actions = {RenameSchema.name, DropSchema.name, DescribeModel.name}
                return self._offers(
                    [action for action in actions if action.name not in member_actions],
                    reason, [action for action in actions if action.name in member_actions],
                )
            reason = await self._catalog.cascade_reason(node.name)
            if reason is not None:
                schema_mutations = {RenameSchema.name, DropSchema.name}
                return self._offers(
                    [action for action in actions if action.name not in schema_mutations],
                    reason, [action for action in actions if action.name in schema_mutations],
                )
            return ActionOffers(actions)
        if isinstance(node, (TableNode, ViewNode)) and not node.is_system:
            reason = await self._catalog.relation_action_reason(path[0].name, node.name)
            if reason is not None:
                return self._offers([], reason, self._actions.for_kind(node.kind))
            return ActionOffers(self._actions.for_kind(node.kind))
        # A report admits a command when the command is about what it reports,
        # which is a question of state and so is answered here rather than by
        # `applies_to`.
        if isinstance(node, ReportNode):
            return ActionOffers([
                self._actions.get(name) for name in REPORT_COMMANDS.get(node_id, ())
            ])
        return ActionOffers([])
