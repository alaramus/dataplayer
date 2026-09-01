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

# The leading keyword of the state-changing families, which are refused with a
# sentence naming what they are. This table only chooses the wording: nothing
# here can make a statement runnable, because `read` is decided below by what
# the parse produced.
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
}

# What a parse of a whole statement may produce and still be a read.
_QUERY_NODES = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Values)

# Anything that writes, wherever it appears in the tree. A writable CTE parses
# as a query whose body holds one of these, which is exactly the form a first
# word would let through.
_WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Copy)

_DDL_NODES = (exp.Create, exp.Drop, exp.Alter, exp.TruncateTable, exp.Comment)


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

    if any(True for _ in node.find_all(*_WRITE_NODES)):
        return "copy" if isinstance(node, exp.Copy) else "dml"
    if isinstance(node, _DDL_NODES):
        return "ddl"
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
                kind=_classify(piece),
                parameters=found,
                targets=_targets(piece),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
