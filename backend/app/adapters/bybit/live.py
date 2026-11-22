"""A symbol watched live over Bybit's public streams: the next slice."""

from collections.abc import AsyncGenerator

from app.adapters.bybit.markets import Market
from app.adapters.bybit.session import BybitSession
from app.adapters.live import LiveRows
from app.core.translation import say


class BybitLive:
    def __init__(self, session: BybitSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        del market, symbol, interval, node_id
        raise ValueError(say("Only a symbol's market is watched live"))
        yield
