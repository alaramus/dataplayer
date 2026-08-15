import base64

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from app.core import crypto
from app.core.config import Settings


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = b'{"password": "s3cret"}'

    restored = crypto.decrypt(crypto.encrypt(plaintext))

    assert restored == plaintext


def test_ciphertext_does_not_contain_plaintext() -> None:
    plaintext = b"very-secret-password"

    payload = crypto.encrypt(plaintext)

    assert plaintext not in payload


def test_same_plaintext_encrypts_to_different_payloads() -> None:
    plaintext = b"same input"

    first = crypto.encrypt(plaintext)
    second = crypto.encrypt(plaintext)

    assert first != second


def test_tampered_payload_is_rejected() -> None:
    payload = bytearray(crypto.encrypt(b"payload"))
    payload[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        crypto.decrypt(bytes(payload))


def test_key_shorter_than_32_bytes_is_rejected() -> None:
    too_short = base64.urlsafe_b64encode(b"x" * 16).decode()

    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(CONNECTOR_SECRET_KEY=too_short)  # type: ignore[call-arg]


def test_key_that_is_not_base64_is_rejected() -> None:
    with pytest.raises(ValidationError, match="base64"):
        Settings(CONNECTOR_SECRET_KEY="not base64 ☃")  # type: ignore[call-arg]
