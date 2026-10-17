"""Which element of a key a row is, and what it held when it was read.

A row of a Redis key is not a row of a table: it is a field of a hash, a
position in a list, a member of a set. There is no primary key and no `xmin`,
so a handle carries the element's own name and a fingerprint of what was read
— which is what makes an edit refuse rather than overwrite when somebody else
changed the same field in between (D25's rule, kept by a source that has no
version of its own).

Opaque to the client, like PostgreSQL's: it is passed back unchanged and read
only here.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.core.translation import say

# What a fingerprint is: enough of a digest to tell one value from another,
# and short enough that a page of five hundred handles is not a page of
# hashes. Sixteen hex characters is 64 bits.
FINGERPRINT_LENGTH = 16


@dataclass(frozen=True)
class RedisRowHandle:
    """One element of one key, as it was read.

    `data_type` is carried so that a handle read against a key which has since
    been deleted and written again as another type is refused rather than
    applied to whatever is there now.
    """

    data_type: str
    # What names the element within its key: a field, an index, a member. The
    # empty string for a string key, which has one row and nothing to name.
    identity: str
    fingerprint: str


def fingerprint(*parts: str) -> str:
    """What the row held, as a digest of it.

    The parts are joined with a separator that cannot occur in a digest, so
    two different rows cannot fingerprint alike by their concatenation.
    """
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8", "surrogatepass"))
    return digest.hexdigest()[:FINGERPRINT_LENGTH]


def encode_row_handle(data_type: str, identity: str, *values: str) -> str:
    raw = json.dumps(
        {"t": data_type, "i": identity, "v": fingerprint(*values)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_row_handle(value: str) -> RedisRowHandle:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        data_type = decoded["t"]
        identity = decoded["i"]
        held = decoded["v"]
        if not all(isinstance(one, str) for one in (data_type, identity, held)):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    return RedisRowHandle(data_type=data_type, identity=identity, fingerprint=held)
