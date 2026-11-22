"""Coinbase Exchange's one market (D438, D439).

Coinbase Exchange trades spot only, so the source has one market. Its key is
`spot`, as on every other exchange, so a node id reads the same.
"""

from dataclasses import dataclass
from typing import Literal

from app.core.translation import N_

MarketKey = Literal["spot"]
MARKETS: tuple[MarketKey, ...] = ("spot",)

# The interval names this application shows, and Coinbase's granularity in
# seconds for each; it has no other.
INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}

CANDLES_PER_REQUEST = 300
TRADES_PER_REQUEST = 1000
# Coinbase answers the whole book; a side is cut to this many levels.
DEEPEST_BOOK = 1000


@dataclass(frozen=True)
class Market:
    key: MarketKey
    title: str
    futures: bool = False
    in_contracts: bool = False
    intervals: tuple[str, ...] = tuple(INTERVALS)
    max_depth: int = DEEPEST_BOOK

    def depth_for(self, levels: int) -> int:
        """Coinbase answers the whole book whatever is asked."""
        return min(levels, self.max_depth)


SPOT = Market(key="spot", title=N_("Spot"))

BY_KEY: dict[str, Market] = {"spot": SPOT}

HOSTS: dict[str, str] = {
    "coinbase": "https://api.exchange.coinbase.com",
    "sandbox": "https://api-public.sandbox.exchange.coinbase.com",
}
STREAM_HOSTS: dict[str, str] = {
    "coinbase": "wss://ws-feed.exchange.coinbase.com",
    "sandbox": "wss://ws-feed-public.sandbox.exchange.coinbase.com",
}
