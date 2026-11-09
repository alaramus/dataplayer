"""Composing a CQL statement: the shared composer, with CQL's names.

A name is quoted by `Identifier`; a value is a `?` bound to a prepared
statement (D342). Everything else is `app.adapters.compose`.
"""

from app.adapters.cassandra.session import quoted_name
from app.adapters.compose import SQL as SQL
from app.adapters.compose import Composable as Composable
from app.adapters.compose import Composed as Composed


class Identifier(Composable):
    """A name, each part quoted apart: "keyspace"."table"."""

    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def text(self) -> str:
        return quoted_name(*self._parts)

    def readable(self) -> str:
        return self.text()
