"""Rows written as keys, each replacing the key it names (D314).

A key per row: its name is a prefix and the row's key value, and it holds the
row's values — one as a string, several as a hash. A write replaces the key
whole, so writing a row twice changes nothing.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# How long a key may be told to live: a second to a year.
MAX_TTL_SECONDS = 365 * 24 * 3600


class KeyedRow(BaseModel):
    """One row: the value naming its key, and its values in the order of
    the request's fields."""

    model_config = ConfigDict(extra="forbid")

    key: str | None
    values: list[str | None]


class KeyedWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A place of the source: a database, or a folder in one.
    place_node_id: str
    prefix: str = Field(default="", max_length=1024)
    # One field is a string key; several are a hash, by these names.
    fields: Annotated[list[str], Field(min_length=1, max_length=100)]
    rows: Annotated[list[KeyedRow], Field(max_length=5000)]
    ttl_seconds: int | None = Field(default=None, ge=1, le=MAX_TTL_SECONDS)


class KeyedWritten(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Writes made: a key named by several rows of the request is written once.
    written: int
    # Rows with no key, or nothing to hold.
    without_key: int = 0
    # Keys holding another type, left as they were.
    other_type: int = 0
