"""Where one statement ends and what kind of statement it is.

Pure: text in, prepared statements out, no connection anywhere. That is what
lets every awkward form — a semicolon inside a string, a comment or a
dollar-quoted function body, a writable CTE, `SELECT INTO` — be tested without
a database.

The dialect's own tokenizer draws the boundaries and its parser decides the
class. Splitting on semicolons, reading the first word or keeping a blacklist
are not accepted substitutes (D62), and the reason is visible here: `read` is
granted only by a parse that produced a query and nothing else, so a form this
version has never seen is refused rather than allowed by omission.
"""

import logging
import re

from sqlglot import exp, parse_one
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

# The leading keyword of the families the parser is not asked about. Most are
# refused with a sentence naming what they are; `maintenance` runs, outside a
# transaction and with write access (D206). Nothing here can make a statement
# a read: `read` is decided below by what the parse produced.
_LEADING: dict[str, StatementClass] = {
    "BEGIN": "transaction",
    "START": "transaction",
    "COMMIT": "transaction",
    "END": "transaction",
    "ROLLBACK": "transaction",
    "SAVEPOINT": "transaction",
    "RELEASE": "transaction",
    "SET": "session",
    "RESET": "session",
    "DISCARD": "session",
    "LISTEN": "session",
    "UNLISTEN": "session",
    "NOTIFY": "session",
    "PREPARE": "session",
    "EXECUTE": "session",
    "DEALLOCATE": "session",
    "COPY": "copy",
    "EXPLAIN": "explain",
    "ANALYZE": "maintenance",
    "ANALYSE": "maintenance",
    "VACUUM": "maintenance",
    "REINDEX": "maintenance",
    "CLUSTER": "maintenance",
    "CHECKPOINT": "maintenance",
    "REFRESH": "maintenance",
}

# The maintenance that locks a relation against its readers while it works:
# a full vacuum and a cluster rewrite the table, a reindex and a refresh lock
# it unless they are told to work concurrently. Asked about every time (D66).
_LOCKING = frozenset({"CLUSTER", "REINDEX", "REFRESH"})

# What a parse of a whole statement may produce and still be a read.
_QUERY_NODES = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Values)

# Anything that writes, wherever it appears in the tree. A writable CTE parses
# as a query whose body holds one of these, which is exactly the form a first
# word would let through.
_WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Copy)

# A permission change is a change to the schema's rules, so it is DDL here
# and high risk below; the allowlist of what may actually run is narrower.
_DDL_NODES = (
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Comment,
    exp.Grant,
    exp.Revoke,
)

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


def split(text: str) -> list[tuple[int, int]]:
    """The range of every statement in this text, in order.

    Ranges rather than pieces: an error points into what the person wrote, and
    a run keeps the exact text it executed. Blank runs between semicolons are
    not statements and are left out.
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


def _leading_keyword(text: str) -> str:
    tokens = _tokenizer.tokenize(text)
    return tokens[0].text.upper() if tokens else ""


def _command_words(text: str) -> set[str]:
    """The words of a statement, upper-cased, comments and strings left out.

    Trap: the tokenizer reads a command it has no grammar for — VACUUM,
    REINDEX — as its keyword and one string holding the rest, so the rest is
    tokenized again rather than searched as text.
    """
    tokens = _tokenizer.tokenize(text)
    if len(tokens) == 2 and tokens[0].token_type is TokenType.COMMAND:
        tokens = _tokenizer.tokenize(tokens[1].text)
    return {token.text.upper() for token in tokens}


def _classify(text: str) -> StatementClass:
    """What kind of statement this is, or `unknown`.

    The order is the point. A statement whose leading keyword names a
    state-changing family is that family whatever else the parser makes of it —
    sqlglot reads `START TRANSACTION` as an alias, and an alias must not become
    a read. Everything else has to parse into a query with nothing that writes
    in it before it may be called one.
    """
    leading = _leading_keyword(text)
    named = _LEADING.get(leading)
    if named is not None:
        return named

    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):
        return "unknown"

    # Structure before writing, because a structure change may contain one:
    # `CREATE TABLE t AS WITH x AS (INSERT ... RETURNING *) SELECT * FROM x`
    # creates a relation, and reading the INSERT first would have called it a
    # DML statement and let it run on `write` access alone.
    if isinstance(node, _DDL_NODES):
        return "ddl"
    if any(True for _ in node.find_all(*_WRITE_NODES)):
        return "copy" if isinstance(node, exp.Copy) else "dml"
    if isinstance(node, exp.Select) and node.args.get("into") is not None:
        # `SELECT ... INTO new_table` creates a relation, whatever it looks
        # like from the first word.
        return "ddl"
    if isinstance(node, _QUERY_NODES):
        return "read"
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


def _refusal(text: str, kind: StatementClass) -> str | None:
    """Why this source will not carry the statement out, if it will not.

    Only structure changes are answered here; every other class is admitted or
    refused by its class alone. The vocabulary is closed and lives beside the
    parse because it is dialect knowledge: what `CREATE` may be followed by is
    a fact about PostgreSQL, not about the module that runs statements (D66).
    """
    if kind != "ddl":
        return None
    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):  # pragma: no cover - `unknown` by then
        return _GENERAL_REFUSAL
    if isinstance(node, exp.Grant | exp.Revoke):
        return "Permissions are not administered from the query editor"
    if isinstance(node, exp.TruncateTable):
        return None
    if isinstance(node, exp.Comment):
        subject = str(node.args.get("kind") or "").upper()
        if subject in _ALLOWED_COMMENT_KINDS:
            return None
        return _OUTSIDE.get(subject, _GENERAL_REFUSAL)
    if isinstance(node, exp.Create | exp.Drop | exp.Alter):
        subject = str(node.args.get("kind") or "").upper()
        if subject in _ALLOWED_KINDS:
            return None
        return _OUTSIDE.get(subject, _GENERAL_REFUSAL)
    # `SELECT ... INTO t` creates a table and is read as a query by the parser.
    if isinstance(node, exp.Select):
        return None
    return _GENERAL_REFUSAL


def _destructive(text: str, kind: StatementClass) -> bool:
    """Whether what this does cannot be read back out of the statement.

    Dropping something takes its dependants with it, truncating takes rows and
    an alter that removes a column removes what was in it. None of that is
    visible in the text, which is why these are the statements rehearsed in a
    transaction and rolled back before anybody runs them for real (D66).
    """
    if kind != "ddl":
        return False
    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):  # pragma: no cover - `unknown` by then
        return True
    if isinstance(node, exp.Drop | exp.TruncateTable):
        return True
    if isinstance(node, exp.Alter):
        actions = node.args.get("actions") or []
        return any(
            isinstance(action, exp.Drop)
            # A column changing type rewrites what is in it, and a value the
            # new type cannot hold does not survive the rewrite.
            or (isinstance(action, exp.AlterColumn) and action.args.get("dtype"))
            for action in actions
        )
    return False


def _risky(text: str, kind: StatementClass) -> bool:
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
        words = _command_words(text)
        leading = _leading_keyword(text)
        if leading == "VACUUM":
            return "FULL" in words
        return leading in _LOCKING and "CONCURRENTLY" not in words
    if kind != "dml":
        return False
    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):
        return True
    if any(True for _ in node.find_all(exp.Merge)):
        return True
    return any(
        write.args.get("where") is None for write in node.find_all(exp.Update, exp.Delete)
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


def _targets(text: str) -> list[str]:
    """What the statement names, for saying what a run was about."""
    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):
        return []
    names: list[str] = []
    for table in node.find_all(exp.Table):
        # Built from the parts rather than rendered: rendering carries the
        # alias with it, and what a run touched is the relation, not the
        # letter somebody called it in this query.
        qualified = ".".join(
            part for part in (table.catalog, table.db, table.name) if part
        )
        if qualified and qualified not in names:
            names.append(qualified)
    return names


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
        kind = _classify(piece)
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
                risk="high" if _risky(piece, kind) else "low",
                destructive=_destructive(piece, kind),
                refused=_refusal(piece, kind),
                parameters=found,
                targets=_targets(piece),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
