"""Which OKX a connection speaks to (D432).

The endpoint is a choice of a few rather than a URL, as Binance's and
Bybit's are (D316, D426): each is a host for REST and one for the public
streams. A key is an endpoint of its own, and OKX's key brings a
passphrase beside the key and its secret.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.market.keys import Keyed
from app.core.translation import N_


def _endpoint_field(endpoint: str) -> Any:
    return Field(default=endpoint, title=N_("Endpoint"), json_schema_extra=layout())


class OkxMain(BaseModel):
    """www.okx.com and ws.okx.com."""

    model_config = ConfigDict(extra="forbid", title=N_("OKX"))

    endpoint: Literal["okx"] = _endpoint_field("okx")


class OkxEea(BaseModel):
    """eea.okx.com: OKX's European service, a market of its own."""

    model_config = ConfigDict(extra="forbid", title=N_("OKX Europe"))

    endpoint: Literal["eea"] = _endpoint_field("eea")


class OkxDemo(BaseModel):
    """Demo trading: the main host asked for its demo market."""

    model_config = ConfigDict(extra="forbid", title=N_("Demo trading"))

    endpoint: Literal["demo"] = _endpoint_field("demo")


class OkxKeyed(Keyed):
    api_passphrase: SecretStr = Field(
        title=N_("Passphrase"), min_length=1, json_schema_extra=layout()
    )


class OkxMainKey(OkxKeyed):
    """The main hosts, and the account a key reads."""

    model_config = ConfigDict(extra="forbid", title=N_("OKX, with an API key"))

    endpoint: Literal["okx_key"] = _endpoint_field("okx_key")


class OkxEeaKey(OkxKeyed):
    model_config = ConfigDict(extra="forbid", title=N_("OKX Europe, with an API key"))

    endpoint: Literal["eea_key"] = _endpoint_field("eea_key")


class OkxDemoKey(OkxKeyed):
    model_config = ConfigDict(extra="forbid", title=N_("Demo trading, with an API key"))

    endpoint: Literal["demo_key"] = _endpoint_field("demo_key")


OkxOptions = Annotated[
    OkxMain | OkxMainKey | OkxEea | OkxEeaKey | OkxDemo | OkxDemoKey,
    Field(discriminator="endpoint"),
]

# The hosts an endpoint speaks to; a key changes who asks, not where.
HOSTS_OF: dict[str, str] = {
    "okx": "okx",
    "okx_key": "okx",
    "eea": "eea",
    "eea_key": "eea",
    "demo": "demo",
    "demo_key": "demo",
}
