"""Composing a statement from fixed text and validated names.

psycopg's `sql` module for drivers that have none: fixed text is written in
the adapter, a name is quoted by the adapter's own `Composable` for names, and
nothing else can be put into a statement. A value never is — it goes through
a placeholder. How a name is quoted is each dialect's, so that class is not
here.
"""

from collections.abc import Iterable


class Composable:
    def text(self) -> str:
        """The statement as it is sent to the driver."""
        raise NotImplementedError

    def readable(self) -> str:
        """The statement as a person reads and pastes it.

        The same text, except where a driver needs a character spelt twice
        that a person writes once: MySQL's `%`.
        """
        raise NotImplementedError

    def __add__(self, other: Composable) -> Composed:
        return Composed([self, other])


class SQL(Composable):
    """Text written in the adapter, `{}` marking where a part goes."""

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


class Composed(Composable):
    def __init__(self, parts: list[Composable]) -> None:
        self._parts = parts

    def text(self) -> str:
        return "".join(part.text() for part in self._parts)

    def readable(self) -> str:
        return "".join(part.readable() for part in self._parts)
