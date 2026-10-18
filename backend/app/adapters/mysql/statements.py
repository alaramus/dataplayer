"""Where one MySQL statement ends and what kind of statement it is (D232).

Pure: text in, prepared statements out, no connection anywhere. Boundaries come
from sqlglot's MySQL tokenizer, so a semicolon inside a string, a quoted name or
a comment is not one. The class comes from sqlglot's MySQL parser, and `read`
is granted only to the shapes that are reads; whatever the parser does not
model — it falls back to a bare command, or to an alias for `FLUSH` and `TABLE`
— is `unknown` and is not run, unless it is one of the few commands named
below by the keyword the parser kept.
"""

import logging
import re

from sqlglot import exp, parse_one
from sqlglot.dialects.mysql import MySQL
from sqlglot.errors import ParseError, TokenError

# sqlglot re-exports these without naming them in __all__.
from sqlglot.tokens import Token, TokenType  # type: ignore[attr-defined]

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass
from app.core.translation import N_, say_if

# sqlglot logs the statement it could not parse, at warning level; SQL stays
# out of application logs (D64).
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
logging.getLogger("sqlglot").propagate = False

_tokenizer = MySQL().tokenizer_class()

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_READS = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Show, exp.Values)
_WRITES = (exp.Insert, exp.Update, exp.Delete, exp.Merge)

# The commands sqlglot keeps as a keyword and the rest of the text, by that
# keyword. Only these: the parser's own word for a statement it read as far as
# that, not a first word of somebody's text guessed at.
_COMMANDS: dict[str, StatementClass] = {
    "REPLACE": "dml",
    "OPTIMIZE": "maintenance",
    "RENAME": "ddl",
    "ALTER": "ddl",
    "CREATE": "ddl",
    "GRANT": "ddl",
    "REVOKE": "ddl",
}

_PERMISSIONS = N_("Permissions are not administered from the query editor")

# The closed vocabulary of structure changes, as PostgreSQL's (D66). A MySQL
# database is a schema (D229), so creating and dropping one is in it.
_ALLOWED_KINDS = frozenset({"TABLE", "VIEW", "INDEX", "SCHEMA", "DATABASE"})

_OUTSIDE = {
    "USER": N_("Roles and permissions are not administered from the query editor"),
    "ROLE": N_("Roles and permissions are not administered from the query editor"),
    "TABLESPACE": N_("Tablespaces are not managed from the query editor"),
    "FUNCTION": N_("Functions and procedures are not changed from the query editor"),
    "PROCEDURE": N_("Functions and procedures are not changed from the query editor"),
    "TRIGGER": N_("Triggers are not changed from the query editor"),
    "EVENT": N_("Scheduled events are not changed from the query editor"),
    "SEQUENCE": N_("Sequences are not changed from the query editor"),
    "SERVER": N_("Servers are not administered from the query editor"),
}

_GENERAL_REFUSAL = N_(
    "The query editor changes schemas, tables, views and indexes; "
    "this is something else"
)


def _tokens(text: str) -> list[Token]:
    try:
        return list(_tokenizer.tokenize(text))
    except TokenError:
        return []


def split(text: str) -> list[tuple[int, int]]:
    """The range of every statement, read off the dialect's tokens.

    A text the tokenizer cannot read at all — an unterminated string — is one
    statement, which then fails to parse and is refused by name.
    """
    tokens = _tokens(text)
    if not tokens:
        stripped = text.strip()
        if not stripped:
            return []
        start = text.index(stripped[0])
        return [(start, start + len(stripped))]
    ranges: list[tuple[int, int]] = []
    first: Token | None = None
    last: Token | None = None
    for token in tokens:
        if token.token_type is TokenType.SEMICOLON:
            if first is not None and last is not None:
                ranges.append((first.start, last.end + 1))
            first = last = None
            continue
        if first is None:
            first = token
        last = token
    if first is not None and last is not None:
        ranges.append((first.start, last.end + 1))
    return ranges


def placeholders(text: str) -> list[tuple[int, int, str]]:
    """Where every `:name` is, and what it is called.

    Read from tokens, so `:=` is an assignment and a colon inside a string, a
    JSON path or a comment is not a parameter. The same spelling PostgreSQL
    takes: MySQL's own `?` has no name, and a binding here has one.
    """
    tokens = _tokens(text)
    found: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens[:-1]):
        if token.token_type is not TokenType.COLON:
            continue
        following = tokens[index + 1]
        if following.start != token.end + 1:
            continue
        if _IDENTIFIER.fullmatch(following.text) is None:
            continue
        found.append((token.start, following.end + 1, following.text))
    return found


def bind(text: str) -> str:
    """The statement with each `:name` as the driver's `%s`, in order.

    The driver puts the value in, escaped for this server; nothing a user typed
    is composed into the text by this application (D62). A literal `%` is
    doubled, because the driver formats the whole text once anything is bound.
    """
    pieces: list[str] = []
    cursor = 0
    for start, end, _name in placeholders(text):
        pieces.append(text[cursor:start].replace("%", "%%"))
        pieces.append("%s")
        cursor = end
    pieces.append(text[cursor:].replace("%", "%%"))
    return "".join(pieces)


def bound_names(text: str) -> list[str]:
    """Each placeholder's name in order, repeats included: one value per `%s`."""
    return [name for _, _, name in placeholders(text)]


def _without_placeholders(text: str) -> str:
    """The text with each `:name` padded to a literal, so the parser reads it."""
    for start, end, _name in reversed(placeholders(text)):
        text = text[:start] + "0".ljust(end - start) + text[end:]
    return text


def parse(text: str) -> exp.Expr | None:
    try:
        return parse_one(_without_placeholders(text), read="mysql")
    except (ParseError, TokenError, ValueError):
        return None


def _command(node: exp.Command) -> tuple[str, str]:
    """The keyword sqlglot kept, and the first word of what follows it."""
    keyword = str(node.this).upper()
    # The rest is a string, or a string literal, depending on the command.
    rest = node.expression
    rest = str(rest.this if isinstance(rest, exp.Expr) else rest or "").strip()
    following = rest.split(None, 1)[0].upper() if rest else ""
    return keyword, following


def classify(node: exp.Expr | None) -> StatementClass:
    if node is None:
        return "unknown"
    if isinstance(node, exp.Select) and node.args.get("into") is not None:
        # `SELECT ... INTO @v` sets a session variable.
        return "session"
    if isinstance(node, _READS):
        return "dml" if node.find(*_WRITES) is not None else "read"
    if isinstance(node, exp.Describe):
        # `EXPLAIN` and `DESCRIBE` are one statement in MySQL: about a query it
        # is a plan, which is a command of its own (D65); about a table it is
        # a read of its columns.
        return "read" if isinstance(node.this, exp.Table) else "explain"
    if isinstance(node, _WRITES):
        return "dml"
    if isinstance(node, (exp.Create, exp.Drop, exp.Alter, exp.TruncateTable)):
        return "ddl"
    if isinstance(node, (exp.Transaction, exp.Commit, exp.Rollback)):
        return "transaction"
    if isinstance(node, (exp.Set, exp.Use)):
        return "session"
    if isinstance(node, exp.Analyze):
        return "maintenance"
    if isinstance(node, exp.Command):
        keyword, _ = _command(node)
        return _COMMANDS.get(keyword, "unknown")
    return "unknown"


def _subject(node: exp.Expr) -> str:
    """What a structure change is about, in `_OUTSIDE`'s words."""
    if isinstance(node, (exp.Create, exp.Drop)):
        return str(node.args.get("kind") or "").upper()
    if isinstance(node, (exp.Alter, exp.TruncateTable)):
        kind = node.args.get("kind") if isinstance(node, exp.Alter) else "TABLE"
        return str(kind or "TABLE").upper()
    if isinstance(node, exp.Command):
        keyword, following = _command(node)
        if keyword in ("GRANT", "REVOKE"):
            return "USER"
        if keyword == "RENAME":
            return following
        return following
    return ""


def _refusal(node: exp.Expr | None, kind: StatementClass) -> str | None:
    if kind != "ddl" or node is None:
        return None
    if isinstance(node, exp.Command) and _command(node)[0] in ("GRANT", "REVOKE"):
        return _PERMISSIONS
    subject = _subject(node)
    if isinstance(node, exp.Alter) or (
        isinstance(node, exp.Command) and _command(node)[0] == "ALTER"
    ):
        # Changing a database's character set is changing its rules rather
        # than its contents, and renaming one is not possible in MySQL.
        if subject in ("DATABASE", "SCHEMA"):
            return _GENERAL_REFUSAL
    if subject in _ALLOWED_KINDS:
        return None
    return _OUTSIDE.get(subject, _GENERAL_REFUSAL)


def _destructive(node: exp.Expr | None) -> bool:
    """Whether what this does cannot be read back out of the statement (D66)."""
    if isinstance(node, (exp.Drop, exp.TruncateTable)):
        return True
    if isinstance(node, exp.Alter):
        return any(_takes_away(action) for action in node.args.get("actions") or ())
    if isinstance(node, exp.Command) and _command(node)[0] == "ALTER":
        # An alter sqlglot could not read through may take anything away.
        return True
    return False


def _takes_away(action: exp.Expr) -> bool:
    """Whether an alter's action removes what was there: a column, an index,
    a key, or what a column held before its type was rewritten."""
    if isinstance(action, (exp.Drop, exp.ModifyColumn)):
        return True
    return isinstance(action, exp.AlterColumn) and action.args.get("dtype") is not None


def _risky(node: exp.Expr | None, kind: StatementClass) -> bool:
    """A write whose reach is not written down, or a change of structure (D66)."""
    if kind in ("ddl", "unknown"):
        return True
    if kind != "dml" or node is None:
        return False
    if isinstance(node, exp.Command):
        # REPLACE deletes the rows it collides with before it inserts.
        return True
    return any(
        isinstance(found, (exp.Update, exp.Delete)) and found.args.get("where") is None
        for found in node.walk()
    )


def _targets(node: exp.Expr | None) -> list[str]:
    if node is None or isinstance(node, exp.Command):
        return []
    names = [
        ".".join(part for part in (table.db, table.name) if part)
        for table in node.find_all(exp.Table)
    ]
    return [name for name in dict.fromkeys(names) if name]


def _parameters(text: str) -> list[str]:
    found: list[str] = []
    for _, _, name in placeholders(text):
        if name not in found:
            found.append(name)
    return found


def format_text(text: str) -> str:
    """Lay the text out again, only where the result parses back the same."""
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
    if placeholders(statement):
        # Formatting reads `:name` as something else and would write it back
        # changed; a statement with bindings is left as it was written.
        return statement
    try:
        parsed = parse_one(statement, read="mysql")
        # Only what the parser read as a statement it models: `FLUSH PRIVILEGES`
        # parses as an alias, and laid out again it reads `FLUSH AS PRIVILEGES`
        # — the same tree, and a different statement.
        if isinstance(parsed, exp.Command) or classify(parsed) == "unknown":
            return statement
        laid_out = parsed.sql(dialect="mysql", pretty=True)
        if parse_one(laid_out, read="mysql") != parsed:
            return statement
    except (ParseError, TokenError, ValueError):
        return statement
    return laid_out


def prepare(text: str) -> PreparedScript:
    statements: list[PreparedStatement] = []
    parameters: list[str] = []
    for ordinal, (start, end) in enumerate(split(text)):
        piece = text[start:end]
        node = parse(piece)
        kind = classify(node)
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
                refused=say_if(_refusal(node, kind)),
                parameters=found,
                targets=_targets(node),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
