"""How a cloud account signs in, declared like a connection's options (D451).

One flat discriminated union per kind, on `method`, so the form that edits a
connection draws an account too and `SecretStr` decides what is encrypted
(D4). A method that lends the identity of the machine running this server is
`ambient` and offered only where the installation allows it (D452).
"""

import json
import re
from functools import reduce
from operator import or_
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.addresses import http_origin
from app.adapters.cloud import AccountKind
from app.adapters.layout import layout
from app.adapters.options import OptionsSchema
from app.adapters.tls import CERTIFICATE, pem
from app.core.translation import N_, say

# Products' own names, the same in every language.
KIND_TITLES: dict[AccountKind, str] = {
    "aws": "Amazon Web Services",
    "gcp": "Google Cloud",
    "azure": "Microsoft Azure",
    "vault": "HashiCorp Vault",
}

_ROLE_ARN = re.compile(r"arn:aws[a-z-]*:iam::\d{12}:role/[\w+=,.@/-]+")
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def _method_field(value: str) -> Any:
    # Hidden where a kind offers one method: the form then has nothing to choose.
    extra = layout()
    extra["x-ui-hidden"] = True
    return Field(default=value, title=N_("Method"), json_schema_extra=extra)


class CloudAccountSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[AccountKind]
    ambient: ClassVar[bool] = False
    method: str


def _region() -> Any:
    return Field(
        default="",
        max_length=64,
        pattern=r"^[a-z0-9-]*$",
        title=N_("Region"),
        description=N_("Where credentials are asked for; empty is us-east-1"),
        json_schema_extra=layout(),
    )


class _AwsRole(BaseModel):
    """A role assumed over the credentials, when one is named.

    Declared after the credentials by each method, so the form reads the
    credentials first: Pydantic orders inherited fields before a class's own.
    """

    role_arn: str = Field(
        default="",
        max_length=2048,
        title=N_("Role to assume"),
        description=N_("Empty signs in as the credentials themselves"),
        examples=["arn:aws:iam::123456789012:role/dataplayer"],
        json_schema_extra=layout(),
    )
    external_id: str = Field(
        default="",
        max_length=1224,
        pattern=r"^[\w+=,.@:/-]*$",
        title=N_("External ID"),
        json_schema_extra=layout(),
    )
    session_name: str = Field(
        default="dataplayer",
        pattern=r"^[\w+=,.@-]{2,64}$",
        title=N_("Session name"),
        json_schema_extra=layout(),
    )
    duration_minutes: int = Field(
        default=60,
        ge=15,
        le=720,
        title=N_("Session length, minutes"),
        json_schema_extra=layout(),
    )

    @field_validator("role_arn")
    @classmethod
    def _an_arn(cls, value: str) -> str:
        value = value.strip()
        if value and _ROLE_ARN.fullmatch(value) is None:
            raise ValueError(say("A role is named by its ARN, such as arn:aws:iam::123456789012:role/name"))
        return value


class _AwsKey(CloudAccountSettings):
    region: str = _region()
    access_key_id: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Z0-9]+$",
        title=N_("Access key"),
        json_schema_extra=layout(),
    )
    secret_access_key: SecretStr = Field(
        min_length=1, max_length=256, title=N_("Secret key"), json_schema_extra=layout()
    )
    session_token: SecretStr = Field(
        default=SecretStr(""),
        max_length=8192,
        title=N_("Session token"),
        description=N_("Only for temporary credentials"),
        json_schema_extra=layout(),
    )


class _AwsChain(CloudAccountSettings):
    region: str = _region()


# The role last in the bases, so its fields come after the credentials'.
class AwsAccessKey(_AwsRole, _AwsKey):
    model_config = ConfigDict(title=N_("Access key"))
    kind = "aws"
    method: Literal["aws_access_key"] = _method_field("aws_access_key")


class AwsDefaultChain(_AwsRole, _AwsChain):
    model_config = ConfigDict(title=N_("This server's credentials"))
    kind = "aws"
    ambient = True
    method: Literal["aws_default_chain"] = _method_field("aws_default_chain")


def _service_account_email() -> Any:
    return Field(
        default="",
        max_length=320,
        pattern=r"^([a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com)?$",
        title=N_("Act as service account"),
        description=N_("Empty signs in as the credentials themselves"),
        json_schema_extra=layout(),
    )


class GcpServiceAccount(CloudAccountSettings):
    model_config = ConfigDict(title=N_("Service account key"))
    kind = "gcp"
    method: Literal["gcp_service_account"] = _method_field("gcp_service_account")
    key_json: SecretStr = Field(
        max_length=16_384,
        title=N_("Key file (JSON)"),
        json_schema_extra=layout(multiline=True),
    )
    impersonate: str = _service_account_email()

    @field_validator("key_json")
    @classmethod
    def _a_key(cls, value: SecretStr) -> SecretStr:
        try:
            parsed = json.loads(value.get_secret_value())
        except ValueError:
            parsed = None
        if not (
            isinstance(parsed, dict)
            and parsed.get("type") == "service_account"
            and isinstance(parsed.get("client_email"), str)
            and isinstance(parsed.get("private_key"), str)
        ):
            raise ValueError(say("This is not a service account's key file"))
        return value


class GcpDefault(CloudAccountSettings):
    model_config = ConfigDict(title=N_("This server's credentials"))
    kind = "gcp"
    ambient = True
    method: Literal["gcp_adc"] = _method_field("gcp_adc")
    impersonate: str = _service_account_email()


class AzureServicePrincipal(CloudAccountSettings):
    model_config = ConfigDict(title=N_("Service principal"))
    kind = "azure"
    method: Literal["azure_service_principal"] = _method_field("azure_service_principal")
    tenant_id: str = Field(
        min_length=1,
        max_length=255,
        pattern=rf"^({_UUID}|[A-Za-z0-9.-]+)$",
        title=N_("Tenant"),
        json_schema_extra=layout(),
    )
    client_id: str = Field(
        pattern=rf"^{_UUID}$", title=N_("Client ID"), json_schema_extra=layout()
    )
    client_secret: SecretStr = Field(
        min_length=1, max_length=1024, title=N_("Client secret"), json_schema_extra=layout()
    )


class AzureDefault(CloudAccountSettings):
    model_config = ConfigDict(title=N_("This server's credentials"))
    kind = "azure"
    ambient = True
    method: Literal["azure_default"] = _method_field("azure_default")
    client_id: str = Field(
        default="",
        pattern=rf"^({_UUID})?$",
        title=N_("Client ID"),
        description=N_("A user-assigned managed identity; empty is the system's"),
        json_schema_extra=layout(),
    )


class _Vault(CloudAccountSettings):
    address: str = Field(
        min_length=1,
        max_length=512,
        title=N_("Address"),
        examples=["https://vault.example.com:8200"],
        json_schema_extra=layout(),
    )
    namespace: str = Field(
        default="",
        max_length=255,
        pattern=r"^[\w./-]*$",
        title=N_("Namespace"),
        json_schema_extra=layout(),
    )
    ca_certificate: str = Field(
        default="",
        max_length=65_536,
        title=N_("CA certificate"),
        description=N_("PEM, when the trusted authority is a certificate of your own"),
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("address")
    @classmethod
    def _an_address(cls, value: str) -> str:
        found = http_origin(value, say("The address must be an http or https address"))
        if found == "":
            raise ValueError(say("The address must be an http or https address"))
        return found

    @field_validator("ca_certificate")
    @classmethod
    def _a_certificate(cls, value: str) -> str:
        if value.strip() == "":
            return ""
        return pem(value, CERTIFICATE, say("Paste a certificate in PEM, BEGIN CERTIFICATE and all"))


class VaultToken(_Vault):
    model_config = ConfigDict(title=N_("Token"))
    kind = "vault"
    method: Literal["vault_token"] = _method_field("vault_token")
    token: SecretStr = Field(
        min_length=1, max_length=4096, title=N_("Token"), json_schema_extra=layout()
    )


class VaultAppRole(_Vault):
    model_config = ConfigDict(title=N_("AppRole"))
    kind = "vault"
    method: Literal["vault_approle"] = _method_field("vault_approle")
    mount: str = Field(
        default="approle",
        max_length=255,
        pattern=r"^[\w-]+(/[\w-]+)*$",
        title=N_("Mount"),
        json_schema_extra=layout(),
    )
    role_id: str = Field(
        min_length=1, max_length=255, title=N_("Role ID"), json_schema_extra=layout()
    )
    secret_id: SecretStr = Field(
        min_length=1, max_length=1024, title=N_("Secret ID"), json_schema_extra=layout()
    )


METHODS: tuple[type[CloudAccountSettings], ...] = (
    AwsAccessKey,
    AwsDefaultChain,
    GcpServiceAccount,
    GcpDefault,
    AzureServicePrincipal,
    AzureDefault,
    VaultToken,
    VaultAppRole,
)
KINDS: tuple[AccountKind, ...] = ("aws", "gcp", "azure", "vault")


def method_of(tag: str) -> type[CloudAccountSettings] | None:
    return next((one for one in METHODS if one.model_fields["method"].default == tag), None)


def _union(models: list[type[CloudAccountSettings]]) -> OptionsSchema:
    if len(models) == 1:
        return models[0]
    return Annotated[reduce(or_, models), Field(discriminator="method")]


# Built once: `app.adapters.options` keeps its validators by identity, so a
# schema made anew per request would make a validator per request.
_SCHEMAS: dict[tuple[AccountKind, bool], OptionsSchema] = {
    (kind, ambient): _union(
        [one for one in METHODS if one.kind == kind and (ambient or not one.ambient)]
    )
    for kind in KINDS
    for ambient in (True, False)
    if [one for one in METHODS if one.kind == kind and (ambient or not one.ambient)]
}


def schema_of(kind: AccountKind, *, ambient: bool) -> OptionsSchema:
    """The methods of a kind, with or without those lending this server's identity."""
    return _SCHEMAS[(kind, ambient)]
