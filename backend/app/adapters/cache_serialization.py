"""Typed, versioned cache values and Redis names (D101)."""

import hashlib
import os
import re
import uuid
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import TypeAdapter, ValidationError

from app.adapters.cache import CacheKey

WIRE_MAGIC = b"DP-CACHE\x00"
WIRE_VERSION = 1
WIRE_HEADER = WIRE_MAGIC + bytes([WIRE_VERSION])
_DEPLOYMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
NONCE_SIZE = 12


class CacheSerializationError(ValueError):
    """A remote value is not a cache value this server can safely read."""


class CacheCipher:
    """Seal disposable cache bytes under the cache-only key."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("cache encryption key must be exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> bytes:
        nonce = os.urandom(NONCE_SIZE)
        return nonce + self._cipher.encrypt(nonce, plaintext, associated_data)

    def decrypt(self, payload: bytes, *, associated_data: bytes) -> bytes:
        if len(payload) <= NONCE_SIZE:
            raise CacheSerializationError("Encrypted cache value is truncated")
        nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
        return self._cipher.decrypt(nonce, ciphertext, associated_data)


class CacheFormat[T]:
    """The closed response type a cache entry must contain."""

    def __init__(self, schema: Any) -> None:
        self._adapter: TypeAdapter[T] = TypeAdapter(schema)

    def encode(self, value: T) -> bytes:
        return WIRE_HEADER + self._adapter.dump_json(value)

    def decode(self, payload: bytes) -> T:
        if not payload.startswith(WIRE_MAGIC):
            raise CacheSerializationError("Cache value has no DataPlayer header")
        if not payload.startswith(WIRE_HEADER):
            raise CacheSerializationError("Cache value uses an unsupported version")
        try:
            return self._adapter.validate_json(payload[len(WIRE_HEADER) :])
        except ValidationError as failure:
            raise CacheSerializationError("Cache value has an invalid shape") from failure


class CacheNamespace:
    """Names belonging to one deployment of the shared cache."""

    def __init__(self, deployment: str) -> None:
        if not _DEPLOYMENT.fullmatch(deployment):
            raise ValueError(
                "deployment must be 1-63 letters, digits, dots, dashes or underscores"
            )
        self._deployment = deployment
        self._prefix = f"dataplayer:{deployment}:cache:v{WIRE_VERSION}"

    @property
    def invalidation_channel(self) -> str:
        return f"{self._prefix}:invalidate"

    def generation_key(self, connector_id: uuid.UUID) -> str:
        # Connector ids are globally unique and invalidation crosses every
        # grantee. User scoping belongs on values, not this shared generation.
        return f"{self._prefix}:connector:{connector_id}:generation"

    @property
    def values_prefix(self) -> str:
        return self._prefix

    def value_key(self, key: CacheKey, generation: int) -> str:
        request_digest = hashlib.sha256(key.request.encode()).hexdigest()
        return (
            f"{self._prefix}:user:{key.owner_id}:connector:{key.connector_id}:"
            f"generation:{generation}:{key.area}:{request_digest}"
        )

    def associated_data(self, key: CacheKey, generation: int) -> bytes:
        """The exact key authenticated with a value before it is accepted."""
        return b"\x00".join(
            (
                self.value_key(key, generation).encode(),
                key.request.encode(),
            )
        )
