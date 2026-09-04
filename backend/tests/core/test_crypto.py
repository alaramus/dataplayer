import base64

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from app.core import crypto
from app.core.config import Settings

PURPOSES: list[crypto.Purpose] = ["connector", "query_content"]


@pytest.mark.parametrize("purpose", PURPOSES)
def test_encrypt_decrypt_roundtrip(purpose: crypto.Purpose) -> None:
    plaintext = b'{"password": "s3cret"}'

    restored = crypto.decrypt(crypto.encrypt(plaintext, purpose=purpose), purpose=purpose)

    assert restored == plaintext


@pytest.mark.parametrize("purpose", PURPOSES)
def test_ciphertext_does_not_contain_plaintext(purpose: crypto.Purpose) -> None:
    plaintext = b"very-secret-password"

    payload = crypto.encrypt(plaintext, purpose=purpose)

    assert plaintext not in payload


def test_same_plaintext_encrypts_to_different_payloads() -> None:
    plaintext = b"same input"

    first = crypto.encrypt(plaintext, purpose="connector")
    second = crypto.encrypt(plaintext, purpose="connector")

    assert first != second


def test_tampered_payload_is_rejected() -> None:
    payload = bytearray(crypto.encrypt(b"payload", purpose="connector"))
    payload[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        crypto.decrypt(bytes(payload), purpose="connector")


def test_one_key_cannot_read_what_the_other_wrote() -> None:
    """The separation is the point: the two keys rotate independently (D63)."""
    payload = crypto.encrypt(b"select 1", purpose="query_content")

    with pytest.raises(InvalidTag):
        crypto.decrypt(payload, purpose="connector")


@pytest.mark.parametrize(
    "field", ["CONNECTOR_SECRET_KEY", "QUERY_CONTENT_KEY", "DATA_CACHE_SECRET_KEY"]
)
def test_key_shorter_than_32_bytes_is_rejected(field: str) -> None:
    too_short = base64.urlsafe_b64encode(b"x" * 16).decode()

    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(**{field: too_short})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field", ["CONNECTOR_SECRET_KEY", "QUERY_CONTENT_KEY", "DATA_CACHE_SECRET_KEY"]
)
def test_key_that_is_not_base64_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="base64"):
        Settings(**{field: "not base64 ☃"})  # type: ignore[arg-type]
