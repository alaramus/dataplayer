"""A Redis server as a source type: reaching one, and saying why not (D85)."""

import pytest
from pydantic import SecretStr, ValidationError

from app.adapters import options as adapter_options
from app.adapters import registry
from app.adapters.protocol import DataAdapter, SupportsCatalog, SupportsFetch
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.options import RedisNoAuth, RedisPassword


def _unreachable() -> RedisAdapter:
    # Port 1 on the loopback: nothing listens there, and nothing has to be
    # started for the answer to be honest.
    return RedisAdapter(RedisNoAuth(auth_method="no_auth", host="127.0.0.1", port=1))


def test_the_type_is_registered_with_the_options_it_takes() -> None:
    kind = registry.get("redis")

    assert kind.title == "Redis"
    assert kind.adapter_class is RedisAdapter
    # Grouped by what it is rather than by what there was a group for: it has
    # no statements, no relations and no schema.
    assert kind.category == "keyvalue"


def test_what_it_can_do_is_read_off_the_driver() -> None:
    """Which is why an unimplemented capability cannot be claimed by mistake.

    It began as a connection check and nothing else. Browsing, reading and the
    four things one does to a key arrived later, and the catalog said so in
    the same commit — because the list is derived from the driver rather than
    kept beside it.
    """
    adapter = _unreachable()
    assert isinstance(adapter, DataAdapter)
    assert isinstance(adapter, SupportsCatalog)
    assert isinstance(adapter, SupportsFetch)

    titles = [
        item.title for item in registry.capabilities_of(registry.get("redis"))
    ]

    assert "Browse the catalog" in titles
    assert "Read rows" in titles
    # Six ways to write a key rather than one with a type to pick (D91), the
    # three that act on one that exists, and the ordinary editing of what a
    # key already holds.
    assert {
        "New string",
        "New hash",
        "New list",
        "New set",
        "New sorted set",
        "New stream",
        "Delete",
        "Set expiry",
        "Remove expiry",
    } <= set(titles)
    assert {"Edit rows", "Insert rows", "Delete rows"} <= set(titles)
    # Still not a source with statements, relations or a query console.
    assert "Describe a relation" not in titles
    assert "Follow references" not in titles


async def test_a_server_that_is_not_there_is_a_network_answer() -> None:
    result = await _unreachable().check_connection()

    assert result.ok is False
    assert result.error_kind == "network"
    # Not the driver's text: it names the host and port it failed on.
    assert result.message == "Could not reach the Redis server"


def test_a_password_is_a_secret_of_the_schema() -> None:
    """So D4's split encrypts it without being told."""
    secrets = adapter_options.secret_field_names(registry.get("redis").options_schema)

    assert secrets == {"password"}


def test_the_two_ways_of_connecting_are_two_shapes() -> None:
    """A single model with an optional password would be a form that asks for
    something half of its users must leave empty — and a `SecretStr | None`
    that the secret split would not recognise at all."""
    schema = registry.get("redis").options_schema

    with_password = adapter_options.validate(
        schema,
        {
            "auth_method": "password",
            "host": "cache",
            "password": "hunter2",
        },
    )
    without = adapter_options.validate(
        schema, {"auth_method": "no_auth", "host": "cache"}
    )

    assert isinstance(with_password, RedisPassword)
    assert with_password.password == SecretStr("hunter2")
    assert isinstance(without, RedisNoAuth)
    assert without.port == 6379


def test_options_that_name_no_way_of_connecting_are_refused() -> None:
    with pytest.raises(ValidationError):
        adapter_options.validate(
            registry.get("redis").options_schema, {"host": "cache"}
        )


def test_a_form_opens_on_the_commonest_answer() -> None:
    """The same default PostgreSQL has, for the same reason: a server on this
    machine is the commonest case, and a value usually right is worth more than
    a box that always has to be filled in."""
    options = adapter_options.validate(
        registry.get("redis").options_schema, {"auth_method": "no_auth"}
    )

    assert options.host == "localhost"
    assert options.port == 6379
    assert options.database == 0


def test_a_database_outside_the_sixteen_is_refused() -> None:
    with pytest.raises(ValidationError):
        adapter_options.validate(
            registry.get("redis").options_schema,
            {"auth_method": "no_auth", "host": "cache", "database": 99},
        )


async def test_a_server_that_is_not_there_says_nothing_about_its_version() -> None:
    """What it is running is a line on a panel, never a reason to fail."""
    said = await _unreachable().source_features()

    assert said.server_version is None
    # It has none to declare, and answering that is not the same as refusing
    # to answer: a plain server still has a version worth showing.
    assert said.features == []
