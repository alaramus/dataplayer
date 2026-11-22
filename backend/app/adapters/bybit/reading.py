"""A symbol's candles and trades read on by a pipeline's link: the next slice."""

from app.adapters.bybit.markets import Market
from app.adapters.bybit.session import BybitSession
from app.adapters.market.adapter import MarketReading
from app.adapters.reading_on import BookmarkAccess


class BybitReading(MarketReading[Market]):
    def __init__(self, session: BybitSession, bookmarks: BookmarkAccess | None) -> None:
        self._session = session
        self._bookmarks = bookmarks

    def reads_on(self, node_id: str) -> bool:
        del node_id
        return False
