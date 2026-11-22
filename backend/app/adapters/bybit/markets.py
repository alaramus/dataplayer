"""Bybit's three categories as markets (D426, D427).

Spot, linear (USDT and USDC perpetuals and dated futures) and inverse
(futures settled in the base coin, quoted in USD) answer the same paths under
`/v5/market`, the category a parameter. A market's key is Bybit's category,
so an id says it in Bybit's word.
"""

from dataclasses import dataclass
from typing import Literal

from app.core.translation import N_

MarketKey = Literal["spot", "linear", "inverse"]
MARKETS: tuple[MarketKey, ...] = ("spot", "linear", "inverse")

# The interval names this application shows, and Bybit's word for each.
INTERVALS: dict[str, str] = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}

CANDLES_PER_REQUEST = 1000
# Bybit's book answers any depth up to this a side.
DEEPEST_BOOK = 1000


@dataclass(frozen=True)
class Market:
    key: MarketKey
    title: str
    # The newest trades `recent-trade` answers; it pages nothing.
    trades_per_request: int
    futures: bool
    # Bybit counts `volume` in the quote asset (contracts of 1 USD) and
    # `turnover` in the base asset; elsewhere the other way round (D427).
    volume_in_quote: bool = False
    intervals: tuple[str, ...] = tuple(INTERVALS)
    in_contracts: bool = False
    max_depth: int = DEEPEST_BOOK

    def depth_for(self, levels: int) -> int:
        """Bybit answers any depth it has, so the levels asked are the depth."""
        return min(levels, self.max_depth)


SPOT = Market(key="spot", title=N_("Spot"), trades_per_request=60, futures=False)
LINEAR = Market(
    key="linear",
    title=N_("USDT and USDC futures"),
    trades_per_request=1000,
    futures=True,
)
INVERSE = Market(
    key="inverse",
    title=N_("Inverse futures"),
    trades_per_request=1000,
    futures=True,
    volume_in_quote=True,
)

BY_KEY: dict[str, Market] = {"spot": SPOT, "linear": LINEAR, "inverse": INVERSE}

# Where each endpoint's REST and public streams are.
HOSTS: dict[str, str] = {
    "bybit": "https://api.bybit.com",
    "bytick": "https://api.bytick.com",
    "testnet": "https://api-testnet.bybit.com",
}
STREAM_HOSTS: dict[str, str] = {
    "bybit": "wss://stream.bybit.com",
    "bytick": "wss://stream.bytick.com",
    "testnet": "wss://stream-testnet.bybit.com",
}
