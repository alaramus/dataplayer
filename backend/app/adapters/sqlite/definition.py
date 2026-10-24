"""What a table's own `CREATE TABLE` text says that the pragmas do not (D249).

Checks, a column's collation, a generated column's expression and the names
constraints were given. Read by a tokenizer that knows SQLite's names, strings
and comments, so a comma or a parenthesis inside one of them is not taken for
structure; an expression is the original text between its parentheses.

A clause this reader cannot place is passed over rather than failing the
table: what the pragmas say stands without it.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

TokenKind = Literal["word", "name", "string", "number", "punct", "other"]

_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z_\u0080-￿][A-Za-z0-9_$\u0080-￿]*")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|0[xX][0-9A-Fa-f]+")
_BLOB = re.compile(r"[xX]'[0-9A-Fa-f]*'")


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    # A word in capitals, a quoted name without its quotes, anything else as
    # written.
    value: str
    start: int
    end: int

    def is_word(self, *words: str) -> bool:
        return self.kind == "word" and self.value in words


def _quoted(text: str, start: int, close: str) -> int:
    """Where a quoted run that opened at `start` ends; a doubled quote is one."""
    index = start + 1
    while index < len(text):
        if text[index] == close:
            if close != "]" and index + 1 < len(text) and text[index + 1] == close:
                index += 2
                continue
            return index + 1
        index += 1
    return len(text)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(text):
        character = text[index]
        if (space := _SPACE.match(text, index)) is not None:
            index = space.end()
            continue
        if text.startswith("--", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            index = len(text) if closing < 0 else closing + 2
            continue
        if (blob := _BLOB.match(text, index)) is not None:
            tokens.append(Token("other", blob.group(), index, blob.end()))
            index = blob.end()
            continue
        if character in "\"`[":
            close = "]" if character == "[" else character
            end = _quoted(text, index, close)
            inner = text[index + 1 : end - 1]
            if close != "]":
                inner = inner.replace(close * 2, close)
            tokens.append(Token("name", inner, index, end))
            index = end
            continue
        if character == "'":
            end = _quoted(text, index, "'")
            tokens.append(Token("string", text[index:end], index, end))
            index = end
            continue
        if (number := _NUMBER.match(text, index)) is not None:
            tokens.append(Token("number", number.group(), index, number.end()))
            index = number.end()
            continue
        if (word := _WORD.match(text, index)) is not None:
            tokens.append(Token("word", word.group().upper(), index, word.end()))
            index = word.end()
            continue
        tokens.append(Token("punct" if character in "(),.;" else "other", character, index, index + 1))
        index += 1
    return tokens


def name_of(token: Token, text: str) -> str:
    """A name as SQLite reads it: quoted without its quotes, a word as written."""
    return token.value if token.kind == "name" else text[token.start : token.end]


@dataclass(frozen=True)
class CheckText:
    name: str | None
    expression: str


@dataclass(frozen=True)
class KeyText:
    """A key the text names: a primary key, a unique one, or a foreign one."""

    name: str | None
    columns: list[str]
    target: str | None = None


@dataclass
class ColumnText:
    collation: str | None = None
    generated: str | None = None


@dataclass
class TableText:
    # By the column's name in lower case: SQLite compares names without case.
    columns: dict[str, ColumnText] = field(default_factory=dict)
    checks: list[CheckText] = field(default_factory=list)
    primary_key: KeyText | None = None
    unique: list[KeyText] = field(default_factory=list)
    foreign: list[KeyText] = field(default_factory=list)


# Where a column's type ends and its constraints begin.
_CONSTRAINT_WORDS = frozenset(
    {
        "CONSTRAINT",
        "PRIMARY",
        "NOT",
        "NULL",
        "UNIQUE",
        "CHECK",
        "DEFAULT",
        "COLLATE",
        "REFERENCES",
        "GENERATED",
        "AS",
    }
)
_TABLE_CONSTRAINT_WORDS = frozenset({"CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN"})


def _items(tokens: list[Token]) -> list[list[Token]]:
    """The comma-separated parts inside the first parentheses of a statement."""
    opening = next((i for i, token in enumerate(tokens) if token.value == "("), None)
    if opening is None:
        return []
    items: list[list[Token]] = [[]]
    depth = 0
    for token in tokens[opening + 1 :]:
        if token.kind == "punct" and token.value == "(":
            depth += 1
        elif token.kind == "punct" and token.value == ")":
            if depth == 0:
                return [item for item in items if item]
            depth -= 1
        elif token.kind == "punct" and token.value == "," and depth == 0:
            items.append([])
            continue
        items[-1].append(token)
    return [item for item in items if item]


def _group(tokens: list[Token], at: int) -> int:
    """The index just past the parenthesised group that opens at `at`."""
    depth = 0
    for index in range(at, len(tokens)):
        if tokens[index].kind != "punct":
            continue
        if tokens[index].value == "(":
            depth += 1
        elif tokens[index].value == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(tokens)


def _inside(text: str, tokens: list[Token], at: int) -> tuple[str, int]:
    """The text between the parentheses that open at `at`, and where they close."""
    end = _group(tokens, at)
    closing = tokens[end - 1]
    if closing.value != ")":
        return text[tokens[at].end :].strip(), end
    return text[tokens[at].end : closing.start].strip(), end


def _names(text: str, tokens: list[Token], at: int) -> tuple[list[str], int]:
    """The column names of a parenthesised list, without directions or collations."""
    end = _group(tokens, at)
    names: list[str] = []
    expecting = True
    for token in tokens[at + 1 : end - 1]:
        if token.kind == "punct" and token.value == ",":
            expecting = True
        elif expecting and token.kind in ("word", "name"):
            names.append(name_of(token, text))
            expecting = False
    return names, end


def _skip_to_constraint(tokens: list[Token], at: int) -> int:
    """Past whatever this reader does not read, up to the next constraint word."""
    index = at
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "punct" and token.value == "(":
            index = _group(tokens, index)
            continue
        if token.kind == "word" and token.value in _CONSTRAINT_WORDS:
            return index
        index += 1
    return index


def _column(text: str, item: list[Token], table: TableText) -> None:
    name = name_of(item[0], text)
    column = table.columns.setdefault(name.lower(), ColumnText())
    index = _skip_to_constraint(item, 1)
    constraint_name: str | None = None
    while index < len(item):
        token = item[index]
        if token.is_word("CONSTRAINT") and index + 1 < len(item):
            constraint_name = name_of(item[index + 1], text)
            index += 2
            continue
        if token.is_word("CHECK") and index + 1 < len(item) and item[index + 1].value == "(":
            expression, index = _inside(text, item, index + 1)
            table.checks.append(CheckText(constraint_name, expression))
        elif token.is_word("COLLATE") and index + 1 < len(item):
            column.collation = name_of(item[index + 1], text)
            index += 2
        elif token.is_word("PRIMARY"):
            table.primary_key = KeyText(constraint_name, [name])
            index = _skip_to_constraint(item, index + 1)
        elif token.is_word("UNIQUE"):
            table.unique.append(KeyText(constraint_name, [name]))
            index = _skip_to_constraint(item, index + 1)
        elif token.is_word("REFERENCES") and index + 1 < len(item):
            table.foreign.append(KeyText(constraint_name, [name], name_of(item[index + 1], text)))
            index = _skip_to_constraint(item, index + 2)
        elif token.is_word("GENERATED", "AS"):
            opening = next(
                (i for i in range(index, len(item)) if item[i].value == "("), None
            )
            if opening is None:
                return
            column.generated, index = _inside(text, item, opening)
        else:
            index = _skip_to_constraint(item, index + 1)
            constraint_name = None
            continue
        constraint_name = None


def _table_constraint(text: str, item: list[Token], table: TableText) -> None:
    index = 0
    name: str | None = None
    if item[0].is_word("CONSTRAINT") and len(item) > 1:
        name = name_of(item[1], text)
        index = 2
    if index >= len(item):
        return
    head = item[index]
    opening = next((i for i in range(index, len(item)) if item[i].value == "("), None)
    if opening is None:
        return
    if head.is_word("CHECK"):
        expression, _ = _inside(text, item, opening)
        table.checks.append(CheckText(name, expression))
    elif head.is_word("PRIMARY"):
        columns, _ = _names(text, item, opening)
        table.primary_key = KeyText(name, columns)
    elif head.is_word("UNIQUE"):
        columns, _ = _names(text, item, opening)
        table.unique.append(KeyText(name, columns))
    elif head.is_word("FOREIGN"):
        columns, end = _names(text, item, opening)
        target = next(
            (
                name_of(item[i + 1], text)
                for i in range(end, len(item) - 1)
                if item[i].is_word("REFERENCES")
            ),
            None,
        )
        table.foreign.append(KeyText(name, columns, target))


def read_table(text: str | None) -> TableText:
    """What a `CREATE TABLE` statement says; empty for no text or `AS SELECT`."""
    table = TableText()
    if not text:
        return table
    for item in _items(tokenize(text)):
        if item[0].kind == "word" and item[0].value in _TABLE_CONSTRAINT_WORDS:
            _table_constraint(text, item, table)
        elif item[0].kind in ("word", "name"):
            _column(text, item, table)
    return table


def index_predicate(text: str | None) -> str | None:
    """The condition of a partial index: what follows its WHERE, as written."""
    if not text:
        return None
    tokens = tokenize(text)
    depth = 0
    for token in tokens:
        if token.kind == "punct" and token.value == "(":
            depth += 1
        elif token.kind == "punct" and token.value == ")":
            depth -= 1
        elif depth == 0 and token.is_word("WHERE"):
            return text[token.end :].strip().rstrip(";").strip() or None
    return None
