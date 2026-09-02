"""Finding a node by its name, below a level of the catalog.

A search is a read of the catalog rather than a query: what comes back is
`CatalogNode`s, the same ones a listing gives, so everything that draws a row,
opens a node or acts on one works unchanged (D76).

The text a person types is matched, never compiled: it is a case-insensitive
substring of a name, and there is no pattern language for a client to reach
into. That is D2c's rule about queries, said for the one input this capability
takes.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import CatalogNode

# What a search may be asked for at most, and what it costs when nothing says.
# Named here and used by both the model and the route that fills it, so a
# ceiling is one number rather than two that agree today.
DEFAULT_MATCHES = 100
MAX_MATCHES = 500

# An empty needle would match everything, and a thousand characters is not a
# name.
MAX_QUERY_LENGTH = 200


class NodeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Where the search starts: the level being looked at, or the root.
    node_id: str | None = None
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    limit: int = Field(default=DEFAULT_MATCHES, ge=1, le=MAX_MATCHES)


class NodeMatch(BaseModel):
    """One node that matched, and where it was found.

    `parent_id` is the source's own opaque id and is what the client sends back
    to stand there; `location` is the source's own wording for the same place,
    because a client that composed one would be reading an id apart (D21). The
    root of a connector has no name of its own, so it is the empty string —
    what the catalog draws there is the name of the connection.
    """

    model_config = ConfigDict(extra="forbid")

    node: CatalogNode
    parent_id: str | None = None
    location: str = ""


class NodeSearchResult(BaseModel):
    """What was found, and whether that is all there was.

    A search that stopped at a ceiling says so rather than looking complete:
    "nothing else matched" and "I stopped looking" are different answers, and
    the difference is the only thing that tells somebody to narrow the words.
    """

    model_config = ConfigDict(extra="forbid")

    matches: list[NodeMatch] = Field(default_factory=list)
    complete: bool = True
    # Why it stopped, in the source's own words. Absent when it did not.
    notice: str | None = None
