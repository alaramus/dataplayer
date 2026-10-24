"""Composing a MySQL statement: the shared composer, with MySQL's names.

A name is quoted by `Identifier`; everything else is `app.adapters.compose`.
"""

from app.adapters.compose import SQL as SQL
from app.adapters.compose import Composable as Composable
from app.adapters.compose import Composed as Composed
from app.adapters.mysql.session import identifier, quoted_name


class Identifier(Composable):
    """A name, each part quoted apart: `db`.`table`."""

    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def text(self) -> str:
        return identifier(*self._parts)

    def readable(self) -> str:
        return quoted_name(*self._parts)
