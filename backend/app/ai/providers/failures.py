"""What a provider's failure means, in words that can be shown (D2c)."""

from typing import Literal

FailureKind = Literal["key_refused", "rate_limited", "not_found", "unavailable"]

SENTENCES: dict[FailureKind, str] = {
    "key_refused": "The provider refused the key",
    "rate_limited": "The provider is limiting requests; try again in a moment",
    "not_found": "The provider does not offer this model to this key",
    "unavailable": "The provider could not be reached",
}

UNKNOWN_FAILURE = "The model could not answer"


def by_status(status: int | None) -> FailureKind | None:
    """What an HTTP status from a provider means, shared by the SDK modules."""
    if status in (401, 403):
        return "key_refused"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 500:
        return "unavailable"
    return None
