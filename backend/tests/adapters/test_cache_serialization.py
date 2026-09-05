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
from app.adapters.catalog import CatalogNode, SchemaNode, TableNode
from app.adapters.fetch import FetchColumn, FetchResult
from app.adapters.query import ColumnSummary, QueryMetadata, RelationSummary
from app.adapters.relation import ColumnType


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
    assert "{staging}" in first.lru_key
    assert key.request in first.associated_data(key, 3).decode()


@pytest.mark.parametrize("deployment", ["", "has spaces", "a" * 64, ":escape"])
def test_deployment_namespace_is_a_bounded_plain_name(deployment: str) -> None:
    with pytest.raises(ValueError, match="deployment"):
        CacheNamespace(deployment)


def test_a_page_of_rows_survives_the_wire_unchanged() -> None:
    """The format the fetch route actually caches, not a stand-in for it.

    A shared backend rebuilds the answer from JSON while memory hands back the
    object it was given, and D100 says a caller cannot tell which one it is
    talking to. That only holds while every field of the real model survives
    the round trip, so the real model is what is asked.
    """
    page = FetchResult(
        columns=[
            FetchColumn(
                name="id",
                type=ColumnType(sql="bigint", category="number"),
                sortable=True,
                filter_operators=["eq", "gt"],
            ),
            FetchColumn(
                name="tags",
                type=ColumnType(
                    sql="text[]",
                    category="array",
                    element=ColumnType(sql="text", category="string"),
                    dimensions=1,
                ),
                nullable=True,
            ),
        ],
        rows=[["1", "{a,b}"], ["2", None]],
        has_more=True,
        row_handles=["handle-1", None],
        update_supported=True,
        update_reason=None,
        refresh_seconds=5,
        page_commands=["download", "chart"],
    )
    cache_format: CacheFormat[FetchResult] = CacheFormat(FetchResult)

    assert cache_format.decode(cache_format.encode(page)) == page


def test_a_catalog_level_comes_back_as_the_kinds_it_went_in_as() -> None:
    """A discriminated union has to survive as its members, not as a base."""
    level: list[CatalogNode] = [
        SchemaNode(id="public", name="public", has_children=True, representations=[]),
        TableNode(
            id="public.people",
            name="people",
            has_children=False,
            representations=[],
            describable=True,
            row_count_estimate=1200,
        ),
    ]
    cache_format: CacheFormat[list[CatalogNode]] = CacheFormat(list[CatalogNode])

    restored = cache_format.decode(cache_format.encode(level))

    assert restored == level
    assert [type(node) for node in restored] == [SchemaNode, TableNode]


def test_what_the_editor_completes_against_survives_the_wire() -> None:
    metadata = QueryMetadata(
        schemas=["public", "demo_lab"],
        relations=[
            RelationSummary(schema_name="public", name="people", kind="table"),
            RelationSummary(schema_name="public", name="active", kind="view"),
        ],
        columns={
            "public.people": [
                ColumnSummary(name="id", type_sql="bigint"),
                ColumnSummary(name="name", type_sql="text"),
            ]
        },
        complete=False,
    )
    cache_format: CacheFormat[QueryMetadata] = CacheFormat(QueryMetadata)

    assert cache_format.decode(cache_format.encode(metadata)) == metadata
