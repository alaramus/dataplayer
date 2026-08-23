"""The one seam through which an options schema is used.

A schema used to be a single model, and every consumer reached for
`model_json_schema` and `model_fields` directly. Now it may also be a
discriminated union, which has neither, so the question "what does this schema
say" is asked here and nowhere else. Rule D4 lives or quietly dies in
`secret_field_names`: a field declared SecretStr in one variant only must still
be encrypted.
"""

from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.adapters import options


class Plain(BaseModel):
    host: str
    port: int = 5432
    password: SecretStr


class WithPassword(BaseModel):
    model_config = ConfigDict(title="User & Password")

    auth_method: Literal["user_password"] = "user_password"
    host: str
    user: str
    password: SecretStr


class WithCertificate(BaseModel):
    model_config = ConfigDict(title="Certificate")

    auth_method: Literal["certificate"] = "certificate"
    host: str
    certificate: SecretStr


class WithoutAuth(BaseModel):
    model_config = ConfigDict(title="No auth")

    auth_method: Literal["no_auth"] = "no_auth"
    host: str
    user: str


Union = Annotated[
    WithPassword | WithoutAuth,
    Field(discriminator="auth_method"),
]

ThreeWay = Annotated[
    WithPassword | WithCertificate | WithoutAuth,
    Field(discriminator="auth_method"),
]


def test_json_schema_of_a_plain_model_is_the_model_schema() -> None:
    schema = options.json_schema(Plain)

    assert "oneOf" not in schema
    assert set(schema["properties"]) == {"host", "port", "password"}


def test_json_schema_of_a_union_carries_the_variants_and_the_discriminator() -> None:
    schema = options.json_schema(Union)

    assert schema["discriminator"]["propertyName"] == "auth_method"
    assert set(schema["discriminator"]["mapping"]) == {"user_password", "no_auth"}
    assert len(schema["oneOf"]) == 2


def test_a_variant_is_named_by_the_title_its_model_declares() -> None:
    """Without model_config the pick list would offer class names."""
    schema = options.json_schema(Union)

    assert schema["$defs"]["WithPassword"]["title"] == "User & Password"


def test_validate_returns_the_variant_the_discriminator_names() -> None:
    model = options.validate(
        Union,
        {"auth_method": "no_auth", "host": "db", "user": "reader"},
    )

    assert isinstance(model, WithoutAuth)


def test_validate_of_a_plain_model_still_works() -> None:
    model = options.validate(Plain, {"host": "db", "password": "p"})

    assert isinstance(model, Plain)


def test_a_missing_discriminator_is_rejected() -> None:
    """The reason stored connectors need a data migration."""
    with pytest.raises(ValidationError):
        options.validate(Union, {"host": "db", "user": "reader"})


def test_variants_of_a_plain_model_are_the_model_itself() -> None:
    assert options.variants(Plain) == [Plain]


def test_variants_of_a_union_are_its_members_in_order() -> None:
    assert options.variants(ThreeWay) == [WithPassword, WithCertificate, WithoutAuth]


def test_secret_field_names_of_a_plain_model() -> None:
    assert options.secret_field_names(Plain) == {"password"}


def test_secret_field_names_covers_every_variant() -> None:
    """A field secret in one variant only must still reach the blob.

    This is where D4 either holds or breaks without a word: `certificate` is
    declared by one variant out of three, and a name collected from the first
    variant alone would leave it in plaintext in `config`.
    """
    assert options.secret_field_names(ThreeWay) == {"password", "certificate"}


def test_a_schema_answers_the_same_way_twice() -> None:
    """Nothing here may depend on being asked for the first time."""
    assert options.json_schema(Union) == options.json_schema(Union)
    assert options.secret_field_names(Union) == options.secret_field_names(Union)
