"""Which Coinbase Exchange a connection speaks to (D438).

The endpoint is a choice of a few rather than a URL, as every exchange's is
(D316): the exchange itself, its public sandbox, or the exchange with a
Coinbase Developer Platform key that reads the owner's Coinbase account
through Advanced Trade (D443).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.market.keys import Keyed
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


class CoinbaseKey(Keyed):
    """The exchange's market data, and the account a CDP key reads (D443).

    The key's name and its private key, as Coinbase's developer platform
    gives them; the sandbox has no Advanced Trade, so it has no key.
    """

    model_config = ConfigDict(
        extra="forbid", title=N_("Coinbase Exchange, with an API key")
    )

    endpoint: Literal["coinbase_key"] = _endpoint_field("coinbase_key")
    api_key: SecretStr = Field(
        title=N_("API key name"), min_length=1, json_schema_extra=layout()
    )
    api_secret: SecretStr = Field(
        title=N_("Private key"), min_length=1, json_schema_extra=layout()
    )


CoinbaseOptions = Annotated[
    CoinbaseMain | CoinbaseKey | CoinbaseSandbox, Field(discriminator="endpoint")
]

# The hosts an endpoint speaks to; a key changes who asks, not where.
HOSTS_OF: dict[str, str] = {
    "coinbase": "coinbase",
    "coinbase_key": "coinbase",
    "sandbox": "sandbox",
}
