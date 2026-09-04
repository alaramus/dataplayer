"""A Redis address, written and read back (D91).

Both directions against each other, because that is the failure this file
exists to prevent: an address composed in one place and parsed in another
drifts, and it drifts in the quoting first.
"""

import pytest

from app.adapters import registry
from app.adapters.protocol import (
    ComposesSecretUrl,
    DescribesDraft,
    ParsesConnectionString,
    SupportsConnectionString,
)
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.url import (
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from tests.utils.keyspace import redis_options


def test_the_type_says_it_can_write_and_read_an_address() -> None:
    """Read off the driver, so a screen cannot offer a field nothing fills."""
    adapter = RedisAdapter(redis_options())

    assert isinstance(adapter, SupportsConnectionString)
    assert issubclass(RedisAdapter, ParsesConnectionString)
    assert issubclass(RedisAdapter, DescribesDraft)
    assert issubclass(RedisAdapter, ComposesSecretUrl)
    assert registry.get("redis").adapter_class is RedisAdapter


def test_an_address_is_written_with_as_much_as_there_is() -> None:
    assert compose_url(host="cache") == "redis://cache"
    assert compose_url(host="cache", port=6379) == "redis://cache:6379"
    assert compose_url(host="cache", port=6379, database=3) == "redis://cache:6379/3"
    # Zero is a database, not an absent one.
    assert compose_url(host="cache", database=0) == "redis://cache/0"


def test_the_address_shown_never_carries_the_password() -> None:
    """It is on a screen and pasted into other tools."""
    adapter = RedisAdapter(redis_options())

    assert "@" not in adapter.connection_string()


def test_the_one_that_does_carry_it_quotes_it() -> None:
    """A generated password may hold a character with meaning in a URL, and
    the one window that shows one shows an address to paste (D89)."""
    written = compose_url_with_password(
        host="127.0.0.1", port=6380, database=0, password="a/b:c@d"
    )

    assert written == "redis://:a%2Fb%3Ac%40d@127.0.0.1:6380/0"
    assert options_from_url(written)["password"] == "a/b:c@d"
    assert options_from_url(written)["auth_method"] == "password"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "redis://cache",
            {"host": "cache", "port": 6379, "database": 0, "auth_method": "no_auth"},
        ),
        (
            "redis://cache:6380/7",
            {"host": "cache", "port": 6380, "database": 7, "auth_method": "no_auth"},
        ),
        (
            # Both spellings of the database exist in the wild.
            "redis://cache:6380?db=4",
            {"host": "cache", "port": 6380, "database": 4, "auth_method": "no_auth"},
        ),
        (
            "redis://:secret@cache:6380/1",
            {
                "host": "cache",
                "port": 6380,
                "database": 1,
                "auth_method": "password",
                "password": "secret",
            },
        ),
        (
            # A user is accepted and dropped: this source connects as the
            # default user, and refusing would refuse what most tools write.
            "redis://default:secret@cache/2",
            {
                "host": "cache",
                "port": 6379,
                "database": 2,
                "auth_method": "password",
                "password": "secret",
            },
        ),
    ],
)
def test_an_address_is_taken_apart_into_the_fields_of_the_form(
    url: str, expected: dict[str, object]
) -> None:
    """Which way of connecting a string describes is the driver's inference."""
    assert options_from_url(url) == expected


@pytest.mark.parametrize(
    ("url", "says"),
    [
        ("postgresql://cache", "not a Redis connection string"),
        ("redis://", "names no host"),
        ("", "not a Redis connection string"),
        ("redis://cache/99", "between 0 and 15"),
        ("redis://cache/main", "no usable database"),
        # Recognised rather than treated as a stranger, so that pasting one
        # gets an answer about what is missing instead of a plaintext
        # connection nobody asked for.
        ("rediss://cache", "does not do TLS"),
    ],
)
def test_a_string_that_is_not_an_address_says_what_is_wrong(
    url: str, says: str
) -> None:
    with pytest.raises(ValueError) as refusal:
        options_from_url(url)

    assert says in str(refusal.value)


def test_a_half_typed_form_still_has_an_address() -> None:
    """The point of a draft address is to show as much of it as there is."""
    assert RedisAdapter.draft_connection_string({"host": ""}) is None
    assert RedisAdapter.draft_connection_string({}) is None
    assert (
        RedisAdapter.draft_connection_string({"host": "cache", "port": "63"})
        == "redis://cache:63"
    )
    assert (
        RedisAdapter.draft_connection_string({"host": "cache", "port": "not a port"})
        == "redis://cache"
    )
