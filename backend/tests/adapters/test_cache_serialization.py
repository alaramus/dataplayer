import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.adapters.cache import CacheKey
from app.adapters.cache_serialization import (
    WIRE_HEADER,
    CacheCipher,
    CacheFormat,
    CacheNamespace,
    CacheSerializationError,
)


def cache_key(request: str = '{"node_id":"public.people"}') -> CacheKey:
    return CacheKey(
        owner_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        connector_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        area="fetch",
        request=request,
    )


def test_round_trips_only_the_declared_shape() -> None:
    cache_format: CacheFormat[list[int]] = CacheFormat(list[int])

    encoded = cache_format.encode([1, 2, 3])

    assert encoded.startswith(WIRE_HEADER)
    assert cache_format.decode(encoded) == [1, 2, 3]
    with pytest.raises(CacheSerializationError, match="invalid shape"):
        cache_format.decode(CacheFormat(str).encode("not a list"))


def test_unknown_wire_version_is_a_miss_instead_of_guessed() -> None:
    cache_format: CacheFormat[str] = CacheFormat(str)
    encoded = bytearray(cache_format.encode("answer"))
    encoded[len(WIRE_HEADER) - 1] += 1

    with pytest.raises(CacheSerializationError, match="unsupported version"):
        cache_format.decode(bytes(encoded))


def test_cache_cipher_hides_values_and_binds_the_exact_key() -> None:
    cipher = CacheCipher(b"x" * 32)
    plaintext = b'sensitive customer name: Ada'

    payload = cipher.encrypt(plaintext, associated_data=b"exact key one")

    assert plaintext not in payload
    assert cipher.decrypt(payload, associated_data=b"exact key one") == plaintext
    with pytest.raises(InvalidTag):
        cipher.decrypt(payload, associated_data=b"exact key two")


def test_namespace_separates_deployments_users_and_exact_requests() -> None:
    first = CacheNamespace("staging")
    other_deployment = CacheNamespace("production")
    key = cache_key()
    other_user = CacheKey(uuid.uuid4(), key.connector_id, key.area, key.request)
    other_request = cache_key('{"node_id":"public.orders"}')

    names = {
        first.value_key(key, 3),
        other_deployment.value_key(key, 3),
        first.value_key(other_user, 3),
        first.value_key(other_request, 3),
    }

    assert len(names) == 4
    assert f":user:{key.owner_id}:" in first.value_key(key, 3)
    assert key.request in first.associated_data(key, 3).decode()


@pytest.mark.parametrize("deployment", ["", "has spaces", "a" * 64, ":escape"])
def test_deployment_namespace_is_a_bounded_plain_name(deployment: str) -> None:
    with pytest.raises(ValueError, match="deployment"):
        CacheNamespace(deployment)
