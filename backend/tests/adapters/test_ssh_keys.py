"""What an SSH key is, and the refusals that never quote one (D146)."""

import pytest

from app.adapters.credentials import SigningKey
from app.adapters.ssh import keys
from app.core.translation import in_language


def test_a_key_made_here_is_ed25519_and_says_what_added_it() -> None:
    made = keys.generate("ed25519", None)

    assert made.facts.algorithm == "ssh-ed25519"
    assert made.facts.fingerprint.startswith("SHA256:")
    # The line a person adds to authorized_keys names this application, so the
    # server's owner can tell which line to remove.
    assert made.facts.public_key.startswith("ssh-ed25519 ")
    assert made.facts.public_key.endswith(keys.COMMENT)
    assert not keys.is_encrypted(made.private_key)


def test_a_passphrase_is_what_the_kept_key_is_locked_with() -> None:
    made = keys.generate("ed25519", "correct horse")

    assert keys.is_encrypted(made.private_key)
    assert keys.facts_of(made.private_key, "correct horse") == made.facts


def test_an_encrypted_key_without_its_passphrase_is_asked_for_it() -> None:
    made = keys.generate("ed25519", "correct horse")

    with pytest.raises(keys.KeyNeedsPassphrase):
        keys.imported(made.private_key, None)


def test_a_wrong_passphrase_is_said_without_quoting_the_key() -> None:
    made = keys.generate("ed25519", "correct horse")

    with pytest.raises(ValueError, match="does not open this key") as refused:
        keys.imported(made.private_key, "battery staple")

    assert made.private_key[40:80] not in str(refused.value)


def test_what_is_not_a_key_is_refused_in_our_words() -> None:
    """The library's own message quotes the start of what it could not read."""
    pasted = "-----BEGIN OPENSSH PRIVATE KEY-----\nnot a key at all\n"

    with pytest.raises(ValueError) as refused:
        keys.imported(pasted, None)

    assert str(refused.value) == "This is not a private key this application can read"


def test_a_key_that_arrives_in_the_clear_is_locked_with_the_passphrase_given() -> None:
    """Choosing to be asked protects a key that had no passphrase of its own."""
    clear = keys.generate("ed25519", None)

    kept = keys.imported(clear.private_key, "fresh passphrase")

    assert keys.is_encrypted(kept.private_key)
    assert kept.facts.fingerprint == clear.facts.fingerprint


def test_an_rsa_key_is_there_for_servers_that_refuse_anything_else() -> None:
    made = keys.generate("rsa", None)

    assert made.facts.algorithm == "ssh-rsa"


def test_a_server_key_is_described_from_its_line_and_refused_otherwise() -> None:
    line = keys.generate("ed25519", None).facts.public_key

    assert keys.host_key_facts(line).algorithm == "ssh-ed25519"
    with pytest.raises(ValueError, match="not a server key"):
        keys.host_key_facts("ssh-ed25519 not-base64")


def test_neither_a_signing_key_nor_a_prepared_one_prints_its_secret() -> None:
    """One traceback with a key in a local variable would put it in a log."""
    made = keys.generate("ed25519", "correct horse")
    signing = SigningKey(private_key=made.private_key, passphrase="correct horse")

    assert "correct horse" not in repr(signing)
    assert made.private_key not in repr(signing)
    assert made.private_key not in repr(made)


def test_a_refusal_is_written_in_the_language_asked_for() -> None:
    """D226: the sentence is this repository's, so it has a Russian of its own."""
    pasted = "-----BEGIN OPENSSH PRIVATE KEY-----\nnot a key at all\n"

    def refusal() -> str:
        with pytest.raises(ValueError) as refused:
            keys.imported(pasted, None)
        return str(refused.value)

    assert in_language("ru", refusal) == "Этот закрытый ключ не удаётся прочитать"
