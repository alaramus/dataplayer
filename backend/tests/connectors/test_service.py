import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters import registry
from app.adapters.postgres.adapter import PostgresAdapter
from app.connectors import service
from app.core import crypto

OPTIONS = {
    "auth_method": "user_password",
    "host": "db.example.com",
    "port": 6432,
    "database": "analytics",
    "user": "reader",
    "password": "s3cret",
}


def _postgres_type() -> registry.AdapterType:
    return registry.get("postgres")


def test_secret_fields_are_kept_out_of_config() -> None:
    config, _ = service.split_options(_postgres_type(), OPTIONS)

    assert "password" not in config
    assert config == {
        "auth_method": "user_password",
        "host": "db.example.com",
        "port": 6432,
        "database": "analytics",
        "user": "reader",
    }


def test_config_is_json_serialisable() -> None:
    config, _ = service.split_options(_postgres_type(), OPTIONS)

    assert json.loads(json.dumps(config)) == config


def test_secrets_blob_does_not_contain_the_password() -> None:
    _, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert b"s3cret" not in secrets_blob


def test_merge_restores_original_options() -> None:
    config, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert service.merge_options(config, secrets_blob) == OPTIONS


def test_invalid_options_are_rejected() -> None:
    with pytest.raises(ValidationError):
        service.split_options(_postgres_type(), {"host": "only-host"})


def test_fill_missing_secrets_takes_stored_value() -> None:
    adapter_type = _postgres_type()
    _, secrets_blob = service.split_options(adapter_type, OPTIONS)
    incoming = {k: v for k, v in OPTIONS.items() if k != "password"}

    filled = service.fill_missing_secrets(adapter_type, incoming, secrets_blob)

    assert filled["password"] == "s3cret"


def test_fill_missing_secrets_prefers_supplied_value() -> None:
    adapter_type = _postgres_type()
    _, secrets_blob = service.split_options(adapter_type, OPTIONS)
    incoming = {**OPTIONS, "password": "new-password"}

    filled = service.fill_missing_secrets(adapter_type, incoming, secrets_blob)

    assert filled["password"] == "new-password"


def test_build_adapter_returns_driver_instance() -> None:
    context = registry.AdapterContext(home_dir=Path("/data/users/someone"))

    adapter = service.build_adapter(_postgres_type(), OPTIONS, context)

    assert isinstance(adapter, PostgresAdapter)


def test_encrypted_blob_is_readable_only_through_crypto() -> None:
    _, secrets_blob = service.split_options(_postgres_type(), OPTIONS)

    assert json.loads(crypto.decrypt(secrets_blob, purpose="connector")) == {"password": "s3cret"}


# The schema is a union now, and which fields exist depends on the variant. The
# secret split reads every variant, so the question worth asking is not whether
# it finds `password` but whether it stores one only when the chosen variant
# has one.

NO_AUTH_OPTIONS = {
    "auth_method": "no_auth",
    "host": "db.example.com",
    "port": 6432,
    "database": "analytics",
    "user": "reader",
}


def test_the_chosen_variant_decides_what_is_stored() -> None:
    config, _ = service.split_options(_postgres_type(), NO_AUTH_OPTIONS)

    assert config == NO_AUTH_OPTIONS


def test_a_variant_that_carries_no_secret_stores_none() -> None:
    _, secrets_blob = service.split_options(_postgres_type(), NO_AUTH_OPTIONS)

    assert json.loads(crypto.decrypt(secrets_blob, purpose="connector")) == {}


def test_a_password_sent_to_a_variant_without_one_is_not_kept() -> None:
    """Switching to `no auth` must not leave the old password in the blob."""
    _, secrets_blob = service.split_options(
        _postgres_type(), {**NO_AUTH_OPTIONS, "password": "s3cret"}
    )

    assert json.loads(crypto.decrypt(secrets_blob, purpose="connector")) == {}
    assert b"s3cret" not in secrets_blob


def test_options_that_name_no_variant_are_rejected() -> None:
    """The failure the data migration exists to prevent."""
    with pytest.raises(ValidationError):
        service.split_options(
            _postgres_type(), {k: v for k, v in OPTIONS.items() if k != "auth_method"}
        )
