"""Where one DuckDB statement ends and what kind of statement it is (D392).

Pure: text in, prepared statements out, no connection anywhere. Tokens are
DuckDB's own (`duckdb.tokenize`), so a semicolon in a string, a dollar-quoted
body, a quoted name or a comment is not a boundary, and each statement's type
is the one DuckDB's parser names (`duckdb.extract_statements`). What is not
named below is `unknown` and is not run.
"""

import logging
from dataclasses import dataclass

import duckdb
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError, TokenError

from app.adapters import database_ids as ids
from app.adapters.query import (
    PreparedScript,
    PreparedStatement,
    SchemaEffect,
    StatementClass,
)
from app.core.translation import N_, say, say_if

# sqlglot logs the statement it could not parse, at warning level; SQL stays
# out of application logs (D64).
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
logging.getLogger("sqlglot").propagate = False

DEFAULT_SCHEMA = "main"

# Pragmas that only report. Any other pragma, and any pragma given a value,
# is a setting, and the engine's settings are fixed (D388).
_READ_PRAGMAS = frozenset(
    {
        "version",
        "platform",
        "user_agent",
        "table_info",
        "show",
        "show_tables",
        "show_tables_expanded",
        "show_databases",
        "database_list",
        "database_size",
        "storage_info",
        "metadata_info",
        "functions",
        "collations",
    }
)

# The closed vocabulary of structure changes (D66): what this console makes,
# changes and drops.
_ALLOWED_KINDS = frozenset(
    {"TABLE", "VIEW", "INDEX", "SCHEMA", "SEQUENCE", "TYPE", "MACRO", "FUNCTION"}
)
# Words between CREATE, ALTER or DROP and the kind of thing they are about.
_MODIFIERS = frozenset({"OR", "REPLACE", "TEMP", "TEMPORARY", "UNIQUE", "PERSISTENT"})

_OTHER_DATABASES = N_("A connection to this file opens no other database")
_FILES = N_(
    "Files are not written or loaded from the query editor; load one with "
    "INSERT … SELECT * FROM '~/file.csv'"
)
_EXTENSIONS = N_("Extensions are not installed or loaded here")
_SETTINGS = N_("The engine's settings are fixed; the schema is chosen above the editor")
_PREPARED = N_("Statements are not prepared here; write parameters as $name")
_SECRETS = N_("Secrets are of no use here: this engine reaches no network")
_GENERAL_REFUSAL = N_(
    "The query editor changes tables, views, indexes, schemas, sequences, types "
    "and macros; this is something else"
)

_TARGET_WORDS = frozenset({"FROM", "JOIN", "INTO", "UPDATE", "TABLE", "VIEW"})


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    kind: str
    text: str

    @property
    def word(self) -> str:
        """The token as a keyword is compared: in capitals, never a quoted name."""
        if self.kind in ("keyword", "identifier") and not self.text.startswith('"'):
            return self.text.upper()
        return ""

    @property
    def name(self) -> str:
        """The token as a name: a quoted one unquoted, any other as written."""
        if self.text.startswith('"') and self.text.endswith('"') and len(self.text) >= 2:
            return self.text[1:-1].replace('""', '"')
        return self.text

    def is_name(self) -> bool:
        return self.kind in ("keyword", "identifier")


def tokens_of(text: str) -> list[Token]:
    """DuckDB's tokens of the text, comments included, each ending where its text does."""
    raw = duckdb.tokenize(text)
    tokens: list[Token] = []
    for index, (start, kind) in enumerate(raw):
        following = raw[index + 1][0] if index + 1 < len(raw) else len(text)
        piece = text[start:following].rstrip()
        tokens.append(Token(start=start, end=start + len(piece), kind=kind.name, text=piece))
    return tokens


def _code(text: str) -> list[Token]:
    return [token for token in tokens_of(text) if token.kind != "comment"]


def _words(tokens: list[Token]) -> list[str]:
    return [token.word for token in tokens if token.word]


def split(text: str) -> list[tuple[int, int]]:
    """The range of every statement, from its first token to its last, without
    its semicolon or a comment after it."""
    ranges: list[tuple[int, int]] = []
    first: Token | None = None
    last: Token | None = None
    for token in _code(text):
        if token.kind == "operator" and token.text == ";":
            if first is not None and last is not None:
                ranges.append((first.start, last.end))
            first = last = None
            continue
        if first is None:
            first = token
        last = token
    if first is not None and last is not None:
        ranges.append((first.start, last.end))
    return ranges


def _parsed(text: str) -> tuple[str | None, set[str], str | None]:
    """DuckDB's type for one statement, its named parameters, and its parse error.

    A type DuckDB's own enumeration does not know — `UPDATE EXTENSIONS` — is
    no type at all here (checked on 2.0.0).
    """
    try:
        found = duckdb.extract_statements(text)
    except duckdb.Error as exc:
        return None, set(), sentence(str(exc))
    if len(found) != 1:
        return None, set(), None
    statement = found[0]
    try:
        kind: str | None = statement.type.name
    except ValueError:
        kind = None
    return kind, set(statement.named_parameters), None


_UNSAFE = {ord(character): " " for character in ("\r", "\n", "\t", "\x00")}


def sentence(text: str) -> str:
    """DuckDB's own sentence, without the excerpt it quotes and on one line."""
    head = text.split("\n\nLINE ", 1)[0].split("\nLINE ", 1)[0]
    return " ".join(head.translate(_UNSAFE).split())[:500] or say("The statement could not be read")


def _subject(words: list[str]) -> str:
    """What a structure change is about: TABLE, VIEW, INDEX, SECRET."""
    for word in words[1:]:
        if word not in _MODIFIERS:
            return word
    return ""


def _classify(text: str, tokens: list[Token], kind: str | None) -> tuple[StatementClass, str | None]:
    """The statement's class, and why it is refused when it is."""
    words = _words(tokens)
    first = words[0] if words else ""
    if kind is None:
        if words[:2] == ["UPDATE", "EXTENSIONS"]:
            return "session", _EXTENSIONS
        return "unknown", None
    if kind == "SELECT":
        return "read", None
    if kind == "MULTI":
        return ("read", None) if first in ("PIVOT", "UNPIVOT") else ("unknown", None)
    if kind == "CALL":
        return ("maintenance", None) if first in ("CHECKPOINT", "FORCE") else ("read", None)
    if kind == "VACUUM":
        return "maintenance", None
    if kind in ("INSERT", "UPDATE", "DELETE", "MERGE_INTO"):
        return "dml", None
    if kind == "EXPLAIN":
        return _explained(text, tokens)
    if kind == "TRANSACTION":
        return "transaction", None
    if kind in ("CREATE", "ALTER", "DROP"):
        if first == "DEALLOCATE":
            return "session", _PREPARED
        if first == "COMMENT":
            return "ddl", None
        subject = _subject(words)
        if subject == "SECRET":
            return "session", _SECRETS
        return "ddl", None if subject in _ALLOWED_KINDS else _GENERAL_REFUSAL
    if kind == "PRAGMA":
        if first == "IMPORT":
            return "session", _FILES
        name = tokens[1].name.lower() if len(tokens) > 1 else ""
        sets = any(token.text == "=" for token in tokens[2:3])
        if name in _READ_PRAGMAS and not sets:
            return "read", None
        return "session", _SETTINGS
    if kind in ("SET", "VARIABLE_SET"):
        return "session", _SETTINGS
    if kind in ("ATTACH", "DETACH", "COPY_DATABASE"):
        return "session", _OTHER_DATABASES
    if kind in ("COPY", "EXPORT"):
        return "session", _FILES
    if kind in ("LOAD", "EXTENSION"):
        return "session", _EXTENSIONS
    if kind in ("PREPARE", "EXECUTE"):
        return "session", _PREPARED
    return "unknown", None


def _explained(text: str, tokens: list[Token]) -> tuple[StatementClass, str | None]:
    """EXPLAIN plans; EXPLAIN ANALYZE runs what it explains, so it is that."""
    for index, token in enumerate(tokens[1:3], start=1):
        if token.word == "ANALYZE":
            rest = text[tokens[index].end :]
            kind, _, _ = _parsed(rest)
            inner, refused = _classify(rest, _code(rest), kind)
            return ("explain", None) if inner == "read" else (inner, refused)
    return "explain", None


def _qualified(tokens: list[Token], at: int) -> tuple[str | None, str] | None:
    """A name, maybe qualified by a schema, starting at `tokens[at]`; of a
    three-part name, the last two parts."""
    if at >= len(tokens) or not tokens[at].is_name():
        return None
    parts = [tokens[at].name]
    while (
        at + 2 < len(tokens)
        and tokens[at + 1].text == "."
        and tokens[at + 2].is_name()
    ):
        parts.append(tokens[at + 2].name)
        at += 2
    if len(parts) == 1:
        return None, parts[0]
    return parts[-2], parts[-1]


def _name_after(tokens: list[Token], *words: str) -> tuple[str | None, str] | None:
    """The object a statement names after its keywords and any IF [NOT] EXISTS."""
    index = 0
    for word in words:
        while index < len(tokens) and tokens[index].word != word:
            index += 1
        index += 1
    while index < len(tokens) and tokens[index].word in ("IF", "NOT", "EXISTS"):
        index += 1
    return _qualified(tokens, index)


def _targets(tokens: list[Token]) -> list[str]:
    names: list[str] = []
    for index, token in enumerate(tokens):
        if token.word not in _TARGET_WORDS:
            continue
        at = index + 1
        while at < len(tokens) and tokens[at].word in ("IF", "NOT", "EXISTS", "OR"):
            at += 1
        found = _qualified(tokens, at)
        if found is None:
            continue
        schema, name = found
        names.append(name if schema is None else f"{schema}.{name}")
    return list(dict.fromkeys(names))


def _depth_zero_words(tokens: list[Token]) -> list[str]:
    words: list[str] = []
    depth = 0
    for token in tokens:
        if token.text == "(":
            depth += 1
        elif token.text == ")":
            depth -= 1
        elif depth == 0 and token.word:
            words.append(token.word)
    return words


def _destructive(words: list[str]) -> bool:
    """Whether what this does cannot be read back out of the statement (D66)."""
    if words[:1] in (["DROP"], ["TRUNCATE"]):
        return True
    if words[:3] == ["CREATE", "OR", "REPLACE"]:
        # A replaced table loses its rows, a replaced view its definition.
        return True
    return words[:1] == ["ALTER"] and "DROP" in words


def _risky(tokens: list[Token], kind: StatementClass) -> bool:
    """A write whose reach is not written down, or a change of structure (D66)."""
    if kind in ("ddl", "unknown"):
        return True
    if kind != "dml":
        return False
    words = _depth_zero_words(tokens)
    first = words[0] if words else ""
    if first in ("TRUNCATE", "MERGE"):
        return True
    if first == "INSERT" and "REPLACE" in words:
        # A replacement overwrites the rows it collides with.
        return True
    if first in ("UPDATE", "DELETE"):
        return "WHERE" not in words
    return False


def _parameters(tokens: list[Token], named: set[str]) -> list[str]:
    """Every `$name` in the order it first appears, then any DuckDB names that
    a scan of the tokens did not see, such as a bare `?`."""
    found: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if token.text != "$" or following.start != token.end:
            continue
        if following.kind in ("keyword", "identifier", "numeric_const"):
            name = following.name
            if name not in found:
                found.append(name)
    found += sorted(name for name in named if name not in found)
    return found


def statement_type(text: str) -> str | None:
    """The type DuckDB's parser names for one statement, or nothing."""
    return _parsed(text)[0]


def returns_rows(text: str) -> bool:
    """Whether a change hands back rows: `RETURNING` outside every parenthesis."""
    return "RETURNING" in _depth_zero_words(_code(text))


def effect_of(text: str, schema: str = DEFAULT_SCHEMA) -> SchemaEffect:
    """What a structure change means for the catalog on screen (D66).

    `schema` is where an unqualified name lands. Sequences, types and macros
    are not in the catalog yet, and something temporary is in no catalog.
    """
    tokens = _code(text)
    words = _words(tokens)
    if words[:1] == ["COMMENT"]:
        found = _name_after(tokens, "ON", words[2] if len(words) > 2 else "")
        if found is None:
            return SchemaEffect(scope="connection")
        owner, name = found
        if len(words) > 2 and words[2] == "COLUMN":
            # COMMENT ON COLUMN t.c, or s.t.c: the relation is before the column.
            return SchemaEffect(scope="connection") if owner is None else SchemaEffect(
                relation_node_ids=[ids.relation_id(schema, owner)]
            )
        return SchemaEffect(relation_node_ids=[ids.relation_id(owner or schema, name)])
    subject = _subject(words)
    if "TEMP" in words[:4] or "TEMPORARY" in words[:4]:
        return SchemaEffect()
    if subject == "SCHEMA":
        return SchemaEffect(reload_node_ids=[None])
    if subject not in ("TABLE", "VIEW", "INDEX"):
        return SchemaEffect()
    if words[:1] == ["DROP"] and subject == "INDEX":
        return SchemaEffect(scope="connection")
    found = _name_after(tokens, "ON") if subject == "INDEX" else _name_after(tokens, subject)
    if found is None:
        return SchemaEffect(scope="connection")
    owner, name = found
    where = owner or schema
    relation = ids.relation_id(where, name)
    if subject == "INDEX":
        return SchemaEffect(relation_node_ids=[relation])
    if words[:1] == ["ALTER"]:
        if "RENAME" in words and "TO" in words and "COLUMN" not in words:
            return SchemaEffect(reload_node_ids=[ids.database_id(where)])
        return SchemaEffect(relation_node_ids=[relation])
    return SchemaEffect(reload_node_ids=[ids.database_id(where)])


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
    kind, named, error = _parsed(statement)
    tokens = _code(statement)
    # Only reads and row changes: a layout of DDL may drop what sqlglot does
    # not model, and a parameter is not sqlglot's to move.
    if error is not None or named or _classify(statement, tokens, kind)[0] not in ("read", "dml"):
        return statement
    try:
        parsed = parse_one(statement, read="duckdb")
        if isinstance(parsed, exp.Command):
            return statement
        laid_out = parsed.sql(dialect="duckdb", pretty=True)
        if parse_one(laid_out, read="duckdb") != parsed:
            return statement
    except (ParseError, TokenError, ValueError):
        return statement
    return laid_out


def prepare(text: str) -> PreparedScript:
    statements: list[PreparedStatement] = []
    parameters: list[str] = []
    for ordinal, (start, end) in enumerate(split(text)):
        piece = text[start:end]
        tokens = _code(piece)
        kind, named, error = _parsed(piece)
        if error is not None:
            klass: StatementClass = "unknown"
            refused: str | None = error
        else:
            klass, worded = _classify(piece, tokens, kind)
            refused = say_if(worded)
        found = _parameters(tokens, named)
        for name in found:
            if name not in parameters:
                parameters.append(name)
        statements.append(
            PreparedStatement(
                ordinal=ordinal,
                start=start,
                end=end,
                text=piece,
                kind=klass,
                risk="high" if _risky(tokens, klass) else "low",
                destructive=_destructive(_words(tokens)),
                refused=refused,
                parameters=found,
                targets=_targets(tokens),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
