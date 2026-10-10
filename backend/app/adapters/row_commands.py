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


class RowCommandCondition(BaseModel):
    """Which rows a command belongs on, when it does not belong on all of them.

    An extension is installed or removed, never both, and the row already says
    which: offering the other one is offering something the server refuses.
    One column and one value, compared against the cell exactly as this
    source's own answer spelled it — the client reads a page of text and knows
    nothing about what `installed` means.
    """

    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)
    equals: str


class RowCommand(BaseModel):
    """One thing a source offers to do to a row of one relation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    # What to draw, in the client's icon vocabulary. Declared here for the
    # reason the title is: the command is offered in the corner of its own
    # row, where there is room for a picture and none for a sentence, and a
    # client choosing the picture would be a table of command names on that
    # side — the thing declaring commands on the source exists to avoid.
    icon: str = Field(min_length=1)
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
    # The rows this one is offered on, or every row when it says nothing.
    applies_when: RowCommandCondition | None = None
    # Whether running it can leave the catalog of this connection different
    # from what is on screen. Installing an extension brings schemas, types and
    # functions with it; cancelling a query brings nothing. Said by the command
    # because only the command knows, and read by the client to decide whether
    # anything but the grid has to be read again (D66).
    changes_structure: bool = False


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


class PickedRowsAction(BaseModel):
    """An action offered over the rows somebody picked in a relation (D209).

    A row command (D70) runs at once. Some things done to rows are reviewed
    first — dropping chunks is a job with a plan — and those are actions of
    the node the rows belong to (D9), which the client cannot name: a node id
    is the source's encoding. So the relation names the action and the columns
    that name a row, and the source turns picked rows into the action's node
    and parameters when asked.
    """

    model_config = ConfigDict(extra="forbid")

    # The name of an action of the node the rows belong to.
    action: str = Field(min_length=1)
    title: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    destructive: bool = False
    # The level the action itself requires, so nobody is shown what they may not run.
    requires: Access = "write"
    # The columns whose values name one row, in order.
    identified_by: list[str] = Field(min_length=1, max_length=4)


class PickedRowsTarget(BaseModel):
    """What picked rows are, for the action offered over them."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    node_label: str = Field(min_length=1)
    # Set in the action's form; the plan reads each of them again.
    params: dict[str, object]
    # Fields these parameters stand in for, left out of the form.
    replaces: list[str] = Field(default_factory=list)


@runtime_checkable
class SupportsPickedRows(Protocol):
    """A source with reviewed actions over rows picked in some of its relations."""

    def picked_rows_actions(self, node_id: str) -> list[PickedRowsAction]: ...

    async def resolve_picked_rows(
        self, node_id: str, action: str, keys: Sequence[Sequence[str]]
    ) -> PickedRowsTarget: ...
