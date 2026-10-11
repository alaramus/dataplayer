"""Telling the search that a connection's names changed (D216).

A protocol here and an implementation in `app.search`, handed in at assembly:
the writers below the search in the layers cannot import it, and those above
it should not — what they changed is theirs to say, what follows is not.
"""

import uuid
from typing import Annotated, Protocol

from fastapi import Depends, Request


class NamesChanged(Protocol):
    """Something in DataPlayer created, renamed or dropped a node of this connection."""

    async def __call__(self, connector_id: uuid.UUID) -> None: ...


async def unchanged(connector_id: uuid.UUID) -> None:
    """What a writer is handed when nobody listens: a test, a script."""


def names_changed(request: Request) -> NamesChanged:
    hook: NamesChanged = getattr(request.app.state, "names_changed", unchanged)
    return hook


NamesChangedDep = Annotated[NamesChanged, Depends(names_changed)]
