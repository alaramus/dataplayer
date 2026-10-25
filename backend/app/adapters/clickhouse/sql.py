"""Composing a ClickHouse statement: the shared composer, with ClickHouse's names
and the server's own parameters.

A name is quoted by `Identifier`; a value is a `{name:Type}` parameter whose
text travels apart from the statement (D267). Everything else is
`app.adapters.compose`.
"""

from app.adapters.clickhouse.session import quoted_name
from app.adapters.compose import SQL as SQL
from app.adapters.compose import Composable as Composable
from app.adapters.compose import Composed as Composed


class Identifier(Composable):
    """A name, each part quoted apart: `db`.`table`."""

    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def text(self) -> str:
        return quoted_name(*self._parts)

    def readable(self) -> str:
        return self.text()


class Params:
    """The parameters of one statement, each named as it is added.

    `type_` is always written by this adapter — a type of a closed set, or one
    the catalog stated — and never by a client.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def add(self, value: str, type_: str) -> Composable:
        name = f"p{len(self.values)}"
        self.values[name] = value
        return SQL("{" + name + ":" + type_ + "}")


def text_literal(value: str) -> str:
    """A string as ClickHouse's text format writes one, quotes and all."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def array_of_strings(values: list[str]) -> str:
    """The text of an `Array(String)` parameter."""
    return "[" + ",".join(text_literal(value) for value in values) + "]"
