"""A column's definition as the server writes it, changed in one place (D235).

MySQL changes a column's type or nullability with `MODIFY`, which takes the
whole definition and keeps nothing it is not told: a definition rebuilt from
the catalog loses whatever the rebuild forgot — a default, a comment,
AUTO_INCREMENT, ON UPDATE, a collation. So the definition is the line
`SHOW CREATE TABLE` prints for the column, and only the part being changed is
replaced, found by the dialect's tokens so that nothing inside a quoted
default or comment is mistaken for a keyword.
"""

from dataclasses import dataclass

from sqlglot.dialects.mysql import MySQL
from sqlglot.errors import TokenError

# sqlglot re-exports these without naming them in __all__.
from sqlglot.tokens import Token, TokenType  # type: ignore[attr-defined]

from app.adapters.mysql.session import MysqlSession, quoted_name
from app.adapters.mysql.sql import SQL, Identifier
from app.core.translation import say

_tokenizer = MySQL().tokenizer_class()

# The words that end a column's type and begin its attributes. A character set
# and a collation belong to the type: MySQL takes them before NOT NULL.
_ATTRIBUTES = frozenset(
    {
        "NOT",
        "NULL",
        "DEFAULT",
        "AUTO_INCREMENT",
        "COMMENT",
        "ON",
        "GENERATED",
        "AS",
        "INVISIBLE",
        "VISIBLE",
        "UNIQUE",
        "PRIMARY",
        "KEY",
        "SRID",
        "COLUMN_FORMAT",
        "STORAGE",
        "CHECK",
        "REFERENCES",
    }
)
_CHARSET = frozenset({"CHARACTER", "CHARSET", "COLLATE"})
_LITERAL = frozenset({TokenType.STRING, TokenType.IDENTIFIER, TokenType.NATIONAL_STRING})


@dataclass(frozen=True)
class Definition:
    """One column's definition, without its name, cut where it can change."""

    text: str
    # Where the base type ends and where the type, with its character set and
    # collation, ends: offsets into `text`.
    base_end: int
    type_end: int

    @property
    def charset(self) -> str:
        return self.text[self.base_end : self.type_end].strip()

    def with_nullability(self, nullable: bool) -> str:
        """The same definition, requiring a value or not."""
        rest = _without_nullability(self.text[self.type_end :], default_too=not nullable)
        marker = " NULL" if nullable else " NOT NULL"
        return (self.text[: self.type_end].rstrip() + marker + " " + rest.strip()).strip()

    def with_type(self, type_sql: str, *, keeps_charset: bool) -> str:
        """The same definition with another type.

        The character set and collation stay only when the new type is text
        as well; a number has neither.
        """
        charset = f" {self.charset}" if keeps_charset and self.charset else ""
        return (type_sql + charset + " " + self.text[self.type_end :].strip()).strip()


def _tokens(text: str) -> list[Token]:
    try:
        return list(_tokenizer.tokenize(text))
    except TokenError:
        raise ValueError(say("The column's definition could not be read")) from None


def _word(token: Token) -> str:
    return "" if token.token_type in _LITERAL else token.text.upper()


def parse(text: str) -> Definition:
    depth = 0
    base_end: int | None = None
    for token in _tokens(text):
        if token.token_type is TokenType.L_PAREN:
            depth += 1
        elif token.token_type is TokenType.R_PAREN:
            depth -= 1
        elif depth == 0:
            word = _word(token)
            if word in _CHARSET and base_end is None:
                base_end = token.start
            if word in _ATTRIBUTES:
                return Definition(
                    text=text,
                    base_end=token.start if base_end is None else base_end,
                    type_end=token.start,
                )
    end = len(text)
    return Definition(text=text, base_end=end if base_end is None else base_end, type_end=end)


def _without_nullability(attributes: str, *, default_too: bool) -> str:
    """The attributes with `NOT NULL` or a bare `NULL` taken out.

    `DEFAULT NULL` is a default, and stays unless the column is to require a
    value, which a default of nothing contradicts.
    """
    tokens = _tokens(attributes)
    cut: list[tuple[int, int]] = []
    for index, token in enumerate(tokens):
        word = _word(token)
        before = _word(tokens[index - 1]) if index else ""
        if word == "NOT" and index + 1 < len(tokens) and _word(tokens[index + 1]) == "NULL":
            cut.append((token.start, tokens[index + 1].end + 1))
        elif word == "NULL" and before not in ("DEFAULT", "NOT"):
            cut.append((token.start, token.end + 1))
        elif word == "DEFAULT" and default_too and index + 1 < len(tokens) and _word(tokens[index + 1]) == "NULL":
            cut.append((token.start, tokens[index + 1].end + 1))
    for start, end in reversed(cut):
        attributes = attributes[:start] + attributes[end:]
    return " ".join(attributes.split())


async def column_definition(session: MysqlSession, schema: str, table: str, column: str) -> Definition:
    """The line SHOW CREATE TABLE prints for this column, without its name."""
    statement = SQL("SHOW CREATE TABLE {}").format(Identifier(schema, table))
    rows = await session.query(statement.text())
    ddl = str(rows[0].get("Create Table") or "")
    prefix = quoted_name(column) + " "
    for line in ddl.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return parse(stripped[len(prefix) :].rstrip(","))
    raise ValueError(say('Relation has no column "{column}"', column=column))
