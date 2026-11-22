"""Which Bybit a connection speaks to (D426).

The endpoint is a choice of a few rather than a URL, as Binance's is (D316):
each is a host for REST and one for the public streams, and a typed address
could only be one of them or wrong. The choice is a
discriminated union: a key is an endpoint of its own, as Binance's is (D322,
D431).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.layout import layout
from app.adapters.market.keys import Keyed
from app.core.translation import N_


def _endpoint_field(endpoint: str) -> Any:
    return Field(default=endpoint, title=N_("Endpoint"), json_schema_extra=layout())


class BybitMain(BaseModel):
    """api.bybit.com and stream.bybit.com."""

    model_config = ConfigDict(extra="forbid", title=N_("Bybit"))

    endpoint: Literal["bybit"] = _endpoint_field("bybit")


class BybitBytick(BaseModel):
    """api.bytick.com: the same service under a second name."""

    model_config = ConfigDict(extra="forbid", title=N_("Bybit, through bytick.com"))

    endpoint: Literal["bytick"] = _endpoint_field("bytick")


class BybitTestnet(BaseModel):
    model_config = ConfigDict(extra="forbid", title=N_("Testnet"))

    endpoint: Literal["testnet"] = _endpoint_field("testnet")


class BybitMainKey(Keyed):
    """The main hosts, and the unified account a key reads (D431)."""

    model_config = ConfigDict(extra="forbid", title=N_("Bybit, with an API key"))

    endpoint: Literal["bybit_key"] = _endpoint_field("bybit_key")


class BybitTestnetKey(Keyed):
    model_config = ConfigDict(extra="forbid", title=N_("Testnet, with an API key"))

    endpoint: Literal["testnet_key"] = _endpoint_field("testnet_key")


BybitOptions = Annotated[
    BybitMain | BybitMainKey | BybitBytick | BybitTestnet | BybitTestnetKey,
    Field(discriminator="endpoint"),
]

Endpoint = Literal["bybit", "bybit_key", "bytick", "testnet", "testnet_key"]
# The hosts an endpoint speaks to; a key changes who asks, not where.
HOSTS_OF: dict[str, str] = {
    "bybit": "bybit",
    "bybit_key": "bybit",
    "bytick": "bytick",
    "testnet": "testnet",
    "testnet_key": "testnet",
}
