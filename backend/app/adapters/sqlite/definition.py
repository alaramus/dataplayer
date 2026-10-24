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

# A stretch of the text, as (start, end) offsets into it.
Span = tuple[int, int]

ClauseKind = Literal[
    "primary", "unique", "foreign", "check", "not_null", "null", "default", "collate", "generated"
]


@dataclass(frozen=True)
class Clause:
    """One constraint of the table, or one clause of a column, where it is written.

    `span` runs from the clause's CONSTRAINT name, when it has one, to its last
    token; a table constraint's span is its whole item. A structure change
    edits the text by these spans and leaves everything else as written (D255).
    """

    kind: ClauseKind
    name: str | None
    span: Span
    # Which comma-separated item of the definition it is in.
    item: int
    # Inside a column's definition rather than an item of its own.
    inline: bool
    columns: list[str] = field(default_factory=list)
    target: str | None = None
    expression: str | None = None


@dataclass
class ColumnText:
    name: str
    item: int
    # Where the declared type is; an empty span just after the name if none.
    type_span: Span
    collation: str | None = None
    generated: str | None = None
    clauses: list[Clause] = field(default_factory=list)


@dataclass
class TableText:
    text: str = ""
    # The table's name as written, qualified or not.
    name_span: Span | None = None
    # Every comma-separated item between the definition's parentheses.
    items: list[Span] = field(default_factory=list)
    # By the column's name in lower case: SQLite compares names without case.
    columns: dict[str, ColumnText] = field(default_factory=dict)
    # The constraints, inline and table-level, in the order they are written.
    constraints: list[Clause] = field(default_factory=list)

    @property
    def checks(self) -> list[Clause]:
        return [clause for clause in self.constraints if clause.kind == "check"]

    @property
    def primary_key(self) -> Clause | None:
        return next((clause for clause in self.constraints if clause.kind == "primary"), None)

    @property
    def unique(self) -> list[Clause]:
        return [clause for clause in self.constraints if clause.kind == "unique"]

    @property
    def foreign(self) -> list[Clause]:
        return [clause for clause in self.constraints if clause.kind == "foreign"]


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


def _conflict(tokens: list[Token], at: int) -> int:
    """Past an `ON CONFLICT <resolution>` clause, if one starts at `at`."""
    if at + 1 < len(tokens) and tokens[at].is_word("ON") and tokens[at + 1].is_word("CONFLICT"):
        return min(at + 3, len(tokens))
    return at


def _reference_end(tokens: list[Token], at: int) -> int:
    """Past a foreign key clause whose REFERENCES is at `at`.

    `ON DELETE SET NULL` holds a word that starts a column's NULL clause, so
    the clause is read word by word rather than skipped to the next such word.
    """
    index = at + 2
    if index < len(tokens) and tokens[index].value == "(":
        index = _group(tokens, index)
    while index < len(tokens):
        token = tokens[index]
        if token.is_word("ON") and index + 1 < len(tokens):
            index += 2
            if index < len(tokens) and tokens[index].is_word("SET", "NO"):
                index += 2
            else:
                index += 1
        elif token.is_word("MATCH"):
            index += 2
        elif token.is_word("NOT") and index + 1 < len(tokens) and tokens[index + 1].is_word(
            "DEFERRABLE"
        ):
            index += 2
        elif token.is_word("DEFERRABLE"):
            index += 1
        elif token.is_word("INITIALLY"):
            index += 2
        else:
            break
    return min(index, len(tokens))


def _default_end(tokens: list[Token], at: int) -> int:
    """Past a DEFAULT clause whose keyword is at `at`: a group, or one value."""
    index = at + 1
    if index < len(tokens) and tokens[index].value == "(":
        return _group(tokens, index)
    if index < len(tokens) and tokens[index].value in ("+", "-"):
        index += 1
    return min(index + 1, len(tokens))


def _span(tokens: list[Token], start: int, end: int) -> Span:
    """From the start of `tokens[start]` to the end of `tokens[end - 1]`."""
    return tokens[start].start, tokens[max(end, start + 1) - 1].end


def _column(text: str, item: list[Token], position: int, table: TableText) -> None:
    name = name_of(item[0], text)
    typed = _skip_to_constraint(item, 1)
    type_span = (
        _span(item, 1, typed) if typed > 1 else (item[0].end, item[0].end)
    )
    column = ColumnText(name=name, item=position, type_span=type_span)
    table.columns[name.lower()] = column
    index = typed
    named_at: int | None = None
    constraint_name: str | None = None
    while index < len(item):
        token = item[index]
        if token.is_word("CONSTRAINT") and index + 1 < len(item):
            named_at = index
            constraint_name = name_of(item[index + 1], text)
            index += 2
            continue
        start = index if named_at is None else named_at
        clause: Clause | None = None
        if token.is_word("CHECK") and index + 1 < len(item) and item[index + 1].value == "(":
            expression, index = _inside(text, item, index + 1)
            clause = Clause("check", constraint_name, _span(item, start, index), position, True, [name], expression=expression)
        elif token.is_word("COLLATE") and index + 1 < len(item):
            column.collation = name_of(item[index + 1], text)
            index += 2
            clause = Clause("collate", constraint_name, _span(item, start, index), position, True)
        elif token.is_word("PRIMARY"):
            index = min(index + 2, len(item))
            if index < len(item) and item[index].is_word("ASC", "DESC"):
                index += 1
            index = _conflict(item, index)
            if index < len(item) and item[index].is_word("AUTOINCREMENT"):
                index += 1
            clause = Clause("primary", constraint_name, _span(item, start, index), position, True, [name])
        elif token.is_word("UNIQUE"):
            index = _conflict(item, index + 1)
            clause = Clause("unique", constraint_name, _span(item, start, index), position, True, [name])
        elif token.is_word("NOT") and index + 1 < len(item) and item[index + 1].is_word("NULL"):
            index = _conflict(item, index + 2)
            clause = Clause("not_null", constraint_name, _span(item, start, index), position, True)
        elif token.is_word("NULL"):
            index = _conflict(item, index + 1)
            clause = Clause("null", constraint_name, _span(item, start, index), position, True)
        elif token.is_word("DEFAULT"):
            index = _default_end(item, index)
            clause = Clause("default", constraint_name, _span(item, start, index), position, True)
        elif token.is_word("REFERENCES") and index + 1 < len(item):
            target = name_of(item[index + 1], text)
            index = _reference_end(item, index)
            clause = Clause("foreign", constraint_name, _span(item, start, index), position, True, [name], target)
        elif token.is_word("GENERATED", "AS"):
            opening = next((i for i in range(index, len(item)) if item[i].value == "("), None)
            if opening is None:
                return
            column.generated, index = _inside(text, item, opening)
            if index < len(item) and item[index].is_word("STORED", "VIRTUAL"):
                index += 1
            clause = Clause("generated", constraint_name, _span(item, start, index), position, True)
        else:
            index = _skip_to_constraint(item, index + 1)
        if clause is not None:
            column.clauses.append(clause)
            if clause.kind in ("primary", "unique", "foreign", "check"):
                table.constraints.append(clause)
        named_at = None
        constraint_name = None


def _table_constraint(text: str, item: list[Token], position: int, table: TableText) -> None:
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
    span = _span(item, 0, len(item))
    if head.is_word("CHECK"):
        expression, _ = _inside(text, item, opening)
        table.constraints.append(Clause("check", name, span, position, False, expression=expression))
    elif head.is_word("PRIMARY"):
        columns, _ = _names(text, item, opening)
        table.constraints.append(Clause("primary", name, span, position, False, columns))
    elif head.is_word("UNIQUE"):
        columns, _ = _names(text, item, opening)
        table.constraints.append(Clause("unique", name, span, position, False, columns))
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
        table.constraints.append(Clause("foreign", name, span, position, False, columns, target))


def _name_span(tokens: list[Token]) -> Span | None:
    """Where the table's name is: the name, maybe qualified, before its `(`."""
    opening = next((i for i, token in enumerate(tokens) if token.value == "("), None)
    if opening is None or opening < 1 or tokens[opening - 1].kind not in ("word", "name"):
        return None
    first = opening - 1
    if first >= 2 and tokens[first - 1].value == "." and tokens[first - 2].kind in ("word", "name"):
        first -= 2
    return tokens[first].start, tokens[opening - 1].end


def read_table(text: str | None) -> TableText:
    """What a `CREATE TABLE` statement says; empty for no text or `AS SELECT`."""
    table = TableText(text=text or "")
    if not text:
        return table
    tokens = tokenize(text)
    table.name_span = _name_span(tokens)
    for position, item in enumerate(_items(tokens)):
        table.items.append((item[0].start, item[-1].end))
        if item[0].kind == "word" and item[0].value in _TABLE_CONSTRAINT_WORDS:
            _table_constraint(text, item, position, table)
        elif item[0].kind in ("word", "name"):
            _column(text, item, position, table)
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
