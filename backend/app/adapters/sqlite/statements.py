"""Where one SQLite statement ends and what kind of statement it is (D252).

Pure: text in, prepared statements out, no connection anywhere. Tokens come
from the adapter's own tokenizer of SQLite's names, strings and comments, and
a semicolon ends a statement only where SQLite itself says the statement is
complete (`sqlite3.complete_statement`), so the body of a trigger stays one
statement. SQLite's grammar names a statement by its first keyword, after an
`EXPLAIN` or a `WITH` clause, and that keyword is what classes it; what is not
named below is `unknown` and is not run.
"""

import logging
import sqlite3

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError, TokenError

from app.adapters.query import (
    PreparedScript,
    PreparedStatement,
    SchemaEffect,
    StatementClass,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.definition import Token, name_of, tokenize
from app.adapters.sqlite.inspection import SCHEMA
from app.core.translation import N_, say_if

# sqlglot logs the statement it could not parse, at warning level; SQL stays
# out of application logs (D64).
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
logging.getLogger("sqlglot").propagate = False

_READS = frozenset({"SELECT", "VALUES"})
_WRITES = frozenset({"INSERT", "UPDATE", "DELETE", "REPLACE"})
_TRANSACTION = frozenset({"BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE"})
_MAINTENANCE = frozenset({"ANALYZE", "VACUUM", "REINDEX"})
_STRUCTURE = frozenset({"CREATE", "DROP", "ALTER"})

# Pragmas that only report, by the form they report in: about one table or
# index, with it named in parentheses, or bare. The same name with a value set
# is a setting, and a setting is a session statement (D252).
_REPORTS_ABOUT = frozenset(
    {
        "table_info",
        "table_xinfo",
        "table_list",
        "index_list",
        "index_info",
        "index_xinfo",
        "foreign_key_list",
        "foreign_key_check",
        "integrity_check",
        "quick_check",
    }
)
_REPORTS = _REPORTS_ABOUT | frozenset(
    {
        "application_id",
        "auto_vacuum",
        "collation_list",
        "compile_options",
        "data_version",
        "database_list",
        "encoding",
        "foreign_keys",
        "freelist_count",
        "function_list",
        "journal_mode",
        "module_list",
        "page_count",
        "page_size",
        "pragma_list",
        "schema_version",
        "user_version",
    }
)
# Pragmas that look after the file's storage.
_LOOKS_AFTER = frozenset({"optimize", "incremental_vacuum", "wal_checkpoint"})

# The closed vocabulary of structure changes, as PostgreSQL's (D66). SQLite
# has one schema here (D248), so there is no schema to make or drop.
_ALLOWED_KINDS = frozenset({"TABLE", "VIEW", "INDEX"})
_OUTSIDE = {
    "TRIGGER": N_("Triggers are not changed from the query editor"),
}
_GENERAL_REFUSAL = N_(
    "The query editor changes tables, views and indexes; this is something else"
)
_OTHER_FILES = N_("A connection to this file opens no other file")

# Words between CREATE and the kind of thing it makes.
_CREATE_MODIFIERS = frozenset({"TEMP", "TEMPORARY", "UNIQUE", "VIRTUAL"})


def _words(tokens: list[Token]) -> list[str]:
    return [token.value for token in tokens if token.kind == "word"]


def split(text: str) -> list[tuple[int, int]]:
    """The range of every statement, without its semicolon."""
    ranges: list[tuple[int, int]] = []
    first: Token | None = None
    last: Token | None = None
    for token in tokenize(text):
        if token.kind == "punct" and token.value == ";":
            if first is None or last is None:
                continue
            # A trigger's body holds semicolons of its own; SQLite says where
            # the statement really ends.
            if sqlite3.complete_statement(text[first.start : token.end]):
                ranges.append((first.start, last.end))
                first = last = None
            else:
                last = token
            continue
        if first is None:
            first = token
        last = token
    if first is not None and last is not None:
        ranges.append((first.start, last.end))
    return ranges


def placeholders(text: str) -> list[tuple[int, int, str]]:
    """Where every `:name` is, and what it is called.

    Read from tokens, so a colon inside a string, a quoted name or a comment is
    not a parameter. SQLite binds `:name` itself, so the text is sent as it is
    and only the values are given by name.
    """
    tokens = tokenize(text)
    found: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if token.value != ":" or following.kind != "word" or following.start != token.end:
            continue
        found.append((token.start, following.end, text[following.start : following.end]))
    return found


def _parameters(text: str) -> list[str]:
    found: list[str] = []
    for _, _, name in placeholders(text):
        if name not in found:
            found.append(name)
    return found


def _depth_zero(tokens: list[Token]) -> list[Token]:
    """The tokens outside every parenthesis."""
    found: list[Token] = []
    depth = 0
    for token in tokens:
        if token.kind == "punct" and token.value == "(":
            depth += 1
        elif token.kind == "punct" and token.value == ")":
            depth -= 1
        elif depth == 0:
            found.append(token)
    return found


def _main_keyword(tokens: list[Token]) -> str:
    """The keyword that names the statement, past EXPLAIN and WITH."""
    words = [token for token in tokens if token.kind == "word"]
    if not words:
        return ""
    head = words[0].value
    if head != "WITH":
        return head
    for token in _depth_zero(tokens)[1:]:
        if token.kind == "word" and token.value in _READS | _WRITES:
            return token.value
    return ""


def _pragma(text: str, tokens: list[Token]) -> tuple[str, bool, bool]:
    """A pragma's name, whether it sets a value, and whether it names an argument."""
    rest = tokens[1:]
    if len(rest) >= 3 and rest[1].value == ".":
        rest = rest[2:]
    if not rest:
        return "", False, False
    name = name_of(rest[0], text).lower()
    after = rest[1:]
    sets = bool(after) and after[0].value == "="
    argument = bool(after) and after[0].value == "("
    return name, sets, argument


def classify(text: str, tokens: list[Token]) -> StatementClass:
    keyword = _main_keyword(tokens)
    if keyword == "EXPLAIN":
        return "explain"
    if keyword in _READS:
        return "read"
    if keyword in _WRITES:
        return "dml"
    if keyword in _STRUCTURE:
        return "ddl"
    if keyword in _TRANSACTION:
        return "transaction"
    if keyword in _MAINTENANCE:
        return "maintenance"
    if keyword in ("ATTACH", "DETACH"):
        return "session"
    if keyword == "PRAGMA":
        name, sets, argument = _pragma(text, tokens)
        if name in _LOOKS_AFTER and not sets:
            return "maintenance"
        if sets or (argument and name not in _REPORTS_ABOUT):
            return "session"
        return "read" if name in _REPORTS else "unknown"
    return "unknown"


def _subject(tokens: list[Token]) -> str:
    """What a structure change is about: TABLE, VIEW, INDEX, TRIGGER."""
    words = _words(tokens)
    for word in words[1:]:
        if word not in _CREATE_MODIFIERS:
            return word
    return ""


def _refusal(tokens: list[Token], kind: StatementClass) -> str | None:
    words = _words(tokens)
    if words[:1] in (["ATTACH"], ["DETACH"]):
        return _OTHER_FILES
    if kind != "ddl":
        return None
    subject = _subject(tokens)
    if subject in _ALLOWED_KINDS:
        return None
    return _OUTSIDE.get(subject, _GENERAL_REFUSAL)


def _qualified(text: str, tokens: list[Token], at: int) -> tuple[str | None, str] | None:
    """A name, maybe qualified by a schema, starting at `tokens[at]`."""
    if at >= len(tokens) or tokens[at].kind not in ("word", "name"):
        return None
    first = name_of(tokens[at], text)
    if at + 2 < len(tokens) and tokens[at + 1].value == "." and tokens[at + 2].kind in ("word", "name"):
        return first, name_of(tokens[at + 2], text)
    return None, first


def _name_after(text: str, tokens: list[Token], *words: str) -> tuple[str | None, str] | None:
    """The object a statement names after its keywords and any IF [NOT] EXISTS."""
    index = 0
    for word in words:
        while index < len(tokens) and not tokens[index].is_word(word):
            index += 1
        index += 1
    while index < len(tokens) and tokens[index].is_word("IF", "NOT", "EXISTS"):
        index += 1
    return _qualified(text, tokens, index)


_TARGET_WORDS = frozenset({"FROM", "JOIN", "INTO", "UPDATE", "TABLE", "VIEW"})


def _targets(text: str, tokens: list[Token]) -> list[str]:
    names: list[str] = []
    for index, token in enumerate(tokens):
        if not token.is_word(*_TARGET_WORDS):
            continue
        at = index + 1
        while at < len(tokens) and tokens[at].is_word("IF", "NOT", "EXISTS", "OR"):
            at += 1
        found = _qualified(text, tokens, at)
        if found is None:
            continue
        schema, name = found
        names.append(name if schema in (None, SCHEMA) else f"{schema}.{name}")
    return list(dict.fromkeys(names))


def _destructive(tokens: list[Token]) -> bool:
    """Whether what this does cannot be read back out of the statement (D66)."""
    words = _words(tokens)
    if words[:1] == ["DROP"]:
        return True
    return words[:2] == ["ALTER", "TABLE"] and "DROP" in words


def _risky(tokens: list[Token], kind: StatementClass) -> bool:
    """A write whose reach is not written down, or a change of structure (D66)."""
    if kind in ("ddl", "unknown"):
        return True
    if kind != "dml":
        return False
    words = [token.value for token in _depth_zero(tokens) if token.kind == "word"]
    keyword = _main_keyword(tokens)
    if keyword == "REPLACE" or ("OR" in words and "REPLACE" in words):
        # A replacement deletes the rows it collides with before it inserts.
        return True
    if keyword in ("UPDATE", "DELETE"):
        return "WHERE" not in words[words.index(keyword) :]
    return False


def effect_of(text: str) -> SchemaEffect:
    """What a structure change means for the catalog on screen (D66).

    A relation's own changes name the relation; making, dropping or renaming
    one names `main`. A dropped index does not say which table it was on, and
    something in `temp` is in no catalog.
    """
    tokens = tokenize(text)
    words = _words(tokens)
    subject = _subject(tokens)
    temporary = "TEMP" in words[:3] or "TEMPORARY" in words[:3]
    if temporary:
        return SchemaEffect()
    if words[:1] == ["DROP"] and subject == "INDEX":
        return SchemaEffect(scope="connection")
    if subject == "INDEX":
        found = _name_after(text, tokens, "ON")
    else:
        found = _name_after(text, tokens, subject)
    if found is None:
        return SchemaEffect(scope="connection")
    schema, name = found
    if schema not in (None, SCHEMA):
        return SchemaEffect()
    relation = ids.relation_id(name)
    if subject == "INDEX":
        return SchemaEffect(relation_node_ids=[relation])
    if words[:1] == ["ALTER"]:
        if "RENAME" in words and "TO" in words and "COLUMN" not in words:
            return SchemaEffect(reload_node_ids=[SCHEMA])
        return SchemaEffect(relation_node_ids=[relation])
    return SchemaEffect(reload_node_ids=[SCHEMA])


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
    tokens = tokenize(statement)
    # Only reads and row changes: sqlglot's reading of SQLite's DDL loses
    # clauses it does not model (D252).
    if placeholders(statement) or classify(statement, tokens) not in ("read", "dml"):
        return statement
    try:
        parsed = parse_one(statement, read="sqlite")
        if isinstance(parsed, exp.Command):
            return statement
        laid_out = parsed.sql(dialect="sqlite", pretty=True)
        if parse_one(laid_out, read="sqlite") != parsed:
            return statement
    except (ParseError, TokenError, ValueError):
        return statement
    return laid_out


def prepare(text: str) -> PreparedScript:
    statements: list[PreparedStatement] = []
    parameters: list[str] = []
    for ordinal, (start, end) in enumerate(split(text)):
        piece = text[start:end]
        tokens = tokenize(piece)
        kind = classify(piece, tokens)
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
                risk="high" if _risky(tokens, kind) else "low",
                destructive=_destructive(tokens),
                refused=say_if(_refusal(tokens, kind)),
                parameters=found,
                targets=_targets(piece, tokens),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)
