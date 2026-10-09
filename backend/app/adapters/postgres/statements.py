"""Where one statement ends and what kind of statement it is.

Pure: text in, prepared statements out, no connection anywhere. That is what
lets every awkward form — a semicolon inside a string, a comment or a
dollar-quoted function body, a writable CTE, `SELECT INTO` — be tested without
a database.

The dialect's own parser draws the boundaries and decides the class: pglast,
PostgreSQL's parser itself, so a statement the server accepts is one this
module can read. Other dialects keep their own modules rather than sharing
this one: what `BIT VARYING` means is a fact about PostgreSQL, not about
querying in general. Splitting on semicolons, reading the first word or
keeping a blacklist are not accepted substitutes (D62), and the reason is
visible here: `read` is granted only by a parse that produced a query and
nothing else, so a form this version has never seen is refused rather than
allowed by omission.
"""

import logging
import re
from typing import Any

from pglast import Error as PgError
from pglast import ast as pgast
from pglast import parse_sql
from pglast.enums import AlterTableType, ObjectType
from pglast.visitors import Visitor
from sqlglot import parse_one
from sqlglot.dialects.postgres import Postgres
from sqlglot.errors import ParseError, TokenError

# sqlglot re-exports these without naming them in __all__.
from sqlglot.tokens import Token, TokenType  # type: ignore[attr-defined]

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass

# sqlglot logs the statement it could not parse, at warning level. D64 keeps
# SQL out of application logs, so this logger is silenced here rather than
# left to whoever configures logging next.
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
logging.getLogger("sqlglot").propagate = False

_tokenizer = Postgres().tokenizer_class()

# What may follow a colon and be a parameter name.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Anything that writes, wherever it appears in the tree. A writable CTE parses
# as a query whose body holds one of these, which is exactly the form a first
# word would let through.
_WRITE_NODES = (
    pgast.InsertStmt,
    pgast.UpdateStmt,
    pgast.DeleteStmt,
    pgast.MergeStmt,
    pgast.CopyStmt,
)

# The shapes that change the structure, by node rather than by word. Most are
# refused with a sentence naming what they are; what the closed vocabulary
# admits is decided beside the parse, in `_subject_of`. A permission change is
# a change to the schema's rules, so it is DDL here and high risk below, while
# the allowlist of what may actually run is narrower.
_DDL_NODES = (
    pgast.CreateStmt,
    pgast.CreateTableAsStmt,
    pgast.CreateSchemaStmt,
    pgast.IndexStmt,
    pgast.ViewStmt,
    pgast.DropStmt,
    pgast.AlterTableStmt,
    pgast.TruncateStmt,
    pgast.CommentStmt,
    pgast.GrantStmt,
)

# What other `Create` and `Alter` shapes are about, in `_OUTSIDE`'s words.
# Whatever the engine adds tomorrow arrives as DDL and is refused with the
# general sentence rather than admitted by omission — except the two forms the
# application owns elsewhere: moving a relation into another schema, and
# renaming a schema, are catalog actions and stay `unknown` here.
_FOREIGN_SUBJECTS: dict[str, str] = {
    "CreatedbStmt": "DATABASE",
    "DropdbStmt": "DATABASE",
    "CreateSeqStmt": "SEQUENCE",
    "AlterSeqStmt": "SEQUENCE",
    "AlterEnumStmt": "TYPE",
    "AlterFunctionStmt": "FUNCTION",
    "CreateEnumStmt": "TYPE",
    "CreateTypeStmt": "TYPE",
    "CreateFunctionStmt": "FUNCTION",
    "CreateRoleStmt": "ROLE",
    "AlterRoleStmt": "ROLE",
    "DropRoleStmt": "ROLE",
    "CreateExtensionStmt": "EXTENSION",
    "AlterExtensionStmt": "EXTENSION",
    "CreateTrigStmt": "TRIGGER",
}

# What an object type of the engine is, in the same words. A materialized view
# answers as the view it is: creating and dropping one is admitted, so
# renaming and commenting one is too.
_OBJECT_SUBJECTS: dict[ObjectType, str] = {
    ObjectType.OBJECT_TABLE: "TABLE",
    ObjectType.OBJECT_VIEW: "VIEW",
    ObjectType.OBJECT_MATVIEW: "VIEW",
    ObjectType.OBJECT_INDEX: "INDEX",
    ObjectType.OBJECT_SCHEMA: "SCHEMA",
    ObjectType.OBJECT_COLUMN: "COLUMN",
    ObjectType.OBJECT_DATABASE: "DATABASE",
    ObjectType.OBJECT_ROLE: "ROLE",
    ObjectType.OBJECT_TABLESPACE: "TABLESPACE",
    ObjectType.OBJECT_EXTENSION: "EXTENSION",
    ObjectType.OBJECT_FUNCTION: "FUNCTION",
    ObjectType.OBJECT_PROCEDURE: "FUNCTION",
    ObjectType.OBJECT_TRIGGER: "TRIGGER",
    ObjectType.OBJECT_TYPE: "TYPE",
    ObjectType.OBJECT_SEQUENCE: "SEQUENCE",
}

_PERMISSIONS = "Permissions are not administered from the query editor"

# The closed vocabulary of structure changes this source will carry out (D66).
# Schemas, tables, views and indexes, their comments, and emptying a table.
#
# It is an allowlist because the alternative cannot be written down: a database
# accepts hundreds of statement forms, most of them administrative, and a list
# of the ones to keep out would be missing whichever one was invented last.
# What is not named here is refused with a sentence saying so.
_ALLOWED_KINDS = frozenset({"TABLE", "VIEW", "SCHEMA", "INDEX"})

# What a comment may be about. The same four, plus a column of one of them.
_ALLOWED_COMMENT_KINDS = frozenset({"TABLE", "VIEW", "SCHEMA", "INDEX", "COLUMN"})

# Why one family is outside the vocabulary, in words rather than a bare no.
# Each of these needs a permission model, a job or a screen this application
# has not designed, and a text box is not the place to invent one (D66).
_OUTSIDE = {
    "DATABASE": "Databases are not created or dropped from the query editor",
    "ROLE": "Roles and permissions are not administered from the query editor",
    "USER": "Roles and permissions are not administered from the query editor",
    "TABLESPACE": "Tablespaces are not managed from the query editor",
    "EXTENSION": "Extensions are not installed from the query editor",
    "FUNCTION": "Functions and procedures are not changed from the query editor",
    "PROCEDURE": "Functions and procedures are not changed from the query editor",
    "TRIGGER": "Triggers are not changed from the query editor",
    "TYPE": "Types are not changed from the query editor",
    "SEQUENCE": "Sequences are not changed from the query editor",
}

_GENERAL_REFUSAL = (
    "The query editor changes schemas, tables, views and indexes; "
    "this is something else"
)

# What an `ALTER TABLE` may do that is not a change to the relation itself.
# Ownership and row security are permission administration wearing an alter,
# refused the way a grant is; a tablespace, a trigger or a rule is a family of
# its own that happens to be switched from the table it belongs to.
_TRIGGERS = _OUTSIDE["TRIGGER"]
_ALTER_REFUSALS: dict[AlterTableType, str] = {
    AlterTableType.AT_ChangeOwner: _PERMISSIONS,
    AlterTableType.AT_EnableRowSecurity: _PERMISSIONS,
    AlterTableType.AT_DisableRowSecurity: _PERMISSIONS,
    AlterTableType.AT_ForceRowSecurity: _PERMISSIONS,
    AlterTableType.AT_NoForceRowSecurity: _PERMISSIONS,
    AlterTableType.AT_SetTableSpace: _OUTSIDE["TABLESPACE"],
    AlterTableType.AT_EnableTrig: _TRIGGERS,
    AlterTableType.AT_EnableAlwaysTrig: _TRIGGERS,
    AlterTableType.AT_EnableReplicaTrig: _TRIGGERS,
    AlterTableType.AT_DisableTrig: _TRIGGERS,
    AlterTableType.AT_EnableTrigAll: _TRIGGERS,
    AlterTableType.AT_DisableTrigAll: _TRIGGERS,
    AlterTableType.AT_EnableTrigUser: _TRIGGERS,
    AlterTableType.AT_DisableTrigUser: _TRIGGERS,
    AlterTableType.AT_EnableRule: _GENERAL_REFUSAL,
    AlterTableType.AT_EnableAlwaysRule: _GENERAL_REFUSAL,
    AlterTableType.AT_EnableReplicaRule: _GENERAL_REFUSAL,
    AlterTableType.AT_DisableRule: _GENERAL_REFUSAL,
    AlterTableType.AT_SetAccessMethod: _GENERAL_REFUSAL,
}


def split(text: str) -> list[tuple[int, int]]:
    """The range of every statement in this text, in order.

    Ranges rather than pieces: an error points into what the person wrote, and
    a run keeps the exact text it executed. Blank runs between semicolons are
    not statements and are left out.
    """
    try:
        found = parse_sql(_without_placeholders(text))
    except PgError:
        # The text does not parse as a whole, so its statements are still
        # found token by token: a script with one broken statement in it shows
        # the others for what they are, and the broken one is refused by name
        # rather than taking the diagnosis with it.
        return _token_ranges(text)
    ranges: list[tuple[int, int]] = []
    for raw in found:
        start = raw.stmt_location or 0
        span = raw.stmt_len or len(text) - start
        end = start + len(text[start : start + span].rstrip())
        if end > start:
            ranges.append((start, end))
    return ranges


def _token_ranges(text: str) -> list[tuple[int, int]]:
    """Where the statements sit, read off tokens rather than parsed.

    Only ever a fallback for a text the parser refused: a semicolon inside a
    string the tokenizer misreads would become a boundary, which is why a text
    that parses never comes here.
    """
    tokens = _tokenizer.tokenize(text)
    ranges: list[tuple[int, int]] = []
    first: Token | None = None
    last: Token | None = None
    for token in tokens:
        if token.token_type is TokenType.SEMICOLON:
            if first is not None and last is not None:
                ranges.append((first.start, last.end + 1))
            first = None
            last = None
            continue
        if first is None:
            first = token
        last = token
    if first is not None and last is not None:
        ranges.append((first.start, last.end + 1))
    return ranges


def _without_placeholders(text: str) -> str:
    """The same text with every `:name` read as the engine's own `$1`.

    Parameters are this application's own spelling, which the engine does not
    know. Padded to the same length, so every offset the parser reports still
    points into what the person wrote; the text that runs keeps every name it
    was written with.
    """
    for start, end, _name in reversed(_placeholders(text)):
        text = text[:start] + "$1".ljust(end - start) + text[end:]
    return text


def _parse_piece(text: str) -> pgast.Node | None:
    """The one statement this slice holds, or nothing.

    A slice holding anything but one statement is nothing too — that is a
    broken split, not a second shape, and answering `unknown` refuses it
    rather than guessing which of the two it is.
    """
    try:
        found = parse_sql(_without_placeholders(text))
    except PgError:
        return None
    if len(found) != 1:
        return None
    return found[0].stmt


class _Collected(Visitor):
    """Every node of one statement, in breadth-first order."""

    def __init__(self) -> None:
        self.nodes: list[Any] = []

    def visit(self, ancestors: Any, node: Any) -> None:
        self.nodes.append(node)


def _walk(node: pgast.Node) -> list[Any]:
    collected = _Collected()
    collected(node)
    return collected.nodes


def _writes(node: pgast.Node) -> bool:
    """Whether anything in this statement writes, wherever it sits."""
    return any(isinstance(one, _WRITE_NODES) for one in _walk(node))


def _classify(node: pgast.Node | None) -> StatementClass:
    """What kind of statement this is, or `unknown`.

    Read off the parse tree the server's own parser produced. Structure comes
    before writing, because a structure change may contain one:
    `CREATE TABLE t AS WITH x AS (INSERT ... RETURNING *) SELECT * FROM x`
    creates a relation, and reading the INSERT first would have called it a
    DML statement and let it run on `write` access alone. Whatever the parser
    has never seen stays `unknown` rather than becoming a read.
    """
    if node is None:
        return "unknown"
    if isinstance(node, pgast.SelectStmt):
        if _writes(node):
            return "dml"
        if getattr(node, "intoClause", None) is not None:
            # `SELECT ... INTO new_table` creates a relation, whatever a query
            # by itself would be allowed.
            return "ddl"
        return "read"
    if isinstance(node, (pgast.InsertStmt, pgast.UpdateStmt, pgast.DeleteStmt, pgast.MergeStmt)):
        return "dml"
    if isinstance(node, pgast.CopyStmt):
        return "copy"
    if isinstance(node, pgast.ExplainStmt):
        return "explain"
    if isinstance(node, pgast.TransactionStmt):
        return "transaction"
    if isinstance(
        node,
        (
            pgast.VariableSetStmt,
            pgast.VariableShowStmt,
            pgast.DiscardStmt,
            pgast.ListenStmt,
            pgast.UnlistenStmt,
            pgast.NotifyStmt,
            pgast.PrepareStmt,
            pgast.ExecuteStmt,
            pgast.DeallocateStmt,
        ),
    ):
        return "session"
    if isinstance(
        node,
        (
            pgast.VacuumStmt,
            pgast.ClusterStmt,
            pgast.ReindexStmt,
            pgast.RefreshMatViewStmt,
            pgast.CheckPointStmt,
        ),
    ):
        # Maintenance runs outside a transaction and with write access (D206).
        return "maintenance"
    if isinstance(node, _DDL_NODES):
        return "ddl"
    if isinstance(node, pgast.RenameStmt):
        # Renaming a schema, or moving a relation into one, belongs to the
        # catalog actions that own those subjects — the screen that renames
        # what it is looking at is not this text box.
        if _renamed_subject(node) in ("TABLE", "VIEW", "INDEX"):
            return "ddl"
        return "unknown"
    if type(node).__name__.startswith(("Create", "Alter", "Drop")):
        # Whatever shape of structure change the vocabulary names below; a
        # form named here is refused with a sentence rather than admitted by
        # omission, and only the two subjects the catalog owns stay unknown.
        # `AlterObjectSchemaStmt` — moving a relation — is one of them.
        if isinstance(node, pgast.AlterObjectSchemaStmt):
            return "unknown"
        return "ddl"
    return "unknown"


def _placeholders(text: str) -> list[tuple[int, int, str]]:
    """Where every `:name` is, and what it is called.

    Read from tokens, so `::` is a cast and not a parameter, and a colon
    inside a string or a comment is neither.
    """
    tokens = _tokenizer.tokenize(text)
    found: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens[:-1]):
        if token.token_type is not TokenType.COLON:
            continue
        following = tokens[index + 1]
        # Adjacent, or it is a colon that happens to precede an identifier.
        if following.start != token.end + 1:
            continue
        # By the text rather than by the token type: a parameter may be
        # called `name`, `text` or `user`, and the tokenizer reads each of
        # those as a keyword of its own. What makes it a parameter is the
        # colon before it and the shape of the word after it.
        if _IDENTIFIER.fullmatch(following.text) is None:
            continue
        found.append((token.start, following.end + 1, following.text))
    return found


def bind(text: str) -> str:
    """The same statement, with `:name` written the way the driver binds it.

    A rewriting of placeholders, not of values: what goes to the server is
    still `$1` with a value beside it, and nothing a user typed is put into
    the statement (D62).

    Every literal per-cent sign is doubled, because psycopg reads one as the
    start of a placeholder as soon as any parameter is supplied — which is how
    `LIKE 'a%b'` in a parameterised statement would otherwise fail.
    """
    pieces: list[str] = []
    cursor = 0
    for start, end, name in _placeholders(text):
        pieces.append(text[cursor:start].replace("%", "%%"))
        pieces.append(f"%({name})s")
        cursor = end
    pieces.append(text[cursor:].replace("%", "%%"))
    return "".join(pieces)


def _subject_of(node: pgast.Node) -> str:
    """What kind of thing this structure change is about, in `_OUTSIDE`'s words."""
    if isinstance(node, (pgast.CreateStmt, pgast.CreateTableAsStmt)):
        return "TABLE"
    if isinstance(node, pgast.CreateSchemaStmt):
        return "SCHEMA"
    if isinstance(node, pgast.IndexStmt):
        return "INDEX"
    if isinstance(node, pgast.ViewStmt):
        return "VIEW"
    if isinstance(node, pgast.AlterTableStmt):
        # The engine parses `ALTER TYPE`, `ALTER SEQUENCE` and `ALTER FOREIGN
        # TABLE` as this node too; what it alters is in `objtype`.
        return _object_subject(node.objtype)
    if isinstance(node, pgast.DropStmt):
        return _object_subject(node.removeType)
    if isinstance(node, pgast.CommentStmt):
        return _object_subject(node.objtype)
    if isinstance(node, pgast.RenameStmt):
        return _renamed_subject(node)
    return _FOREIGN_SUBJECTS.get(type(node).__name__, "")


def _renamed_subject(node: pgast.RenameStmt) -> str:
    """What a rename alters: a column or a constraint is part of its relation."""
    if node.renameType == ObjectType.OBJECT_TABCONSTRAINT:
        return "TABLE"
    if node.renameType in (ObjectType.OBJECT_COLUMN, ObjectType.OBJECT_ATTRIBUTE):
        return _object_subject(node.relationType)
    return _object_subject(node.renameType)


def _object_subject(value: ObjectType | None) -> str:
    """An object type of the engine in the same words, or nothing."""
    return "" if value is None else _OBJECT_SUBJECTS.get(value, "")


def _alter_refusal(node: pgast.AlterTableStmt) -> str | None:
    """Why one of this alter's actions is not a change to the relation."""
    for cmd in node.cmds or ():
        refused = _ALTER_REFUSALS.get(cmd.subtype)
        if refused is not None:
            return refused
    return None


def _refusal(node: pgast.Node | None, kind: StatementClass) -> str | None:
    """Why this source will not carry the statement out, if it will not.

    Only structure changes are answered here; every other class is admitted or
    refused by its class alone. The vocabulary is closed and lives beside the
    parse because it is dialect knowledge: what each shape may be about is a
    fact about PostgreSQL, not about the module that runs statements (D66).
    """
    if kind != "ddl" or node is None:
        return None
    if isinstance(node, (pgast.GrantStmt, pgast.AlterOwnerStmt)):
        return _PERMISSIONS
    if isinstance(node, pgast.TruncateStmt):
        return None
    if isinstance(node, pgast.AlterTableStmt):
        refused = _alter_refusal(node)
        if refused is not None:
            return refused
    if isinstance(node, pgast.CommentStmt):
        subject = _object_subject(node.objtype)
        if subject in _ALLOWED_COMMENT_KINDS:
            return None
        return _OUTSIDE.get(subject, _GENERAL_REFUSAL)
    # `SELECT ... INTO t` creates a table and is read as a query by the parser.
    if isinstance(node, pgast.SelectStmt):
        return None
    subject = _subject_of(node)
    if subject in _ALLOWED_KINDS:
        return None
    return _OUTSIDE.get(subject, _GENERAL_REFUSAL)


def _takes_away(cmd: pgast.AlterTableCmd) -> bool:
    """Whether this alter removes what was there: a column, a constraint, or
    what a column held before its type was rewritten."""
    if cmd.subtype in (AlterTableType.AT_DropColumn, AlterTableType.AT_DropConstraint):
        return True
    # A column changing type rewrites what is in it, and a value the new type
    # cannot hold does not survive the rewrite.
    return cmd.subtype is AlterTableType.AT_AlterColumnType and cmd.def_ is not None


def _destructive(node: pgast.Node | None) -> bool:
    """Whether what this does cannot be read back out of the statement.

    Dropping something takes its dependants with it, truncating takes rows and
    an alter that removes a column removes what was in it. None of that is
    visible in the text, which is why these are the statements rehearsed in a
    transaction and rolled back before anybody runs them for real (D66).
    """
    # Every drop by name: dropping something takes its dependants with it,
    # whatever kind of thing it is. Refused shapes never reach a rehearsal,
    # so this stays a uniform rule rather than a second vocabulary.
    if type(node).__name__.startswith("Drop") or isinstance(node, pgast.TruncateStmt):
        return True
    if isinstance(node, pgast.AlterTableStmt):
        return any(_takes_away(cmd) for cmd in node.cmds or ())
    return False


def _locks_readers_out(node: pgast.Node | None) -> bool:
    """Whether this maintenance holds the table from its readers (D66).

    A full vacuum and a cluster rewrite the table, a reindex and a refresh
    lock it unless they are told to work concurrently.
    """
    if isinstance(node, pgast.VacuumStmt):
        return any(option.defname == "full" for option in node.options or ())
    if isinstance(node, pgast.ClusterStmt):
        return True
    if isinstance(node, pgast.ReindexStmt):
        return not any(option.defname == "concurrently" for option in node.params or ())
    if isinstance(node, pgast.RefreshMatViewStmt):
        return not node.concurrent
    return False


def _risky(node: pgast.Node | None, kind: StatementClass) -> bool:
    """Whether this statement is one to ask about every time (D66).

    High risk is not "a write": it is a write whose reach is not written down.
    An UPDATE or DELETE with no predicate at the top of it touches every row a
    person can see; a MERGE decides per row what it does.

    Every structure change is high risk without further reading. A schema is
    what everything else in a source is described by, and there is no version
    of "this ALTER is routine" that is worth being wrong about.

    Anything this module cannot read is high risk as well, for the reason
    `unknown` is refused: not knowing is not the same as knowing it is safe.
    """
    if kind == "ddl":
        return True
    if kind == "maintenance":
        return _locks_readers_out(node)
    if kind != "dml" or node is None:
        return False
    found = _walk(node)
    if any(isinstance(one, pgast.MergeStmt) for one in found):
        return True
    return any(
        isinstance(one, (pgast.UpdateStmt, pgast.DeleteStmt)) and one.whereClause is None
        for one in found
    )


def _parameters(text: str) -> list[str]:
    """The `:name` bindings in this statement, in order of first appearance.

    Read from tokens, so `::` is a cast and not a parameter, and a colon
    inside a string or a comment is neither.
    """
    found: list[str] = []
    for _, _, name in _placeholders(text):
        if name not in found:
            found.append(name)
    return found


def _object_name(obj: Any) -> str:
    """One dropped thing, dotted: a name, or a function's name without its arguments."""
    if isinstance(obj, pgast.String):
        return obj.sval or ""
    if isinstance(obj, pgast.ObjectWithArgs):
        return ".".join(part.sval for part in obj.objname or ())
    if isinstance(obj, (tuple, list)):
        return ".".join(name for name in (_object_name(part) for part in obj) if name)
    return ""


def _dotted(variable: pgast.RangeVar | None) -> str:
    """A relation name as dots join it: catalog and schema when named.

    Built from the parts rather than rendered: rendering carries the alias
    with it, and what a run touched is the relation, not the letter somebody
    called it in this query.
    """
    if variable is None:
        return ""
    return ".".join(
        part
        for part in (variable.catalogname, variable.schemaname, variable.relname)
        if part
    )


def _targets(node: pgast.Node | None) -> list[str]:
    """What the statement names, for saying what a run was about."""
    if node is None:
        return []
    if isinstance(node, pgast.DropStmt):
        names = [_object_name(obj) for obj in node.objects or ()]
        return [name for name in dict.fromkeys(names) if name]
    if isinstance(node, pgast.RenameStmt):
        parts: list[str | None] = [_dotted(node.relation), node.newname]
        return [name for name in dict.fromkeys(parts) if name]
    if isinstance(node, pgast.CommentStmt):
        names = [_object_name(node.object)]
        return [name for name in dict.fromkeys(names) if name]
    names = [
        _dotted(found)
        for found in _walk(node)
        if isinstance(found, pgast.RangeVar)
    ]
    return [name for name in dict.fromkeys(names) if name]


def format_text(text: str) -> str:
    """Lay this text out again, statement by statement.

    Conservative, because formatting rewrites somebody's work: a statement is
    replaced only when it parses and when the formatted text parses back to
    exactly the same tree. Anything else — a form this dialect module cannot
    read, a round trip that does not match — is left character for character as
    it was. What is between statements is left alone too, so a semicolon, a
    blank line and a comment between them survive.
    """
    ranges = split(text)
    if not ranges:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces.append(text[cursor:start])
        pieces.append(_formatted(text[start:end]))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _formatted(statement: str) -> str:
    try:
        parsed = parse_one(statement, read="postgres")
        laid_out = parsed.sql(dialect="postgres", pretty=True)
        # The proof that nothing was changed: read the new text and compare the
        # trees, not the characters.
        if parse_one(laid_out, read="postgres") != parsed:
            return statement
    except (ParseError, TokenError):
        return statement
    return laid_out


def prepare(text: str) -> PreparedScript:
    """Everything the source can say about this text without running it."""
    statements: list[PreparedStatement] = []
    parameters: list[str] = []
    for ordinal, (start, end) in enumerate(split(text)):
        piece = text[start:end]
        node = _parse_piece(piece)
        kind = _classify(node)
        found = _parameters(piece)
        for name in found:
            if name not in parameters:
                parameters.append(name)
        statements.append(
            PreparedStatement(
                ordinal=ordinal,
                start=start,
                end=end,
                text=piece,
                kind=kind,
                risk="high" if _risky(node, kind) else "low",
                destructive=_destructive(node),
                refused=_refusal(node, kind),
                parameters=found,
                targets=_targets(node),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
