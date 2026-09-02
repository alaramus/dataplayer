"""What a source can be asked to do to rows somebody picked out in a grid.

An action (D9) is about a catalog node: rename this table, drop that schema.
Some relations describe things that are not rows of data at all — a list of
server processes, a queue, a set of jobs — and what a person wants there is to
act on the rows they can see. There was no vocabulary for that, and the only
shapes available were both lies: a delete that is not a delete, and a form
asking somebody to type in a number that is already on their screen.

So a relation may declare commands of its own. The rules are the ones every
other capability here follows: the source says what is offered and for which
node, the client renders what it is given without learning what any of it
means, and running one goes through the declaration rather than past it.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.core.access import Access


class RowCommand(BaseModel):
    """One thing a source offers to do to selected rows of one relation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    # What it will do, in the source's words. The client shows it and never
    # writes one of its own: a sentence about terminating a backend belongs
    # with the statement that terminates it.
    description: str = Field(min_length=1)
    destructive: bool = False
    # What a caller must hold on the connection to run it, declared on the
    # command for the reason an action declares it: only the command knows.
    requires: Access = "write"
    # The column whose value names a row for this command. One column, because
    # that is what every command that exists needs; a compound key is a
    # different contract and is not invented before somebody has one.
    identified_by: str = Field(min_length=1)


class RowCommandResult(BaseModel):
    """What the source did, and what it would not do.

    A count rather than a list of what worked: the interesting half is what
    did not, and the grid is about to be read again anyway.
    """

    model_config = ConfigDict(extra="forbid")

    message: str
    done: int = Field(ge=0)
    # The keys the source declined to act on, in its own words about each.
    refused: list[str] = Field(default_factory=list)


class UnknownRowCommand(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown row command: {name}")
        self.name = name


@runtime_checkable
class SupportsRowCommands(Protocol):
    """A source with commands over the rows of some of its relations.

    Two questions, answered by the same driver: what this node offers, and run
    one of them. There is no third place a name could resolve differently, and
    what a client may do is decided by the first rather than by the vocabulary
    existing at all.
    """

    def row_commands(self, node_id: str) -> list[RowCommand]: ...

    async def run_row_command(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult: ...
