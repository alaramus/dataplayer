"""The model the search finds meaning with (D220).

A protocol and one implementation: a local Text Embeddings Inference server in
a container of its own. An external provider would be a second implementation
saying `sends_out`; before one is written, the passages it embeds have to be
those of connections whose owner allows transfer (D135), with the owner's key
(D140), and the words a person types never leave the server.
"""

import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings

# A vector, as many floats as the model has dimensions.
Vector = list[float]


@dataclass(frozen=True)
class EmbedderInfo:
    """What a model answering now is: a vector is kept under its name."""

    model: str
    # How many tokens it reads of one text; more is cut by the server.
    max_tokens: int


class Embedder(Protocol):
    """Turns text into vectors, a query and a passage each in its own form."""

    @property
    def sends_out(self) -> bool:
        """Whether text leaves this server to be embedded (D135 applies if so)."""
        ...

    async def info(self) -> EmbedderInfo | None:
        """The model answering now, or nothing when none answers."""
        ...

    async def queries(self, texts: Sequence[str]) -> list[Vector]: ...

    async def passages(self, texts: Sequence[str]) -> list[Vector]: ...


# How long what the model said of itself is believed, and how long a server
# that did not answer is left alone: asking on every keystroke would make a
# missing service cost every search a connection attempt.
_INFO_SECONDS = 30.0
# Queries remembered: the same words are asked once per connection's cell.
_REMEMBERED_QUERIES = 128


class LocalEmbedder:
    """A Text Embeddings Inference server, reached over HTTP."""

    def __init__(
        self,
        url: str,
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        self._timeout = timeout
        # A test's stand-in for the server; None is the network.
        self._transport = transport
        self._info: EmbedderInfo | None = None
        self._asked_at = float("-inf")
        self._queries: OrderedDict[str, Vector] = OrderedDict()

    @property
    def sends_out(self) -> bool:
        return False

    async def info(self) -> EmbedderInfo | None:
        if time.monotonic() - self._asked_at < _INFO_SECONDS:
            return self._info
        self._asked_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=2.0, transport=self._transport) as client:
                response = await client.get(f"{self._url}/info")
                response.raise_for_status()
                body = response.json()
            self._info = EmbedderInfo(
                model=str(body["model_id"]), max_tokens=int(body.get("max_input_length", 512))
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            self._info = None
        return self._info

    async def queries(self, texts: Sequence[str]) -> list[Vector]:
        missing = [text for text in texts if text not in self._queries]
        if missing:
            for text, vector in zip(
                missing, await self._embed([self._query_prefix + one for one in missing]), strict=True
            ):
                self._queries[text] = vector
                while len(self._queries) > _REMEMBERED_QUERIES:
                    self._queries.popitem(last=False)
        return [self._queries[text] for text in texts]

    async def passages(self, texts: Sequence[str]) -> list[Vector]:
        return await self._embed([self._passage_prefix + one for one in texts])

    async def _embed(self, inputs: list[str]) -> list[Vector]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                f"{self._url}/embed",
                json={"inputs": inputs, "normalize": True, "truncate": True},
            )
            response.raise_for_status()
            vectors: list[Vector] = response.json()
        return vectors


_EMBEDDER: Embedder | None = None


def embedder() -> Embedder | None:
    """The installation's model, or nothing when search by meaning is off.

    One per process: it remembers what the model said of itself and the last
    queries. A test replaces it with `use`.
    """
    global _EMBEDDER
    if _EMBEDDER is None and settings.EMBEDDINGS_URL:
        _EMBEDDER = LocalEmbedder(
            settings.EMBEDDINGS_URL,
            query_prefix=settings.EMBEDDINGS_QUERY_PREFIX,
            passage_prefix=settings.EMBEDDINGS_PASSAGE_PREFIX,
        )
    return _EMBEDDER


def use(replacement: Embedder | None) -> Embedder | None:
    """Put another model in place, answering the one it replaced."""
    global _EMBEDDER
    previous, _EMBEDDER = _EMBEDDER, replacement
    return previous
