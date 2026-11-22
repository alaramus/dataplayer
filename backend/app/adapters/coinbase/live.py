"""A symbol watched live over Coinbase's public streams: the next slice."""

from collections.abc import AsyncGenerator

from app.adapters.coinbase.markets import Market
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.live import LiveRows
from app.core.translation import say


class CoinbaseLive:
    def __init__(self, session: CoinbaseSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        del market, symbol, interval, node_id
        raise ValueError(say("Only a symbol's market is watched live"))
        yield
