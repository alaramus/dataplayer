"""Which Bybit a connection speaks to (D426).

The endpoint is a choice of a few rather than a URL, as Binance's is (D316):
each is a host for REST and one for the public streams, and a typed address
could only be one of them or wrong. A key comes in a later round as an
endpoint of its own, for the reason Binance's does (D322), so the choice is a
discriminated union from the start.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.layout import layout
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


BybitOptions = Annotated[
    BybitMain | BybitBytick | BybitTestnet,
    Field(discriminator="endpoint"),
]

Endpoint = Literal["bybit", "bytick", "testnet"]
