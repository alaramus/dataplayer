"""Symbols found by name and by their assets, and every name for a kept list (D320).

Read from the symbol list the connection keeps, so a search asks Binance for
nothing it has not already read this hour. "btc" finds BTCUSDT by its name
and ETHBTC by its quote asset; a name that matches itself outranks one that
matches by an asset.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.adapters.binance.catalog import market_node, place_of, quote_node, symbol_node
from app.adapters.binance.markets import BY_KEY, MARKETS, Market, MarketKey
from app.adapters.binance.session import BinanceSession, Symbol
from app.adapters.search import (
    Ancestor,
    Kept,
    KeptName,
    MatchClass,
    NameBatch,
    NodeMatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    class_of_name,
    class_rank,
    words_of,
)
from app.core.translation import say


def full_name(symbol: Symbol) -> str:
    """What the words are matched against: the name and both assets."""
    return f"{symbol.name} {symbol.base} {symbol.quote}"


def _class(words: Sequence[str], symbol: Symbol) -> MatchClass | None:
    by_name = class_of_name(words, symbol.name)
    if by_name is not None:
        return by_name
    by_assets = class_of_name(words, full_name(symbol))
    # Found through an asset is never better than a word of the name.
    if by_assets in {"exact", "prefix"}:
        return "word"
    return by_assets


def _ancestors(market: Market, symbol: Symbol) -> list[Ancestor]:
    return [
        Ancestor(node_id=market.key, name=market_node(market).name),
        Ancestor(node_id=quote_node(market, symbol.quote).id, name=symbol.quote),
    ]


def _location(market: Market, symbol: Symbol) -> str:
    return f"{market_node(market).name} / {symbol.quote}"


def _scope(node_id: str | None) -> tuple[tuple[MarketKey, ...], str | None]:
    """The markets a search looks in, and the quote asset it keeps to."""
    if node_id is None:
        return MARKETS, None
    try:
        place = place_of(node_id)
    except ValueError:
        return MARKETS, None
    return (place.market.key,), place.quote


class BinanceSearch:
    def __init__(self, session: BinanceSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        del bounds
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        markets, quote = _scope(request.node_id)
        kept: Kept[tuple[int, int, Market, Symbol]] = Kept(request.limit)
        extent = 0
        # The markets' lists at once: read one after another they took longer
        # than a search waits for a connection.
        lists = await asyncio.gather(
            *(self._session.symbols(BY_KEY[key]) for key in markets)
        )
        for key, symbols in zip(markets, lists, strict=True):
            market = BY_KEY[key]
            for order, symbol in enumerate(symbols):
                if quote is not None and symbol.quote != quote:
                    continue
                extent += 1
                match_class = _class(words, symbol)
                if match_class is not None and kept.wants(match_class):
                    kept.add(
                        match_class, (class_rank(match_class), order, market, symbol)
                    )
        matches = [
            NodeMatch(
                node=symbol_node(market, symbol),
                parent_id=quote_node(market, symbol.quote).id,
                location=_location(market, symbol),
                ancestors=_ancestors(market, symbol),
            )
            for _, _, market, symbol in sorted(
                kept.items(), key=lambda item: (item[0], item[3].name, item[2].key)
            )
        ]
        notice = None
        if kept.dropped:
            notice = say(
                "More than {limit} matched; the best {limit} are shown",
                limit=request.limit,
            )
        return NodeSearchResult(
            matches=matches, complete=notice is None, notice=notice, extent=extent
        )

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every trading symbol of both markets, scoped to its market (D213)."""
        del bounds
        names: list[KeptName] = []
        notice = None
        for key in MARKETS:
            market = BY_KEY[key]
            for symbol in await self._session.symbols(market):
                if len(names) >= limit:
                    notice = say(
                        "More than {limit} names; the first {limit} are kept",
                        limit=f"{limit:,}",
                    )
                    break
                names.append(
                    KeptName(
                        node=symbol_node(market, symbol),
                        parent_id=quote_node(market, symbol.quote).id,
                        location=_location(market, symbol),
                        ancestors=_ancestors(market, symbol),
                        full_name=full_name(symbol),
                        scope=key,
                    )
                )
        yield NameBatch(names=names, notice=notice)
