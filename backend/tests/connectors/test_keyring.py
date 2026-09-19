"""Passphrases held in this process for a while, and then not (D147)."""

import uuid

import pytest

from app.connectors.keyring import Keyring


def test_a_held_passphrase_is_forgotten_when_its_time_is_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("app.connectors.keyring.time.monotonic", lambda: clock[0])
    key_id = uuid.uuid4()
    keyring = Keyring()

    keyring.unlock(key_id, "for a while", seconds=900)
    clock[0] += 899
    held = keyring.passphrase(key_id)
    clock[0] += 1

    assert held == "for a while"
    assert keyring.passphrase(key_id) is None
    assert keyring.until(key_id) is None


def test_locking_forgets_now_rather_than_when_the_time_is_up() -> None:
    keyring = Keyring()
    key_id = uuid.uuid4()
    keyring.unlock(key_id, "for a while", seconds=900)

    keyring.lock(key_id)

    assert keyring.passphrase(key_id) is None
