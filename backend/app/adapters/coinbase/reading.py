"""A symbol's candles and trades read on by a pipeline's link: the next slice."""

from app.adapters.coinbase.markets import Market
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.market.adapter import MarketReading
from app.adapters.reading_on import BookmarkAccess


class CoinbaseReading(MarketReading[Market]):
    def __init__(
        self, session: CoinbaseSession, bookmarks: BookmarkAccess | None
    ) -> None:
        self._session = session
        self._bookmarks = bookmarks

    def reads_on(self, node_id: str) -> bool:
        del node_id
        return False
