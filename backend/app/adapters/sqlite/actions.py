"""What a SQLite source can be asked to do from its catalog (D9, D258).

PostgreSQL's catalog actions where a file has the thing they act on: one schema
(D248) means no schema is made, renamed, dropped or moved into. SQLite's
structure changes are transactional (D253), so a drop is rehearsed — carried
out and rolled back — and its preview is SQLite's own answer.
"""

import sqlite3
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionDownload,
    ActionDownloadMetadata,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    FileAction,
    FilePayload,
    JsonAction,
    NodeReplacement,
)
from app.adapters.catalog import NodeKind, ReportNode, SchemaNode, TableNode, ViewNode
from app.adapters.csv_load import LoadCsvParams as SharedLoadCsvParams
from app.adapters.csv_load import chosen_rows, read_upload, table_name
from app.adapters.model_code import DIALECT_SUFFIX, DIALECT_TITLE, CodeDialect, render
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.definition import name_of, tokenize
from app.adapters.sqlite.design import NAME_LIMIT, SqliteTableDesign
from app.adapters.sqlite.inspection import SCHEMA, read_relation
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.relation_changes import SqliteRelationChanges
from app.adapters.sqlite.restructure import check_views, edited
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.sqlite.sql import SQL, Identifier, quoted_name
from app.adapters.sqlite.update import DELETING
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say

_TRIGGERS = "SELECT name FROM sqlite_schema WHERE type = 'trigger' AND tbl_name = ? ORDER BY name"
_VIEWS = "SELECT name, sql FROM sqlite_schema WHERE type = 'view' ORDER BY name"
_VIEW_TEXT = "SELECT sql FROM sqlite_schema WHERE type = 'view' AND name = ?"
_ARRIVING = """
SELECT m.name AS source, k."table" AS target
FROM sqlite_schema AS m, pragma_foreign_key_list(m.name, 'main') AS k
WHERE m.type = 'table'
GROUP BY m.name, k.id
"""


def _name(value: str) -> str:
    """A relation name SQLite will keep as given, and not one of its own."""
    if value == "" or value != value.strip() or len(value) > NAME_LIMIT:
        raise ValueError(
            say(
                "A SQLite name is 1 to {limit} characters and does not start or end with spaces",
                limit=NAME_LIMIT,
            )
        )
    if value.lower().startswith("sqlite_"):
        raise ValueError(say('A name starting "sqlite_" is SQLite\'s own'))
    return value


async def _relation_target(
    catalog: SqliteCatalog, node_id: str | None, refused: str
) -> TableNode | ViewNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a relation"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, TableNode | ViewNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return node


def _reads(sql: str, table: str) -> bool:
    """Whether a view's text names the table, as a name rather than a string.

    By its tokens, so a string or a comment holding the name is not a reader.
    A column of the same name is taken for the table: the line in the preview
    then names a view that may not stop working, which is the safer mistake.
    """
    return any(
        token.kind in ("word", "name") and name_of(token, sql).lower() == table.lower()
        for token in tokenize(sql)
    )


class RenameRelationParams(BaseModel):
    new_name: str = Field(title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"})

    _check = field_validator("new_name")(_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    """Rename a table, or a view.

    A table is SQLite's ALTER TABLE, which rewrites what refers to it — keys,
    views, triggers. A view has no rename: it is made again under the new
    name from its own text, and every view is read afterwards, so one that
    read it by its old name refuses the rename.
    """

    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = N_("Rename")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = RenameRelationParams

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: RenameRelationParams) -> ActionResult:
        node = await _relation_target(self._catalog, node_id, say("This relation cannot be renamed"))
        new_name = params.new_name
        if new_name == node.name:
            raise ActionRefused("conflict", say("The relation already has that name"))
        siblings = await self._catalog.list_children(SCHEMA)
        if new_name.lower() in {sibling.name.lower() for sibling in siblings} and (
            new_name.lower() != node.name.lower()
        ):
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=SCHEMA, name=new_name),
            )

        def table(connection: sqlite3.Connection) -> None:
            connection.execute(
                SQL("ALTER TABLE {} RENAME TO {}")
                .format(Identifier(SCHEMA, node.name), Identifier(new_name))
                .text()
            )

        def view(connection: sqlite3.Connection) -> None:
            text = str(connection.execute(_VIEW_TEXT, (node.name,)).fetchone()[0])
            tokens = tokenize(text)
            # CREATE [TEMP] VIEW [IF NOT EXISTS] name — the first name after VIEW.
            at = next(index for index, token in enumerate(tokens) if token.is_word("VIEW")) + 1
            while tokens[at].is_word("IF", "NOT", "EXISTS"):
                at += 1
            end = at
            if at + 2 < len(tokens) and tokens[at + 1].value == ".":
                end = at + 2
            renamed = edited(text, [((tokens[at].start, tokens[end].end), quoted_name(new_name))])
            connection.execute(SQL("DROP VIEW {}").format(Identifier(SCHEMA, node.name)).text())
            connection.execute(renamed)
            check_views(connection)

        try:
            await self._session.restructure(table if isinstance(node, TableNode) else view)
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        return ActionResult(
            message=say("Renamed to {name}", name=new_name),
            reload_node_ids=[SCHEMA],
            replacement=NodeReplacement(
                old_node_id=node.id, new_node_id=ids.relation_id(new_name), title=new_name
            ),
        )


class DropRelationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Rehearsed(Exception):
    """A drop carried out to be described, and rolled back by raising this."""


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations together, after a rehearsal said what that does.

    With foreign keys on, dropping a table deletes its rows first, and the keys
    pointing at it act as on any delete: a cascade follows, a refusal refuses.
    So the rehearsal is the drop itself, rolled back, and what it could not do
    blocks the real one. Tables of the selection that point at others in it go
    first.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropRelationParams) -> ActionResult:
        return await self._drop([node_id])

    async def perform_on_set(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionResult:
        self._validated(raw)
        return await self._drop(list(node_ids))

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets([node_id]))

    async def preview_on_set(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets(list(node_ids)))

    async def _targets(self, node_ids: Sequence[str | None]) -> list[TableNode | ViewNode]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused("not_applicable", say("A relation may be dropped only once"))
        return [
            await _relation_target(self._catalog, node_id, say("This relation cannot be dropped"))
            for node_id in node_ids
        ]

    def _carry_out(self, connection: sqlite3.Connection, targets: Sequence[TableNode | ViewNode]) -> None:
        views = [node.name for node in targets if isinstance(node, ViewNode)]
        tables = _children_first(connection, [node.name for node in targets if isinstance(node, TableNode)])
        for view in views:
            connection.execute(SQL("DROP VIEW {}").format(Identifier(SCHEMA, view)).text())
        for table in tables:
            connection.execute(SQL("DROP TABLE {}").format(Identifier(SCHEMA, table)).text())

    async def _drop(self, node_ids: Sequence[str | None]) -> ActionResult:
        targets = await self._targets(node_ids)
        try:
            await self._session.write(lambda connection: self._carry_out(connection, targets), refusals=DELETING)
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        name = _one_name(targets)
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[SCHEMA],
        )

    async def _preview(self, targets: Sequence[TableNode | ViewNode]) -> ActionPreview:
        name = _one_name(targets)
        names = {node.name.lower() for node in targets}

        def consequences(reading: Reading) -> list[str]:
            items: list[str] = []
            for node in targets:
                if isinstance(node, TableNode):
                    items += [
                        say("Trigger {name} goes with it", name=row[0])
                        for row in reading.tuples(_TRIGGERS, (node.name,))
                    ]
            for row in reading.tuples(_ARRIVING):
                source, target = str(row[0]), str(row[1])
                if target.lower() in names and source.lower() not in names:
                    facts = read_relation(reading, source, structure=False)
                    for key in facts.foreign_keys if facts is not None else []:
                        if (key.target_table or "").lower() == target.lower():
                            items.append(
                                say(
                                    "{table} refers to {target} through {key}",
                                    table=source,
                                    target=target,
                                    key=key.name,
                                )
                            )
            for view, sql in reading.tuples(_VIEWS):
                if str(view).lower() in names:
                    continue
                for node in targets:
                    if _reads(str(sql), node.name):
                        items.append(
                            say("View {view} reads {name} and will stop working", view=view, name=node.name)
                        )
            return items

        items = await self._session.inspection(consequences)

        def rehearse(connection: sqlite3.Connection) -> None:
            self._carry_out(connection, targets)
            raise _Rehearsed

        try:
            await self._session.write(rehearse, refusals=DELETING)
        except _Rehearsed:
            pass
        except ValueError as refused:
            return ActionPreview(summary=str(refused), items=items, blocked=True)
        if not items:
            return ActionPreview(
                summary=(
                    say("Nothing else depends on {name}", name=name)
                    if name is not None
                    else say("Nothing else depends on {count} relations", count=len(targets))
                )
            )
        return ActionPreview(
            summary=(
                say("What dropping {name} would do:", name=name)
                if name is not None
                else say("What dropping {count} relations would do:", count=len(targets))
            ),
            items=items,
        )


def _children_first(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    """The tables in an order where one pointing at another of them goes first.

    Dropping a table deletes its rows, and a key of a table still there that
    points at them would refuse it; a table already dropped points at nothing.
    """
    chosen = {table.lower(): table for table in tables}
    points_at: dict[str, set[str]] = {table.lower(): set() for table in tables}
    for source, target in connection.execute(_ARRIVING).fetchall():
        if str(source).lower() in chosen and str(target).lower() in chosen and source != target:
            points_at[str(source).lower()].add(str(target).lower())
    ordered: list[str] = []
    while points_at:
        # A table no remaining one points at can go last; a cycle goes as it is.
        pointed = {target for targets in points_at.values() for target in targets}
        ready = [table for table in points_at if table not in pointed] or list(points_at)
        for table in sorted(ready):
            ordered.append(chosen[table])
            points_at.pop(table)
    return ordered


def _one_name(targets: Sequence[TableNode | ViewNode]) -> str | None:
    """One relation is called by its name; several are counted."""
    return targets[0].name if len(targets) == 1 else None


class LoadCsvParams(SharedLoadCsvParams):
    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else _name(value)


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a table of `main`.

    Every column is TEXT: a file states no types, and one read off its rows
    would depend on how many were looked at.
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._catalog = catalog
        self._relations = SqliteRelationChanges(session, catalog)

    async def run(self, node_id: str | None, params: LoadCsvParams, payload: FilePayload) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a schema to load into"))
        if params.create_schema or params.schema_name not in ("", SCHEMA):
            raise ActionRefused("not_applicable", say("A SQLite file has one schema, main"))
        name = table_name(params, payload, _name)
        siblings = await self._catalog.list_children(SCHEMA)
        if name.lower() in {sibling.name.lower() for sibling in siblings}:
            raise ActionRefused("conflict", say("{name} is already there", name=name))
        targets, rows = chosen_rows(await read_upload(payload), params, _name)
        try:
            result = await self._relations.create_relation(
                CreateRelationRequest(
                    parent_node_id=SCHEMA,
                    name=name,
                    columns=[NewColumn(name=target, type_code="text") for target in targets],
                    rows=rows,
                )
            )
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        if not isinstance(result, RelationCreated):
            cell = result.cells[0]
            raise ActionRefused(
                "not_applicable",
                say("Row {row}, column {column}: that value cannot be read", row=cell.row + 1, column=cell.column),
            )
        return ActionResult(
            message=say("{name} created with {count} rows", name=name, count=result.inserted),
            reload_node_ids=[SCHEMA],
            created_node_id=result.node.id,
        )


class CreateTableParams(BaseModel):
    # The designer is registered against this workflow, as PostgreSQL's is.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"})

    definition: TableDefinition
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table, review its statements, then create it (D117, D256)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._design = SqliteTableDesign(session, catalog, SqliteRelation(session))

    async def run(self, node_id: str | None, params: CreateTableParams) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a schema to create it in"))
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


class DescribeModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "model-as-code"})

    dialect: CodeDialect = Field(
        default="dbml",
        title=N_("Written as"),
        description=N_("What the file is for: an ORM, or a diagram"),
        json_schema_extra={
            "x-ui-choices": [{"value": dialect, "label": title} for dialect, title in DIALECT_TITLE.items()]
        },
    )


class DescribeModel(Action[DescribeModelParams]):
    """The model of what was selected, written as code and handed over (D73).

    `main` stands for its tables and views, which is what makes selecting it
    the way to draw the file.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema", "table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._relation = SqliteRelation(session)
        self._catalog = catalog

    async def download(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionDownload:
        params = self._validated(raw)
        models = await self._models(node_ids)
        if not models:
            raise ActionRefused("not_applicable", say("There is nothing here to describe"))
        try:
            text = render(models, params.dialect)
        except ValueError as exc:
            raise ActionRefused("too_large", str(exc)) from None
        body = text.encode("utf-8")
        stem = (ids.parse(node_ids[0])[1] or ids.parse(node_ids[0])[0]) if len(node_ids) == 1 else "model"
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=f"{stem}{DIALECT_SUFFIX[params.dialect]}",
                media_type="text/plain; charset=utf-8",
                size_bytes=len(body),
            ),
            body=_one_chunk(body),
        )

    async def _models(self, node_ids: Sequence[str]) -> list[RelationModel]:
        gathered: dict[str, RelationModel] = {}
        for node_id in node_ids:
            node = (await self._catalog.path_to(node_id))[-1]
            if isinstance(node, SchemaNode):
                relations = [
                    child.id
                    for child in await self._catalog.list_children(node_id)
                    if isinstance(child, TableNode | ViewNode) and not child.is_system
                ]
            elif isinstance(node, TableNode | ViewNode):
                relations = [node.id]
            else:
                raise ActionRefused("not_applicable", say("{name} has no model to write out", name=node.name))
            for relation_id in relations:
                if relation_id not in gathered:
                    gathered[relation_id] = await self._relation.relation_model(relation_id)
        return list(gathered.values())


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class SqliteActionType(ActionType, Protocol):
    def __call__(self, session: SqliteSession, catalog: SqliteCatalog) -> Action[Any]: ...


SQLITE_ACTION_TYPES: tuple[SqliteActionType, ...] = (
    RenameRelation,
    LoadCsv,
    CreateTable,
    DropRelation,
    DescribeModel,
)


class SqliteActions:
    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in SQLITE_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return []
        node = (await self._catalog.path_to(node_id))[-1]
        # SQLite's own tables are read and never changed; their model may
        # still be written out. A report changes nothing.
        if isinstance(node, ReportNode):
            return []
        if isinstance(node, TableNode | ViewNode) and node.is_system:
            return [self._actions.get(DescribeModel.name)]
        return self._actions.for_kind(node.kind)
