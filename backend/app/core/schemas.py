from datetime import UTC, datetime

from pydantic_core import ErrorDetails
from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def refusal_sentence(error: ErrorDetails) -> str:
    """A validation error's message as a person reads it: a validator's own
    sentence without the "Value error, " Pydantic puts before it."""
    return str(error["msg"]).removeprefix("Value error, ")


# Generic message
class Message(SQLModel):
    message: str
