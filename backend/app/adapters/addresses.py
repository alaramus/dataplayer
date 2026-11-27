"""An http or https origin a person types: S3's endpoint, Vault's address (D452).

One rule for every outbound address a form names. Any host is allowed, a
private one included, as for a database's host or an SSH server: reaching the
servers of one's own network is what a connection is for. What is refused is
anything but an origin — a key in the address would be stored in clear.
"""

from urllib.parse import urlsplit


def http_origin(value: str, refusal: str) -> str:
    """The origin without a trailing slash, empty kept empty; else ValueError(refusal)."""
    value = value.strip().rstrip("/")
    if value == "":
        return value
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - a port out of range raises here
    except ValueError:
        raise ValueError(refusal) from None
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query != ""
        or parts.fragment != ""
    ):
        raise ValueError(refusal)
    return value
