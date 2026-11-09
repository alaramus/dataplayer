"""Markets, quote assets, symbols and their feeds as a catalog (D317).

Node ids, colon-separated: `spot`; `spot:tickers`, `spot:symbols`;
`spot:quote:USDT`; `spot:symbol:BTCUSDT`, then `:trades`, `:book`, `:candles`
and `:candles:1h` after it. With a key (D322): `spot:account` and
`spot:account:balances` and its siblings, and a symbol's `:orders` and
`:my_trades`. A symbol never holds a colon (the symbol list
leaves one out), and a symbol a client names is looked up among the
market's before anything is asked of Binance.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.adapters.binance.markets import BY_KEY, MARKETS, Market, market_of
from app.adapters.binance.session import Symbol
from app.adapters.catalog import (
    CatalogNode,
    DirectoryNode,
    FeedName,
    FeedNode,
    SymbolNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.words import worded_titles
from app.core.translation import N_, say

ROWS = NodeRepresentation(kind="table", title=N_("View as table"))
MARKET = NodeRepresentation(kind="market", title=N_("View the market"))

FEED_TITLES: dict[FeedName, str] = {
    "tickers": N_("Tickers"),
    "symbols": N_("Symbols"),
    "candles": N_("Candles"),
    "trades": N_("Trades"),
    "order_book": N_("Order book"),
    "balances": N_("Balances"),
    "positions": N_("Positions"),
    "open_orders": N_("Open orders"),
    "orders": N_("My orders"),
    "my_trades": N_("My trades"),
    "deposits": N_("Deposits"),
    "withdrawals": N_("Withdrawals"),
    "market": N_("Market"),
}

ACCOUNT_TITLE = N_("Account")

# A symbol's own feeds by the last part of their id.
SYMBOL_FEEDS: dict[str, FeedName] = {
    "market": "market",
    "trades": "trades",
    "book": "order_book",
    "orders": "orders",
    "my_trades": "my_trades",
}
# The account's feeds of a market, by the last part of their id.
ACCOUNT_FEEDS: dict[str, FeedName] = {
    "balances": "balances",
    "positions": "positions",
    "open_orders": "open_orders",
    "deposits": "deposits",
    "withdrawals": "withdrawals",
}
# What only a key reads.
PRIVATE: frozenset[FeedName] = frozenset(
    {*ACCOUNT_FEEDS.values(), "orders", "my_trades"}
)


@dataclass(frozen=True)
class Place:
    """What a node id names, before anything is asked of Binance."""

    market: Market
    what: Literal[
        "market", "tickers", "symbols", "quote", "symbol", "candles", "feed", "account"
    ]
    quote: str | None = None
    symbol: str | None = None
    feed: FeedName | None = None
    interval: str | None = None


def place_of(node_id: str) -> Place:
    """The node an id names, or a refusal when it names none of this source."""
    parts = node_id.split(":")
    market = market_of(parts[0])
    if len(parts) == 1:
        return Place(market, "market")
    if len(parts) == 2 and parts[1] in {"tickers", "symbols"}:
        return Place(market, "tickers" if parts[1] == "tickers" else "symbols")
    if len(parts) == 2 and parts[1] == "account":
        return Place(market, "account")
    if len(parts) == 3 and parts[1] == "account" and parts[2] in ACCOUNT_FEEDS:
        return Place(market, "feed", feed=ACCOUNT_FEEDS[parts[2]])
    if len(parts) == 3 and parts[1] == "quote" and parts[2] != "":
        return Place(market, "quote", quote=parts[2])
    if len(parts) >= 3 and parts[1] == "symbol" and parts[2] != "":
        symbol = parts[2]
        if len(parts) == 3:
            return Place(market, "symbol", symbol=symbol)
        if len(parts) == 4 and parts[3] in SYMBOL_FEEDS:
            return Place(market, "feed", symbol=symbol, feed=SYMBOL_FEEDS[parts[3]])
        if len(parts) == 4 and parts[3] == "candles":
            return Place(market, "candles", symbol=symbol)
        if len(parts) == 5 and parts[3] == "candles" and parts[4] in market.intervals:
            return Place(
                market, "feed", symbol=symbol, feed="candles", interval=parts[4]
            )
    raise ValueError(say("Not a node of this connection"))


def market_node(market: Market) -> CatalogNode:
    return DirectoryNode(
        id=market.key, name=say(market.title), has_children=True, representations=[]
    )


def markets() -> list[CatalogNode]:
    return [market_node(BY_KEY[key]) for key in MARKETS]


def feed_node(
    node_id: str, feed: FeedName, name: str | None = None, interval: str | None = None
) -> CatalogNode:
    return FeedNode(
        id=node_id,
        name=name or say(FEED_TITLES[feed]),
        feed=feed,
        interval=interval,
        representations=worded_titles([ROWS]),
    )


def quotes_of(symbols: list[Symbol]) -> list[tuple[str, int]]:
    """Quote assets with how many symbols each, the fullest first."""
    counted = Counter(one.quote for one in symbols)
    return sorted(counted.items(), key=lambda item: (-item[1], item[0]))


def quote_node(market: Market, quote: str) -> CatalogNode:
    return DirectoryNode(
        id=f"{market.key}:quote:{quote}",
        name=quote,
        has_children=True,
        representations=[],
    )


def account_node(market: Market) -> CatalogNode:
    return DirectoryNode(
        id=f"{market.key}:account",
        name=say(ACCOUNT_TITLE),
        has_children=True,
        representations=[],
    )


def account_children(market: Market, feeds: list[FeedName]) -> list[CatalogNode]:
    by_feed = {feed: part for part, feed in ACCOUNT_FEEDS.items()}
    return [feed_node(f"{market.key}:account:{by_feed[feed]}", feed) for feed in feeds]


def market_children(
    market: Market, symbols: list[Symbol], keyed: bool = False
) -> list[CatalogNode]:
    """The market's lists, its account when there is a key, then its quotes."""
    return [
        feed_node(f"{market.key}:tickers", "tickers"),
        feed_node(f"{market.key}:symbols", "symbols"),
        *([account_node(market)] if keyed else []),
        *(quote_node(market, quote) for quote, _ in quotes_of(symbols)),
    ]


def symbol_id(market: Market, name: str) -> str:
    return f"{market.key}:symbol:{name}"


def symbol_node(market: Market, symbol: Symbol) -> CatalogNode:
    return SymbolNode(
        id=symbol_id(market, symbol.name),
        name=symbol.name,
        base=symbol.base,
        quote=symbol.quote,
        contract_type=symbol.contract_type,
        representations=[],
    )


def symbol_children(
    market: Market, name: str, keyed: bool = False
) -> list[CatalogNode]:
    base = symbol_id(market, name)
    own = (
        [
            feed_node(f"{base}:orders", "orders"),
            feed_node(f"{base}:my_trades", "my_trades"),
        ]
        if keyed
        else []
    )
    return [
        FeedNode(
            id=f"{base}:market",
            name=say(FEED_TITLES["market"]),
            feed="market",
            representations=worded_titles([MARKET]),
        ),
        DirectoryNode(
            id=f"{base}:candles",
            name=say(FEED_TITLES["candles"]),
            has_children=True,
            representations=[],
        ),
        feed_node(f"{base}:trades", "trades"),
        feed_node(f"{base}:book", "order_book"),
        *own,
    ]


def candle_nodes(market: Market, name: str) -> list[CatalogNode]:
    base = symbol_id(market, name)
    return [
        feed_node(f"{base}:candles:{interval}", "candles", interval, interval)
        for interval in market.intervals
    ]
