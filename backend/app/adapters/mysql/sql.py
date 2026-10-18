"""Composing a MySQL statement from fixed text and validated names.

psycopg's `sql` module for this driver, which has none: fixed text is written
in this package, a name is quoted by `Identifier`, and nothing else can be
put into a statement. A value never is — it goes through a placeholder.
"""

from collections.abc import Iterable

from app.adapters.mysql.session import identifier, quoted_name


class Composable:
    def text(self) -> str:
        """The statement as it is sent to the driver."""
        raise NotImplementedError

    def readable(self) -> str:
        """The statement as a person reads and pastes it: see `identifier`."""
        raise NotImplementedError

    def __add__(self, other: Composable) -> Composed:
        return Composed([self, other])


class SQL(Composable):
    """Text written in this package, `{}` marking where a part goes."""

    def __init__(self, literal: str) -> None:
        self._literal = literal

    def text(self) -> str:
        return self._literal

    def readable(self) -> str:
        return self._literal

    def format(self, *parts: Composable) -> Composed:
        pieces = self._literal.split("{}")
        if len(pieces) != len(parts) + 1:
            raise ValueError("The statement has a different number of places than parts")
        composed: list[Composable] = [SQL(pieces[0])]
        for part, piece in zip(parts, pieces[1:], strict=True):
            composed.extend([part, SQL(piece)])
        return Composed(composed)

    def join(self, parts: Iterable[Composable]) -> Composed:
        joined: list[Composable] = []
        for index, part in enumerate(parts):
            if index:
                joined.append(self)
            joined.append(part)
        return Composed(joined)


class Identifier(Composable):
    """A name, each part quoted apart: `db`.`table`."""

    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def text(self) -> str:
        return identifier(*self._parts)

    def readable(self) -> str:
        return quoted_name(*self._parts)


class Composed(Composable):
    def __init__(self, parts: list[Composable]) -> None:
        self._parts = parts

    def text(self) -> str:
        return "".join(part.text() for part in self._parts)

    def readable(self) -> str:
        return "".join(part.readable() for part in self._parts)
