"""Where one ClickHouse statement ends and what kind of statement it is (D270).

Pure: text in, prepared statements out, no connection anywhere. Boundaries come
from sqlglot's ClickHouse tokenizer and the class from its parser, as MySQL's
do (D232). What the parser does not model falls back to a bare command; only
the commands named below by the keyword the parser kept are classed, and the
rest is `unknown` and is not run. Two shapes the parser refuses are read off
the tokens: an `INSERT … FORMAT` with its data after it, and the read-only
`EXISTS` and `CHECK TABLE`.

A parameter is ClickHouse's own `{name:Type}`: the server parses the value as
the type the statement gives it, and nothing is put into the text (D62).
"""

import logging

from sqlglot import exp, parse_one
from sqlglot.dialects.clickhouse import ClickHouse
from sqlglot.errors import ParseError, TokenError

# sqlglot re-exports these without naming them in __all__.
from sqlglot.tokens import Token, TokenType  # type: ignore[attr-defined]

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass
from app.core.translation import N_, say_if

# sqlglot logs the statement it could not parse, at warning level; SQL stays
# out of application logs (D64).
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
logging.getLogger("sqlglot").propagate = False

_tokenizer = ClickHouse().tokenizer_class()

_READS = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Values)
_WRITES = (exp.Insert, exp.Update, exp.Delete)

# The commands sqlglot keeps as a keyword and the rest of the text.
_COMMANDS: dict[str, StatementClass] = {
    "SHOW": "read",
    "OPTIMIZE": "maintenance",
    "RENAME": "ddl",
    "EXCHANGE": "ddl",
    "ALTER": "ddl",
    "CREATE": "ddl",
    "DROP": "ddl",
    "ATTACH": "ddl",
    "GRANT": "ddl",
    "REVOKE": "ddl",
    "SYSTEM": "maintenance",
}

# What EXPLAIN shows besides a plan: answers about the statement, read as
# rows. A plan itself is Explain, a command of its own beside Run (D65).
_EXPLAIN_READS = frozenset({"AST", "SYNTAX", "QUERY", "PIPELINE", "ESTIMATE", "TABLE"})

_PERMISSIONS = N_("Permissions are not administered from the query editor")

# The closed vocabulary of structure changes (D66). A ClickHouse database is a
# schema (D267), and a dictionary is a table its server keeps filled.
_ALLOWED_KINDS = frozenset({"TABLE", "VIEW", "SCHEMA", "DATABASE", "DICTIONARY"})

_ROLES = N_("Roles and permissions are not administered from the query editor")
_OUTSIDE = {
    "USER": _ROLES,
    "ROLE": _ROLES,
    "ROW": _ROLES,
    "POLICY": _ROLES,
    "QUOTA": _ROLES,
    "SETTINGS": _ROLES,
    "PROFILE": _ROLES,
    "FUNCTION": N_("Functions and procedures are not changed from the query editor"),
    "NAMED": N_("Named collections are not changed from the query editor"),
}

_GENERAL_REFUSAL = N_(
    "The query editor changes databases, tables, views and dictionaries; "
    "this is something else"
)
_SYSTEM = N_("SYSTEM commands manage the server and are not run from the query editor")
_DETACHED = N_("Detaching and attaching tables is not done from the query editor")
_OWN_FORMAT = N_("The console shows a result itself; leave FORMAT out")


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
    """Where every `{name:Type}` is, and what it is called.

    Read from tokens, as the server reads them: a brace inside a string, a
    quoted name or a comment is not one, and a map literal `{'k': 1}` has a
    string where the name would be.
    """
    tokens = _tokens(text)
    found: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        if token.token_type is not TokenType.L_BRACE or index + 2 >= len(tokens):
            continue
        name, colon = tokens[index + 1], tokens[index + 2]
        if colon.token_type is not TokenType.COLON or not name.text.isidentifier():
            continue
        if name.token_type in (TokenType.STRING, TokenType.IDENTIFIER):
            continue
        depth = 0
        for closing in tokens[index + 3 :]:
            if closing.token_type is TokenType.L_PAREN:
                depth += 1
            elif closing.token_type is TokenType.R_PAREN:
                depth -= 1
            elif closing.token_type is TokenType.R_BRACE and depth == 0:
                found.append((token.start, closing.end + 1, name.text))
                break
    return found


def parameter_names(text: str) -> list[str]:
    found: list[str] = []
    for _, _, name in placeholders(text):
        if name not in found:
            found.append(name)
    return found


def parse(text: str) -> exp.Expr | None:
    try:
        return parse_one(text, read="clickhouse")
    except (ParseError, TokenError, ValueError):
        return None


def _words(text: str) -> list[str]:
    """The statement's leading words, upper case, as the tokenizer read them."""
    return [token.text.upper() for token in _tokens(text)[:6]]


def _command(node: exp.Command) -> tuple[str, list[str]]:
    """The keyword sqlglot kept, and the words of what follows it."""
    keyword = str(node.this).upper()
    rest = node.expression
    rest = str(rest.this if isinstance(rest, exp.Expr) else rest or "").strip()
    return keyword, [word.upper() for word in rest.split()[:6]]


def _insert_with_data(text: str) -> bool:
    """`INSERT INTO t [(a, b)] FORMAT Name` followed by its rows."""
    tokens = _tokens(text)
    if not tokens or tokens[0].text.upper() != "INSERT":
        return False
    return any(token.text.upper() == "FORMAT" for token in tokens)


def classify(node: exp.Expr | None, text: str) -> StatementClass:
    if node is None:
        words = _words(text)
        if words[:1] == ["EXISTS"] or words[:2] == ["CHECK", "TABLE"]:
            return "read"
        if _insert_with_data(text):
            return "dml"
        return "unknown"
    if isinstance(node, _READS):
        return "dml" if node.find(*_WRITES) is not None else "read"
    if isinstance(node, exp.Describe):
        return "read"
    if isinstance(node, _WRITES):
        return "dml"
    if isinstance(node, exp.Alter):
        # A mutation, `ALTER TABLE … DELETE`, changes rows rather than structure.
        actions = node.args.get("actions") or ()
        if actions and all(isinstance(action, exp.Delete) for action in actions):
            return "dml"
        return "ddl"
    if isinstance(node, (exp.Create, exp.Drop, exp.TruncateTable, exp.Detach)):
        return "ddl"
    if isinstance(node, (exp.Transaction, exp.Commit, exp.Rollback)):
        return "transaction"
    if isinstance(node, (exp.Set, exp.Use)):
        return "session"
    if isinstance(node, exp.Command):
        keyword, following = _command(node)
        if keyword == "EXPLAIN":
            return "read" if following[:1] and following[0] in _EXPLAIN_READS else "explain"
        if keyword == "ALTER" and "UPDATE" in following:
            return "dml"
        return _COMMANDS.get(keyword, "unknown")
    return "unknown"


def _subject(node: exp.Expr) -> str:
    """What a structure change is about, in `_OUTSIDE`'s words."""
    if isinstance(node, (exp.Create, exp.Drop, exp.Detach)):
        return str(node.args.get("kind") or "").upper()
    if isinstance(node, (exp.Alter, exp.TruncateTable)):
        kind = node.args.get("kind") if isinstance(node, exp.Alter) else "TABLE"
        return str(kind or "TABLE").upper()
    if isinstance(node, exp.Command):
        keyword, following = _command(node)
        if keyword in ("RENAME", "EXCHANGE"):
            return "TABLE"
        return following[0] if following else ""
    return ""


def _refusal(node: exp.Expr | None, kind: StatementClass) -> str | None:
    if isinstance(node, exp.Select) and node.args.get("format") is not None:
        return _OWN_FORMAT
    if node is None:
        return None
    if isinstance(node, exp.Command):
        keyword, _ = _command(node)
        if keyword == "SYSTEM":
            return _SYSTEM
        if keyword == "ATTACH":
            return _DETACHED
        if keyword in ("GRANT", "REVOKE"):
            return _PERMISSIONS
    if isinstance(node, exp.Detach):
        return _DETACHED
    if kind != "ddl":
        return None
    subject = _subject(node)
    if subject in _ALLOWED_KINDS:
        return None
    return _OUTSIDE.get(subject, _GENERAL_REFUSAL)


def _destructive(node: exp.Expr | None, kind: StatementClass) -> bool:
    """Whether what this does cannot be read back out of the statement (D66)."""
    if isinstance(node, (exp.Drop, exp.TruncateTable)):
        return True
    if isinstance(node, exp.Alter) and kind == "ddl":
        return any(
            isinstance(action, (exp.Drop, exp.ModifyColumn))
            or (isinstance(action, exp.AlterColumn) and action.args.get("dtype") is not None)
            for action in node.args.get("actions") or ()
        )
    if isinstance(node, exp.Command) and _command(node)[0] in ("ALTER", "EXCHANGE"):
        # An alter sqlglot could not read through may take anything away.
        return True
    return False


def _risky(node: exp.Expr | None, kind: StatementClass) -> bool:
    """A write whose reach is not written down, or a change of structure (D66)."""
    if kind in ("ddl", "unknown", "maintenance"):
        return True
    if kind != "dml" or node is None:
        return False
    if isinstance(node, exp.Command):
        return True
    return any(
        isinstance(found, (exp.Update, exp.Delete)) and found.args.get("where") is None
        for found in node.walk()
    )


def _targets(node: exp.Expr | None, text: str) -> list[str]:
    if node is None:
        tokens = _tokens(text)
        if _insert_with_data(text) and len(tokens) > 2:
            # INSERT INTO db.t: the words after INTO up to the columns or FORMAT.
            names: list[str] = []
            for token in tokens[2:]:
                if token.token_type in (TokenType.L_PAREN,) or token.text.upper() == "FORMAT":
                    break
                if token.token_type is not TokenType.DOT:
                    names.append(token.text)
            return [".".join(names)] if names else []
        return []
    if isinstance(node, exp.Command):
        return []
    found = [
        ".".join(part for part in (table.db, table.name) if part)
        for table in node.find_all(exp.Table)
    ]
    return [name for name in dict.fromkeys(found) if name]


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
    node = parse(statement)
    if node is None or isinstance(node, exp.Command) or classify(node, statement) == "unknown":
        return statement
    try:
        laid_out = node.sql(dialect="clickhouse", pretty=True)
        if parse_one(laid_out, read="clickhouse") != node:
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
        kind = classify(node, piece)
        found = parameter_names(piece)
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
                destructive=_destructive(node, kind),
                refused=say_if(_refusal(node, kind)),
                parameters=found,
                targets=_targets(node, piece),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
