"""Reading a node on from where a reader stopped (D312).

A reader is named by whoever reads; the source keeps where it stands. A span
is drawn first — from the reader's bookmark to the end as it is now — then
read a block at a time, and each block is confirmed once it is written
elsewhere, so a failure between the two reads the block again.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Where a reader with no bookmark starts: everything the source still keeps,
# or only what comes after the first reading.
ReadStart = Literal["earliest", "latest"]


class Bookmark(BaseModel):
    """The next position to read in each part of a node, by the part's key."""

    model_config = ConfigDict(extra="forbid")

    positions: dict[str, int] = Field(default_factory=dict)


class UnreadSpan(BaseModel):
    """What is still unread for a reader, up to the end as it stood when asked."""

    start: Bookmark
    line: Bookmark
    # At most this much lies between: a source's positions may have gaps.
    count: int
    # Removed by the source before the reader got to it.
    lost: int = 0
    # The reader had no bookmark, and starts where the start choice says.
    fresh: bool = False


class ReadBlock(BaseModel):
    """Rows of the asked columns, and the bookmark just after them."""

    rows: list[list[str | None]]
    after: Bookmark
    # Every part has been read up to the line.
    done: bool
