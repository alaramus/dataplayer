"""What the shared layer knows of an exchange's market and its symbols (D425).

Each exchange declares its markets as it likes; the shared code reads them
through `Market`, so a market is spot, futures counted in the base asset, or
futures counted in contracts of a fixed worth, whatever its exchange calls it.
"""

from dataclasses import dataclass
from typing import Protocol

# The candle intervals by the names this application shows, whatever an
# exchange calls them on the wire.
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


class Market(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def intervals(self) -> tuple[str, ...]: ...

    @property
    def futures(self) -> bool:
        """Whether its symbols are contracts, with a type and a delivery."""
        ...

    @property
    def in_contracts(self) -> bool:
        """Whether its symbols list says what one contract is worth (D321)."""
        ...

    @property
    def max_depth(self) -> int:
        """The most levels a side of its book is read to."""
        ...

    def depth_for(self, levels: int) -> int:
        """The depth asked of the exchange for this many levels."""
        ...


@dataclass(frozen=True)
class Symbol:
    """A pair that trades, with the rules an order on it obeys."""

    name: str
    base: str
    quote: str
    status: str
    contract_type: str | None = None
    delivery_ms: int | None = None
    onboard_ms: int | None = None
    price_step: str | None = None
    quantity_step: str | None = None
    min_notional: str | None = None
    # What one contract is worth in the quote asset, on COIN-M (D321).
    contract_size: int | None = None
