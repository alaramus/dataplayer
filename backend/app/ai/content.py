"""The one place conversation text is encrypted and read back (D141)."""

from app.core import crypto


def sealed(text: str) -> bytes:
    return crypto.encrypt(text.encode(), purpose="ai_content")


def opened(payload: bytes) -> str:
    return crypto.decrypt(payload, purpose="ai_content").decode()


def sealed_bytes(data: bytes) -> bytes:
    """A file sent with a message, under the same key as its text (D142)."""
    return crypto.encrypt(data, purpose="ai_content")


def opened_bytes(payload: bytes) -> bytes:
    return crypto.decrypt(payload, purpose="ai_content")
