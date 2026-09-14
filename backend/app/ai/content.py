"""The one place conversation text is encrypted and read back (D141)."""

from app.core import crypto


def sealed(text: str) -> bytes:
    return crypto.encrypt(text.encode(), purpose="ai_content")


def opened(payload: bytes) -> str:
    return crypto.decrypt(payload, purpose="ai_content").decode()
