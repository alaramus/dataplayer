"""What a provider's failure means, in words that can be shown (D2c)."""

from typing import Any, Literal

FailureKind = Literal["key_refused", "no_credits", "rate_limited", "not_found", "unavailable"]

SENTENCES: dict[FailureKind, str] = {
    "key_refused": "The provider refused the key",
    "no_credits": "The provider reported insufficient credits or quota — add funds, check the plan, or try another model",
    "rate_limited": "The provider is limiting requests; try again in a moment",
    "not_found": "The provider does not offer this model to this key",
    # A 5xx is an answer: the provider was reached and is down or overloaded
    # ("high demand" from Gemini), which "could not be reached" misstated.
    "unavailable": "The provider is unavailable or overloaded right now; try again in a moment",
}

UNKNOWN_FAILURE = "The model could not answer"

# Words inside a provider's code, type or message that mean the account ran
# out of money or quota rather than being throttled. Matched against the
# SDK's structured fields first; the free-form message only as a fallback.
# "limit" alone is deliberately absent: a plain rate limit is not billing.
_BILLING_HINTS = (
    "insufficient",
    "credit",
    "quota",
    "billing",
    "balance",
    "payment",
    "overdue",
    "trial",
)


def _mentions_billing(*values: object) -> bool:
    haystack = " ".join(str(value).lower() for value in values if value)
    return any(hint in haystack for hint in _BILLING_HINTS)


def classify(
    status: int | None,
    code: object = None,
    error_type: object = None,
    message: object = None,
) -> FailureKind | None:
    """What a provider failure means from its status and error details.

    Billing takes precedence over throttling: OpenAI answers an empty
    balance with 429 `insufficient_quota`, Anthropic with 400 mentioning
    the credit balance, others with 402 — none of which "try again in a
    moment" describes. Only the kind crosses to the caller (D2c); the
    provider's own text never does.
    """
    if status == 402 or (
        status in (400, 403, 429) and _mentions_billing(code, error_type, message)
    ):
        return "no_credits"
    return by_status(status)


def from_parts(status: int | None, body: Any, message: object = None) -> FailureKind | None:
    """Classify from an SDK error's raw body, whatever shape it arrived in.

    OpenAI- and Anthropic-shaped bodies carry `{"error": {...}}` or a flat
    `{"code", "type", "message"}`; anything else falls back to the status
    alone rather than raising on an unexpected shape.
    """
    code: object = None
    error_type: object = None
    text: object = message
    node = body.get("error") if isinstance(body, dict) else None
    if not isinstance(node, dict):
        node = body if isinstance(body, dict) else {}
    if isinstance(node, dict):
        code = node.get("code", code)
        error_type = node.get("type", error_type)
        if text is None:
            text = node.get("message")
    return classify(status, code, error_type, text)


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
