"""Composing a DuckDB statement: the shared composer, with DuckDB's names."""

from app.adapters.compose import SQL as SQL
from app.adapters.compose import Composable as Composable
from app.adapters.compose import Composed as Composed


def quoted_name(*parts: str) -> str:
    """A name in double quotes, each part apart: "sales.eu"."orders"."""
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


class Identifier(Composable):
    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def text(self) -> str:
        return quoted_name(*self._parts)

    def readable(self) -> str:
        return quoted_name(*self._parts)
