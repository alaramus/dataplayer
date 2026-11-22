"""A symbol's candles and trades read on by a pipeline's link: the next slice."""

from app.adapters.market.adapter import MarketReading
from app.adapters.okx.markets import Market
from app.adapters.okx.session import OkxSession
from app.adapters.reading_on import BookmarkAccess


class OkxReading(MarketReading[Market]):
    def __init__(self, session: OkxSession, bookmarks: BookmarkAccess | None) -> None:
        self._session = session
        self._bookmarks = bookmarks

    def reads_on(self, node_id: str) -> bool:
        del node_id
        return False
