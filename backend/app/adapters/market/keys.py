"""An exchange's API key in a connection's options (D322, D431).

A key is a choice of an endpoint of its own rather than an optional field,
for the reason Redis's password is (D16): a `SecretStr | None` is not seen
as a secret by the schema split (D4). Each exchange names its keyed
endpoints as subclasses of this.
"""

from typing import Any

from pydantic import BaseModel, Field, SecretStr

from app.adapters.layout import layout
from app.core.translation import N_


class Keyed(BaseModel):
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


def key_of(options: Any) -> Keyed | None:
    """The key a connection reads its account with, if it has one."""
    return options if isinstance(options, Keyed) else None
