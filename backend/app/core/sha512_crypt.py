"""SHA-512 crypt (`$6$`), the password hash glibc's crypt writes (D351).

A server that is told its first password only as such a hash — ScyllaDB's
`--auth-superuser-salted-password` — is given one made here. Python 3.13
removed its `crypt` module, and the scheme is short and fixed: Ulrich
Drepper's "Unix crypt using SHA-256 and SHA-512", with the default 5000
rounds, so the result carries no `rounds=`.
"""

import hashlib
import secrets

_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ROUNDS = 5000
_SALT_LENGTH = 16

# Which bytes of the last digest each group of four characters is made of.
_ORDER = (
    (0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26),
    (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51), (31, 52, 10), (53, 11, 32),
    (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57), (37, 58, 16),
    (59, 17, 38), (18, 39, 60), (40, 61, 19), (62, 20, 41),
)  # fmt: skip


def _encoded(first: int, second: int, third: int, count: int) -> str:
    word = (first << 16) | (second << 8) | third
    characters = []
    for _ in range(count):
        characters.append(_ALPHABET[word & 0x3F])
        word >>= 6
    return "".join(characters)


def _repeated(digest: bytes, length: int) -> bytes:
    return (digest * (length // len(digest) + 1))[:length]


def sha512_crypt(password: str, salt: str | None = None) -> str:
    """`$6$salt$hash` of the password; a random salt unless one is given."""
    if salt is None:
        salt = "".join(secrets.choice(_ALPHABET) for _ in range(_SALT_LENGTH))
    key = password.encode("utf-8")
    salted = salt.encode("utf-8")[:_SALT_LENGTH]

    alternate = hashlib.sha512(key + salted + key).digest()
    first = hashlib.sha512(key + salted)
    first.update(_repeated(alternate, len(key)))
    length = len(key)
    while length:
        first.update(alternate if length & 1 else key)
        length >>= 1
    current = first.digest()

    key_bytes = _repeated(hashlib.sha512(key * len(key)).digest(), len(key))
    salt_bytes = _repeated(hashlib.sha512(salted * (16 + current[0])).digest(), len(salted))

    for round_number in range(_ROUNDS):
        step = hashlib.sha512()
        step.update(key_bytes if round_number & 1 else current)
        if round_number % 3:
            step.update(salt_bytes)
        if round_number % 7:
            step.update(key_bytes)
        step.update(current if round_number & 1 else key_bytes)
        current = step.digest()

    text = "".join(_encoded(current[a], current[b], current[c], 4) for a, b, c in _ORDER)
    text += _encoded(0, 0, current[63], 2)
    return f"$6${salted.decode('utf-8')}${text}"
