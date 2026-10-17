"""Making, renaming, handing over and removing a tablespace (D210).

A tablespace is the server's, not the database's: it names a directory on the
machine PostgreSQL runs on, and objects of every database may be stored in it.
So everything here asks for `own`, as making a role does (D79).

DataPlayer never touches that directory. It cannot list it, create it or give
it to the right operating-system user; the person names a path, the preview
says what the server needs of it, and the server's refusal is reduced to a
sentence. No statement is composed from a client's text: names reach a
statement through `sql.Identifier`, the location through `sql.Literal`, and
the tablespace a row names is the server's own spelling, read back first.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from psycopg import sql
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActsOn,
    FieldChoice,
    FieldHints,
    JsonAction,
    OfferedIn,
)
from app.adapters.catalog import NodeKind
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.names import name_check
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import TABLESPACES_REPORT_ID
from app.adapters.row_commands import (
    PickedRowsAction,
    PickedRowsTarget,
    RowCommand,
    RowCommandCondition,
    RowCommandResult,
)
from app.core.access import Access
from app.core.translation import N_, say

# The column of the Tablespaces report that names one, and the one saying it
# is pg_default or pg_global, which nothing here renames, hands over or drops.
NAME_COLUMN = "name"
BUILT_IN_COLUMN = "built_in"
NOT_BUILT_IN = "false"
# PostgreSQL keeps this prefix for its own tablespaces, and refuses one with 42939.
RESERVED_PREFIX = "pg_"
# How many tablespaces one Remove may name; each is a statement of its own.
MAX_REMOVED = 20

TABLESPACE_REFUSALS: Mapping[str, str] = {
    # insufficient_privilege: CREATE TABLESPACE takes a superuser, and the
    # server answers the same code when it may not write to the directory.
    "42501": N_("This connection may not do that here, or PostgreSQL may not write to that directory"),
    "42710": N_("A tablespace with that name already exists"),
    "42939": N_("Names beginning with pg_ are reserved by PostgreSQL"),
    # undefined_file: the directory is not there.
    "58P01": N_("There is no such directory on the database server"),
    # object_not_in_prerequisite_state: in use already, or not empty.
    "55000": N_("That directory is not empty or is already used by a tablespace"),
    # invalid_object_definition: not absolute, or too long.
    "42P17": N_("The location must be an absolute path on the database server"),
    # undefined_object: the tablespace, or the role named as owner, went
    # after the form was filled.
    "42704": N_("That tablespace or role does not exist any more"),
}
_NOT_EMPTY = N_("Something is still stored in it, in this database or another; move it out first")
_DROP_REFUSALS: Mapping[str, str] = {**TABLESPACE_REFUSALS, "55000": _NOT_EMPTY}

_ROLES = """
SELECT rolname AS name FROM pg_catalog.pg_roles WHERE rolname !~ '^pg_' ORDER BY 1
"""
_TABLESPACE = """
SELECT spcname AS name FROM pg_catalog.pg_tablespace
WHERE spcname = %s AND spcname NOT IN ('pg_default', 'pg_global')
"""


def _not_reserved(value: str) -> str:
    if value.lower().startswith(RESERVED_PREFIX):
        raise ValueError(
            say('Names beginning with "{prefix}" are reserved by PostgreSQL', prefix=RESERVED_PREFIX)
        )
    return value


def _blank_is_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


class CreateTablespaceParams(BaseModel):
    name: str = Field(title=N_("Name"))
    location: str = Field(
        title=N_("Location"), min_length=1, max_length=1024,
        description=N_(
            "An absolute path on the database server. The directory must exist, be empty and "
            "belong to the operating-system user PostgreSQL runs as"
        ),
        examples=["/var/lib/postgresql/fast"],
    )
    owner: str | None = Field(
        default=None, title=N_("Owner"), description=N_("Leave empty to own it yourself")
    )

    _check = field_validator("name")(name_check("tablespace"))
    _reserved = field_validator("name")(_not_reserved)
    _owner_blank = field_validator("owner", mode="before")(_blank_is_none)


class RenameTablespaceParams(BaseModel):
    tablespace: str = Field(min_length=1, json_schema_extra={"x-ui-hidden": True})
    new_name: str = Field(title=N_("New name"))

    _check = field_validator("new_name")(name_check("tablespace"))
    _reserved = field_validator("new_name")(_not_reserved)


class TablespaceOwnerParams(BaseModel):
    tablespace: str = Field(min_length=1, json_schema_extra={"x-ui-hidden": True})
    owner: str = Field(min_length=1, title=N_("Owner"))


class _TablespaceAction[P: BaseModel](JsonAction[P]):
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"report"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "own"
    bulk: ClassVar[bool] = False

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session

    def _here(self, node_id: str | None) -> None:
        if node_id != TABLESPACES_REPORT_ID:
            raise ActionRefused(
                "not_applicable", say("Tablespaces are changed from the Tablespaces report")
            )

    async def _named(self, typed: str) -> str:
        """The server's own spelling of a tablespace that is not built in."""
        rows = await self._session.query(_TABLESPACE, (typed,))
        if not rows:
            raise ActionRefused(
                "not_applicable",
                say('There is no tablespace "{name}" that can be changed', name=typed),
            )
        return str(rows[0]["name"])

    async def field_hints(self, node_id: str | None) -> FieldHints:
        roles = [str(row["name"]) for row in await self._session.query(_ROLES)]
        return FieldHints(choices={"owner": [FieldChoice(value=role, label=role) for role in roles]})


class CreateTablespace(_TablespaceAction[CreateTablespaceParams]):
    """CREATE TABLESPACE, sent with no transaction, which it refuses."""

    name: ClassVar[str] = "create_tablespace"
    title: ClassVar[str] = N_("New tablespace")
    # Above the list of tablespaces, like New role over the list of roles (D79).
    offered_in: ClassVar[OfferedIn] = "rows"
    icon: ClassVar[str] = "create_new_folder"
    params_model = CreateTablespaceParams

    async def field_hints(self, node_id: str | None) -> FieldHints:
        hints = await super().field_hints(node_id)
        return FieldHints(choices={"owner": [FieldChoice(value="", label=say("You")), *hints.choices["owner"]]})

    async def run(self, node_id: str | None, params: CreateTablespaceParams) -> ActionResult:
        self._here(node_id)
        statement = sql.SQL("CREATE TABLESPACE {}{} LOCATION {}").format(
            sql.Identifier(params.name),
            sql.SQL("") if params.owner is None else sql.SQL(" OWNER {}").format(sql.Identifier(params.owner)),
            sql.Literal(params.location),
        )
        await self._refused_as_said(statement)
        return ActionResult(
            message=say(
                "Tablespace {name} created at {location}",
                name=params.name,
                location=params.location,
            ),
            reload_node_ids=[],
        )

    async def _refused_as_said(self, statement: sql.Composed) -> None:
        try:
            await self._session.schema_change(statement.as_string(), refusals=TABLESPACE_REFUSALS, alone=True)
        except ValueError as refusal:
            raise ActionRefused("not_applicable", str(refusal)) from None


class RenameTablespace(_TablespaceAction[RenameTablespaceParams]):
    name: ClassVar[str] = "rename_tablespace"
    title: ClassVar[str] = N_("Rename tablespace")
    offered_in: ClassVar[OfferedIn] = "picked"
    icon: ClassVar[str] = "edit"
    params_model = RenameTablespaceParams

    async def run(self, node_id: str | None, params: RenameTablespaceParams) -> ActionResult:
        self._here(node_id)
        named = await self._named(params.tablespace)
        try:
            await self._session.schema_change(
                sql.SQL("ALTER TABLESPACE {} RENAME TO {}").format(
                    sql.Identifier(named), sql.Identifier(params.new_name),
                ).as_string(),
                refusals=TABLESPACE_REFUSALS,
            )
        except ValueError as refusal:
            raise ActionRefused("not_applicable", str(refusal)) from None
        return ActionResult(
            message=say(
                "Tablespace {name} renamed to {new_name}", name=named, new_name=params.new_name
            ),
            reload_node_ids=[],
        )


class ChangeTablespaceOwner(_TablespaceAction[TablespaceOwnerParams]):
    name: ClassVar[str] = "change_tablespace_owner"
    title: ClassVar[str] = N_("Change tablespace owner")
    offered_in: ClassVar[OfferedIn] = "picked"
    icon: ClassVar[str] = "manage_accounts"
    params_model = TablespaceOwnerParams

    async def run(self, node_id: str | None, params: TablespaceOwnerParams) -> ActionResult:
        self._here(node_id)
        named = await self._named(params.tablespace)
        try:
            await self._session.schema_change(
                sql.SQL("ALTER TABLESPACE {} OWNER TO {}").format(
                    sql.Identifier(named), sql.Identifier(params.owner),
                ).as_string(),
                refusals=TABLESPACE_REFUSALS,
            )
        except ValueError as refusal:
            raise ActionRefused("not_applicable", str(refusal)) from None
        return ActionResult(
            message=say(
                "Tablespace {name} now belongs to {owner}", name=named, owner=params.owner
            ),
            reload_node_ids=[],
        )


TABLESPACE_ACTION_TYPES = (CreateTablespace, RenameTablespace, ChangeTablespaceOwner)

DROP_TABLESPACE = RowCommand(
    name="drop_tablespace",
    title=N_("Remove"),
    icon="delete",
    description=N_(
        "Remove this tablespace from the server. PostgreSQL refuses while anything, "
        "in any database, is still stored in it."
    ),
    destructive=True,
    requires="own",
    identified_by=NAME_COLUMN,
    applies_when=RowCommandCondition(column=BUILT_IN_COLUMN, equals=NOT_BUILT_IN),
)

PICKED: tuple[PickedRowsAction, ...] = tuple(
    PickedRowsAction(
        action=kind.name, title=kind.title, icon=kind.icon or "edit",
        requires=kind.requires, identified_by=[NAME_COLUMN],
    )
    for kind in (RenameTablespace, ChangeTablespaceOwner)
)


def picked_actions(node_id: str) -> list[PickedRowsAction]:
    if node_id != TABLESPACES_REPORT_ID:
        return []
    return [
        picked.model_copy(update={"title": f"{say(picked.title)}…"})
        for picked in PICKED
    ]


async def resolve_picked(
    session: PostgresSession, node_id: str, action: str, keys: Sequence[Sequence[str]],
) -> PickedRowsTarget:
    """One picked tablespace, set in the form of the action that changes it."""
    if node_id != TABLESPACES_REPORT_ID or action not in {offered.action for offered in PICKED}:
        raise ActionRefused("not_applicable", say("This is not offered over these rows"))
    if len(keys) != 1 or len(keys[0]) != 1:
        raise ActionRefused("not_applicable", say("Pick one tablespace"))
    rows = await session.query(_TABLESPACE, (keys[0][0],))
    if not rows:
        raise ActionRefused(
            "not_applicable",
            say("pg_default and pg_global are PostgreSQL's own and are left as they are"),
        )
    named = str(rows[0]["name"])
    return PickedRowsTarget(node_id=node_id, node_label=named, params={"tablespace": named})


async def drop(session: PostgresSession, keys: Sequence[str]) -> RowCommandResult:
    """Each named tablespace dropped on its own, each refusal said for its own name."""
    if len(keys) > MAX_REMOVED:
        raise ValueError(say("At most {count} tablespaces at a time", count=MAX_REMOVED))
    done: list[str] = []
    refused: list[str] = []
    for typed in keys:
        rows = await session.query(_TABLESPACE, (typed,))
        if not rows:
            refused.append(say('"{name}" is not a tablespace that can be removed', name=typed))
            continue
        named = str(rows[0]["name"])
        try:
            await session.schema_change(
                sql.SQL("DROP TABLESPACE {}").format(sql.Identifier(named)).as_string(),
                refusals=_DROP_REFUSALS, alone=True,
            )
        except ValueError as refusal:
            refused.append(f"{named}: {refusal}")
            continue
        done.append(named)
    count, asked = len(done), len(keys)
    if asked == 1:
        message = say("1 tablespace removed") if count == 1 else say("0 of 1 tablespace removed")
    elif count == asked:
        message = say("{count} tablespaces removed", count=count)
    else:
        message = say("{count} of {asked} tablespaces removed", count=count, asked=asked)
    return RowCommandResult(message=message, done=len(done), refused=refused)
