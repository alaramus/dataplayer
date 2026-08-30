"""Reading and writing JSON without letting a number become a float.

Shared because several representations need the same handling and none may
import another: PostgreSQL selects a `jsonb` column as text, the native JSON
viewer builds a tree, and an explicit file projection builds rows. None may
round `10000000000000001` to `1e16` on the way through, which is what
`json.loads` does on its own.

A number therefore keeps the text it arrived as, and everything is written back
in one canonical compact spelling, so a value is the same string wherever it
crossed the boundary (D23).
"""

import json
from typing import Any


class NonStandardJson(ValueError):
    """A token Python accepts as an extension but JSON does not."""


class JsonNumber:
    """A JSON numeric token that must never become a Python float."""

    def __init__(self, text: str) -> None:
        self.text = text


def load(text: str) -> Any:
    """Parse JSON, leaving every numeric token as a `JsonNumber`.

    Raises `json.JSONDecodeError` or `NonStandardJson`, which the caller is
    expected to turn into an answer of its own: what a source does about text
    it cannot read is not decided here.
    """
    return json.loads(
        text,
        parse_int=JsonNumber,
        parse_float=JsonNumber,
        parse_constant=_reject_constant,
    )


def _reject_constant(token: str) -> None:
    # Python accepts NaN and infinities by default; RFC JSON does not. Raising
    # our own error avoids inventing a source position the decoder did not give.
    raise NonStandardJson(f"{token} is not a JSON number")


def encode(value: Any) -> str:
    """The canonical compact text of a value read by `load`."""
    if isinstance(value, JsonNumber):
        return value.text
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(encode(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{encode(item)}"
                for key, item in value.items()
            )
            + "}"
        )
    raise TypeError("Not a JSON value")


def compact(text: str) -> str:
    """Remove JSON whitespace without parsing numeric tokens as floats."""
    return encode(load(text))
