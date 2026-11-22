"""Which Coinbase Exchange a connection speaks to (D438).

The endpoint is a choice of a few rather than a URL, as every exchange's is
(D316): the exchange itself, or its public sandbox.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.layout import layout
from app.core.translation import N_


def _endpoint_field(endpoint: str) -> Any:
    return Field(default=endpoint, title=N_("Endpoint"), json_schema_extra=layout())


class CoinbaseMain(BaseModel):
    """api.exchange.coinbase.com and ws-feed.exchange.coinbase.com."""

    model_config = ConfigDict(extra="forbid", title=N_("Coinbase Exchange"))

    endpoint: Literal["coinbase"] = _endpoint_field("coinbase")


class CoinbaseSandbox(BaseModel):
    model_config = ConfigDict(extra="forbid", title=N_("Sandbox"))

    endpoint: Literal["sandbox"] = _endpoint_field("sandbox")


CoinbaseOptions = Annotated[
    CoinbaseMain | CoinbaseSandbox, Field(discriminator="endpoint")
]
