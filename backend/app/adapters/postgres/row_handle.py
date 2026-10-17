"""Opaque PostgreSQL row handles passed back by the client unchanged."""

import base64
import json
from dataclasses import dataclass
from typing import Any

from app.core.translation import say


@dataclass(frozen=True)
class PostgresRowHandle:
    keys: list[str]
    version: str


def encode_row_handle(keys: list[str], version: str) -> str:
    raw = json.dumps({"keys": keys, "version": version}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_row_handle(value: str) -> PostgresRowHandle:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        keys = decoded["keys"]
        version = decoded["version"]
        if (
            not isinstance(keys, list)
            or not all(isinstance(item, str) for item in keys)
            or not isinstance(version, str)
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    return PostgresRowHandle(keys=keys, version=version)
