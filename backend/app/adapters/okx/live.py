"""A symbol watched live over OKX's public streams: the next slice."""

from collections.abc import AsyncGenerator

from app.adapters.live import LiveRows
from app.adapters.okx.markets import Market
from app.adapters.okx.session import OkxSession
from app.core.translation import say


class OkxLive:
    def __init__(self, session: OkxSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        del market, symbol, interval, node_id
        raise ValueError(say("Only a symbol's market is watched live"))
        yield
