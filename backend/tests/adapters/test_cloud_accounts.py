"""What a cloud account is declared as, before any provider is installed (D451, D452)."""

import json
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adapters import options as options_schema
from app.adapters.cloud import account_field
from app.adapters.cloud.accounts import (
    AwsAccessKey,
    GcpServiceAccount,
    VaultToken,
    method_of,
    schema_of,
)

KEY = {
    "method": "aws_access_key",
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
}


def _methods(kind: Literal["aws", "gcp", "azure", "vault"], ambient: bool) -> set[str]:
    return {
        str(variant.model_fields["method"].default)
        for variant in options_schema.variants(schema_of(kind, ambient=ambient))
    }


def test_the_server_s_own_identity_is_absent_unless_offered() -> None:
    assert _methods("aws", False) == {"aws_access_key"}
    assert _methods("aws", True) == {"aws_access_key", "aws_default_chain"}
    assert _methods("gcp", False) == {"gcp_service_account"}
    assert _methods("azure", False) == {"azure_service_principal"}
    assert _methods("vault", False) == _methods("vault", True) == {"vault_token", "vault_approle"}


def test_a_kind_with_one_method_left_is_a_plain_form_that_still_names_it() -> None:
    schema = options_schema.json_schema(schema_of("aws", ambient=False))

    assert "oneOf" not in schema
    assert schema["properties"]["method"]["default"] == "aws_access_key"
    assert schema["properties"]["method"]["x-ui-hidden"] is True


def test_the_secrets_of_every_method_are_declared_secret() -> None:
    names = set().union(
        *(
            options_schema.secret_field_names(schema_of(kind, ambient=True))
            for kind in ("aws", "gcp", "azure", "vault")
        )
    )

    assert names == {
        "secret_access_key",
        "session_token",
        "key_json",
        "client_secret",
        "token",
        "secret_id",
    }


def test_a_role_is_an_arn_and_a_session_has_bounds() -> None:
    AwsAccessKey.model_validate(KEY | {"role_arn": "arn:aws:iam::123456789012:role/reader"})

    with pytest.raises(ValidationError):
        AwsAccessKey.model_validate(KEY | {"role_arn": "reader"})
    with pytest.raises(ValidationError):
        AwsAccessKey.model_validate(KEY | {"duration_minutes": 5})


def test_a_google_key_must_be_a_service_account_s() -> None:
    good = json.dumps(
        {"type": "service_account", "client_email": "a@b.iam.gserviceaccount.com", "private_key": "x"}
    )

    GcpServiceAccount.model_validate({"method": "gcp_service_account", "key_json": good})
    with pytest.raises(ValidationError) as refused:
        GcpServiceAccount.model_validate(
            {"method": "gcp_service_account", "key_json": '{"type": "authorized_user", "refresh_token": "s3cret"}'}
        )
    # What the API answers with (`cloud_accounts._refusal`): no input.
    assert "s3cret" not in str(refused.value.errors(include_input=False, include_url=False))


@pytest.mark.parametrize(
    "address",
    ["vault.example.com", "ftp://vault", "https://user:pw@vault", "https://vault/v1/secret", ""],
)
def test_vault_s_address_is_an_origin_and_nothing_else(address: str) -> None:
    with pytest.raises(ValidationError):
        VaultToken.model_validate({"method": "vault_token", "address": address, "token": "t"})


def test_vault_s_address_may_be_on_a_private_network_as_a_database_s_may() -> None:
    found = VaultToken.model_validate(
        {"method": "vault_token", "address": "http://10.0.0.5:8200/", "token": "t"}
    )

    assert found.address == "http://10.0.0.5:8200"


def test_a_method_is_found_by_its_tag() -> None:
    assert method_of("aws_access_key") is AwsAccessKey
    assert method_of("nothing") is None


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "db"


class _Iam(_Base):
    auth_method: Literal["aws_iam"] = "aws_iam"
    account: str = account_field("aws", title="Account")


class _Password(_Base):
    auth_method: Literal["password"] = "password"


def test_a_connection_s_account_fields_are_found_with_their_kind() -> None:
    schema = Annotated[_Iam | _Password, Field(discriminator="auth_method")]

    assert options_schema.cloud_account_names(schema) == {"account": "aws"}
    assert options_schema.cloud_account_names(_Password) == {}
    rendered = options_schema.json_schema(schema)["$defs"]["_Iam"]["properties"]["account"]
    assert rendered["x-ui-purpose"] == "cloud-account"
    assert rendered["x-ui-account-kind"] == "aws"
