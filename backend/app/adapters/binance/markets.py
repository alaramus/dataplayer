"""The three markets, as Binance's REST answers them (D316, D321).

Spot, USDⓈ-M and COIN-M futures speak the same language from different hosts, under
different paths, with different weights and ceilings; everything that differs
is written here once, so the rest reads a market rather than asking which.
"""

from dataclasses import dataclass
from typing import Literal

from app.adapters.binance.options import Hosts
from app.core.translation import N_, say

MarketKey = Literal["spot", "usdm", "coinm"]
MARKETS: tuple[MarketKey, ...] = ("spot", "usdm", "coinm")

INTERVAL_MS: dict[str, int] = {
    "1s": 1_000,
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
    # A month is not a fixed span; this is its longest, used only to say how
    # far a page reaches, never to name a candle.
    "1M": 2_678_400_000,
}


@dataclass(frozen=True)
class Market:
    key: MarketKey
    title: str
    # Where its REST paths begin: `/api/v3` or `/fapi/v1`.
    prefix: str
    # What its own `exchangeInfo` says when it says nothing.
    weight_limit: int
    candles_per_request: int
    intervals: tuple[str, ...]
    # The depths `depth` accepts, smallest first.
    depths: tuple[int, ...]
    trades_per_request: int = 1000
    # How far back trades can be asked for at all; spot keeps about two
    # years and answers older ids from its oldest instead of refusing.
    trades_window_ms: int | None = None
    # Whether Binance counts its volumes in contracts of a fixed value in the
    # quote asset rather than in the base asset (D321).
    in_contracts: bool = False
    # Where a key reads its account (D322): balances, positions, own trades.
    account_path: str = "account"
    positions_path: str | None = None
    my_trades_path: str = "userTrades"

    def path(self, name: str) -> str:
        """A name under the market's prefix, or a path of the host's own."""
        return name if name.startswith("/") else f"{self.prefix}/{name}"

    def depth_for(self, levels: int) -> int:
        """The smallest depth Binance accepts that holds this many levels."""
        for depth in self.depths:
            if depth >= levels:
                return depth
        return self.depths[-1]

    def weight(self, name: str, params: dict[str, str]) -> int:
        """What Binance will charge for a request, by its published table."""
        if self.key == "spot":
            return _spot_weight(name, params)
        return _futures_weight(name, params, coin=self.key == "coinm")


def _spot_weight(name: str, params: dict[str, str]) -> int:
    if name == "exchangeInfo":
        return 20
    if name in {"account", "allOrders", "myTrades"}:
        return 20
    if name == "openOrders":
        return 6 if "symbol" in params else 80
    if name == "ticker/24hr":
        return 2 if "symbol" in params else 80
    if name == "klines":
        return 2
    if name == "aggTrades":
        return 4
    if name == "depth":
        limit = int(params.get("limit", "100"))
        if limit <= 100:
            return 5
        if limit <= 500:
            return 25
        if limit <= 1000:
            return 50
        return 250
    return 1


def _futures_weight(name: str, params: dict[str, str], coin: bool) -> int:
    if name == "exchangeInfo":
        return 1
    if name in {"account", "/fapi/v3/account", "/fapi/v3/positionRisk"}:
        return 5
    if name == "positionRisk":
        return 1
    if name == "openOrders":
        return 1 if "symbol" in params else 40
    if name in {"allOrders", "userTrades"}:
        return 20 if coin else 5
    if name == "ticker/24hr":
        return 1 if "symbol" in params else 40
    if name == "klines":
        limit = int(params.get("limit", "500"))
        if limit < 100:
            return 1
        if limit < 500:
            return 2
        if limit <= 1000:
            return 5
        return 10
    if name == "aggTrades":
        return 20
    if name == "depth":
        limit = int(params.get("limit", "500"))
        if limit <= 50:
            return 2
        if limit <= 100:
            return 5
        if limit <= 500:
            return 10
        return 20
    return 1


SPOT = Market(
    key="spot",
    title=N_("Spot"),
    prefix="/api/v3",
    weight_limit=6000,
    candles_per_request=1000,
    intervals=tuple(INTERVAL_MS),
    depths=(5, 10, 20, 50, 100, 500, 1000, 5000),
    my_trades_path="myTrades",
)

USDM = Market(
    key="usdm",
    title=N_("USDⓈ-M futures"),
    prefix="/fapi/v1",
    weight_limit=2400,
    candles_per_request=1500,
    intervals=tuple(name for name in INTERVAL_MS if name != "1s"),
    depths=(5, 10, 20, 50, 100, 500, 1000),
    trades_window_ms=2 * 86_400_000,
    account_path="/fapi/v3/account",
    positions_path="/fapi/v3/positionRisk",
)

COINM = Market(
    key="coinm",
    title=N_("COIN-M futures"),
    prefix="/dapi/v1",
    weight_limit=2400,
    candles_per_request=1500,
    intervals=tuple(name for name in INTERVAL_MS if name != "1s"),
    depths=(5, 10, 20, 50, 100, 500, 1000),
    trades_window_ms=2 * 86_400_000,
    in_contracts=True,
    positions_path="positionRisk",
)

BY_KEY: dict[MarketKey, Market] = {"spot": SPOT, "usdm": USDM, "coinm": COINM}

HOSTS: dict[Hosts, dict[MarketKey, str]] = {
    "binance": {
        "spot": "https://api.binance.com",
        "usdm": "https://fapi.binance.com",
        "coinm": "https://dapi.binance.com",
    },
    "market_data": {
        "spot": "https://data-api.binance.vision",
        "usdm": "https://fapi.binance.com",
        "coinm": "https://dapi.binance.com",
    },
    "testnet": {
        "spot": "https://testnet.binance.vision",
        "usdm": "https://testnet.binancefuture.com",
        "coinm": "https://testnet.binancefuture.com",
    },
}


def market_of(key: str) -> Market:
    for market in (SPOT, USDM, COINM):
        if market.key == key:
            return market
    raise ValueError(say("Not a market of this connection"))
