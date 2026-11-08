"""Which Binance a connection speaks to (D316).

Nothing is secret: public market data asks nobody who they are. The endpoint
is a choice of a few rather than a URL, since each is a pair of hosts — one a
market — and a typed address could only be one of them or wrong.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.layout import layout
from app.core.translation import N_


def _endpoint_field(endpoint: str) -> Any:
    return Field(default=endpoint, title=N_("Endpoint"), json_schema_extra=layout())


class BinanceMain(BaseModel):
    """api.binance.com and fapi.binance.com."""

    model_config = ConfigDict(extra="forbid", title=N_("Binance"))

    endpoint: Literal["binance"] = _endpoint_field("binance")


class BinanceMarketData(BaseModel):
    """Spot from data-api.binance.vision, which serves public data alone."""

    model_config = ConfigDict(extra="forbid", title=N_("Binance, market data only"))

    endpoint: Literal["market_data"] = _endpoint_field("market_data")


class BinanceTestnet(BaseModel):
    model_config = ConfigDict(extra="forbid", title=N_("Testnet"))

    endpoint: Literal["testnet"] = _endpoint_field("testnet")


BinanceOptions = Annotated[
    BinanceMain | BinanceMarketData | BinanceTestnet,
    Field(discriminator="endpoint"),
]

Endpoint = Literal["binance", "market_data", "testnet"]
