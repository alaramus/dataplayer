"""A node watched as it changes, a part at a time (D323).

What is watched is told as rows, so a screen draws them with what it knows of
rows already: a part is named by the source, carries its columns, and each
batch either replaces the part, is added to it, or replaces the rows it
names by their key. The capability says nothing about sockets; the route in
`app.connectors.watch` carries the batches to a browser.
"""

from collections.abc import AsyncGenerator
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

# `replace`: these rows are now the whole part. `append`: they are new rows
# after the ones before. `upsert`: each replaces the row with the same key,
# or is added after them.
LiveMode = Literal["replace", "append", "upsert"]


class LiveRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: str
    mode: LiveMode
    columns: list[str]
    rows: list[list[str | None]]
    # The columns naming a row, for `upsert`.
    key: list[str] = []


class LiveStart(BaseModel):
    """What a watch of a node offers: the intervals there are, and the one taken."""

    model_config = ConfigDict(extra="forbid")

    intervals: list[str]
    interval: str | None


@runtime_checkable
class SupportsLive(Protocol):
    async def live_start(self, node_id: str, interval: str | None) -> LiveStart:
        """The watch the node allows, or a refusal before anything is sent.

        Raises `NodeNotFound` for a node the source does not have, and
        `ValueError` for a node that is not watched or an interval it has not.
        """
        ...

    def live(self, node_id: str, interval: str | None) -> AsyncGenerator[LiveRows]:
        """The node as it stands, then as it changes, until the caller stops.

        Ends by raising `AdapterError` when the source stops answering.
        """
        ...
