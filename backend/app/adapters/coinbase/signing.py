"""A Coinbase Developer Platform key's token for one request (D443).

Advanced Trade takes a JWT signed with the key's EC private key (ES256) in
`Authorization: Bearer`: `kid` the key's name, a fresh `nonce`, `iss` "cdp",
`sub` the key's name, valid for two minutes, and `uri` the method, host and
path of this request — the query string left out, as Coinbase's own SDK
builds it. A token is made for each request.
"""

import re
import secrets
import textwrap

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.translation import say

LIFETIME_SECONDS = 120
_PEM = re.compile(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", re.S)


def private_key(text: str) -> ec.EllipticCurvePrivateKey:
    """The key's PEM as pasted: with its line breaks, with them written as
    `\\n`, or with none, as a one-line field leaves it."""
    found = _PEM.search(text.replace("\\n", "\n"))
    if found is None:
        raise ValueError(say("The private key is not a PEM key"))
    kind, body = found.group(1), re.sub(r"\s+", "", found.group(2))
    pem = "\n".join(
        [
            f"-----BEGIN {kind}-----",
            *textwrap.wrap(body, 64),
            f"-----END {kind}-----",
            "",
        ]
    )
    try:
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
    except ValueError, TypeError:
        raise ValueError(say("The private key is not a PEM key")) from None
    if not isinstance(loaded, ec.EllipticCurvePrivateKey):
        raise ValueError(
            say("Coinbase signs with an ECDSA key; make the key with ECDSA")
        )
    return loaded


def token(name: str, secret: str, host: str, path: str, now: int) -> str:
    """The bearer token for a GET of `path` on `host` at `now`, in seconds."""
    return jwt.encode(
        {
            "sub": name,
            "iss": "cdp",
            "nbf": now,
            "exp": now + LIFETIME_SECONDS,
            "uri": f"GET {host}{path}",
        },
        private_key(secret),
        algorithm="ES256",
        headers={"kid": name, "nonce": secrets.token_hex()},
    )
