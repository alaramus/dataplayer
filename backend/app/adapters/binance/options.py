"""Which Binance a connection speaks to, and with what key (D316, D322).

The endpoint is a choice of a few rather than a URL, since each is a set of
hosts — one a market — and a typed address could only be one of them or
wrong. A key is a choice of its own endpoint rather than an optional field,
for the reason Redis's password is (D16): a `SecretStr | None` is not seen
as a secret by the schema split (D4).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

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


class _Keyed(BaseModel):
    # Declared first so the form keeps the endpoint at the top whichever is
    # chosen: a field a subclass narrows keeps the place its parent gave it,
    # and the key's fields would otherwise push the choice down.
    endpoint: str
    api_key: SecretStr = Field(
        title=N_("API key"), min_length=1, json_schema_extra=layout()
    )
    api_secret: SecretStr = Field(
        title=N_("Secret key"), min_length=1, json_schema_extra=layout()
    )


class BinanceMainKey(_Keyed):
    """The main hosts, and the account a key reads (D322)."""

    model_config = ConfigDict(extra="forbid", title=N_("Binance, with an API key"))

    endpoint: Literal["binance_key"] = _endpoint_field("binance_key")


class BinanceTestnetKey(_Keyed):
    model_config = ConfigDict(extra="forbid", title=N_("Testnet, with an API key"))

    endpoint: Literal["testnet_key"] = _endpoint_field("testnet_key")


BinanceOptions = Annotated[
    BinanceMain
    | BinanceMainKey
    | BinanceMarketData
    | BinanceTestnet
    | BinanceTestnetKey,
    Field(discriminator="endpoint"),
]

Endpoint = Literal["binance", "binance_key", "market_data", "testnet", "testnet_key"]
# The set of hosts an endpoint speaks to; a key changes who asks, not where.
Hosts = Literal["binance", "market_data", "testnet"]
HOSTS_OF: dict[Endpoint, Hosts] = {
    "binance": "binance",
    "binance_key": "binance",
    "market_data": "market_data",
    "testnet": "testnet",
    "testnet_key": "testnet",
}


def key_of(options: BinanceOptions) -> _Keyed | None:
    """The key a connection reads its account with, if it has one."""
    return options if isinstance(options, _Keyed) else None
