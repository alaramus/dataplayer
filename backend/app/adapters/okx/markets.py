"""OKX's instruments as three markets (D432, D433).

OKX sorts instruments by type — SPOT, SWAP (perpetual), FUTURES (dated) —
and each contract by whether it is linear (margined and counted in a
stablecoin, its contract worth some of the base coin) or inverse (margined
in the coin, its contract worth a whole number of USD). The markets here
follow the second, as Bybit's do: spot, linear and inverse, each derivative
market holding OKX's perpetuals and dated futures alike. A market's key is
OKX's own word for its contracts.
"""

from dataclasses import dataclass
from typing import Literal

from app.core.translation import N_

MarketKey = Literal["spot", "linear", "inverse"]
MARKETS: tuple[MarketKey, ...] = ("spot", "linear", "inverse")

# The interval names this application shows, and OKX's word for each. A day
# and longer, and six and twelve hours, are asked opening at UTC midnight:
# OKX's plain `1D` opens at Hong Kong's.
INTERVALS: dict[str, str] = {
    "1s": "1s",
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6Hutc",
    "12h": "12Hutc",
    "1d": "1Dutc",
    "3d": "3Dutc",
    "1w": "1Wutc",
    "1M": "1Mutc",
}

CANDLES_PER_REQUEST = 300
TRADES_PER_REQUEST = 100
# OKX's book answers any depth up to this a side.
DEEPEST_BOOK = 400


@dataclass(frozen=True)
class Market:
    key: MarketKey
    title: str
    # OKX's instrument types the market is read from.
    inst_types: tuple[str, ...]
    futures: bool
    # Inverse contracts are a whole number of USD each (D321).
    in_contracts: bool = False
    intervals: tuple[str, ...] = tuple(INTERVALS)
    max_depth: int = DEEPEST_BOOK

    def depth_for(self, levels: int) -> int:
        """OKX answers any depth it has, so the levels asked are the depth."""
        return min(levels, self.max_depth)


SPOT = Market(key="spot", title=N_("Spot"), inst_types=("SPOT",), futures=False)
LINEAR = Market(
    key="linear",
    title=N_("USDT and USDC futures"),
    inst_types=("SWAP", "FUTURES"),
    futures=True,
)
INVERSE = Market(
    key="inverse",
    title=N_("Inverse futures"),
    inst_types=("SWAP", "FUTURES"),
    futures=True,
    in_contracts=True,
)

BY_KEY: dict[str, Market] = {"spot": SPOT, "linear": LINEAR, "inverse": INVERSE}

# Where each set of hosts has its REST and public streams.
HOSTS: dict[str, str] = {
    "okx": "https://www.okx.com",
    "eea": "https://eea.okx.com",
    # Demo trading is the main host with a header saying so.
    "demo": "https://www.okx.com",
}
STREAM_HOSTS: dict[str, str] = {
    "okx": "wss://ws.okx.com",
    "eea": "wss://wseea.okx.com",
    "demo": "wss://wspap.okx.com",
}
