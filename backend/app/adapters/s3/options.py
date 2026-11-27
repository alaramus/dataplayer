"""How to reach an S3 store, and with which key (D379).

The keys sign every request and never leave the server: the secret is a
`SecretStr`, encrypted at rest like every other. Where browsing stands — a
bucket and a prefix in it, or every bucket the key may list — is judged by the
containment rule node ids are, so a prefix cannot be a way out of the root.
"""

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.adapters.addresses import http_origin
from app.adapters.cloud.signin import aws_account_field
from app.adapters.explorer.storage import is_plain_name, stays_inside_root
from app.adapters.layout import layout
from app.core.translation import N_, say

# Virtual-hosted on AWS and path everywhere else, which every compatible store
# accepts; the other two say so outright.
Addressing = Literal["auto", "path", "virtual"]

DEFAULT_REGION = "us-east-1"


def _bucket_field() -> Any:
    return Field(
        default="",
        max_length=255,
        title=N_("Bucket"),
        description=N_("Empty shows every bucket this key may list"),
        json_schema_extra=layout(row="bucket"),
    )


def _prefix_field() -> Any:
    return Field(
        default="",
        max_length=1024,
        title=N_("Folder"),
        description=N_("Where browsing starts inside the bucket"),
        json_schema_extra=layout(row="bucket"),
    )


def _addressing_field() -> Any:
    return Field(
        default="auto",
        title=N_("Addressing"),
        description=N_("Auto is virtual-hosted on Amazon S3 and path-style elsewhere"),
        json_schema_extra=layout(row="transport"),
    )


def _verify_field() -> Any:
    return Field(
        default=True,
        title=N_("Verify the certificate"),
        description=N_("Off only for a store with a certificate of its own making"),
        json_schema_extra=layout(row="transport"),
    )


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _S3Base(BaseModel):
    """Where the store is, and the rules every variant's fields keep.

    Bucket, folder and transport are declared by each variant through the
    factories above, after the way of signing in: Pydantic puts a base's
    fields first, and the choice of method belongs under the address. The
    validators name them with `check_fields=False` for that reason.
    """

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(
        default="",
        max_length=512,
        title=N_("Endpoint"),
        description=N_(
            "The store's address, such as https://s3.example.com; empty for Amazon S3"
        ),
        json_schema_extra=layout(row="where"),
    )
    region: str = Field(
        default="",
        max_length=64,
        pattern=r"^[a-z0-9-]*$",
        title=N_("Region"),
        description=N_("Empty is us-east-1"),
        json_schema_extra=layout(row="where"),
    )

    if TYPE_CHECKING:
        # Declared by each variant, after its way of signing in.
        bucket: str
        prefix: str
        addressing: Addressing
        verify_tls: bool

    @field_validator("endpoint")
    @classmethod
    def _an_address(cls, value: str) -> str:
        """An origin and nothing else: the bucket and the folder have their
        own fields, and a key in the address would be stored in clear."""
        return http_origin(value, say("The endpoint must be an http or https address"))

    @field_validator("bucket", check_fields=False)
    @classmethod
    def _one_name(cls, value: str) -> str:
        value = value.strip()
        if value != "" and not is_plain_name(value):
            raise ValueError(say("A bucket is one name, without slashes"))
        return value

    @field_validator("prefix", check_fields=False)
    @classmethod
    def _stays_inside(cls, value: str) -> str:
        """Stored as the keys below it begin, without slashes at either end or
        doubled; the containment rule decides the rest, as it does for a node
        id."""
        value = value.strip().strip("/")
        if not stays_inside_root(value):
            raise ValueError(say("The folder must stay inside the bucket"))
        return "/".join(PurePosixPath(value).parts)

    @model_validator(mode="after")
    def _prefix_in_a_bucket(self) -> Self:
        if self.prefix != "" and self.bucket == "":
            raise ValueError(say("A folder needs the bucket it is in"))
        return self

    @property
    def region_name(self) -> str:
        return self.region or DEFAULT_REGION

    @property
    def path_style(self) -> bool:
        if self.addressing == "auto":
            return self.endpoint != ""
        return self.addressing == "path"


class S3AccessKey(_S3Base):
    """An access key and its secret, as every compatible store gives one."""

    model_config = ConfigDict(title=N_("Access key"))

    auth_method: Literal["access_key"] = _auth_method_field("access_key")
    access_key_id: str = Field(
        min_length=1,
        max_length=256,
        title=N_("Access key"),
        json_schema_extra=layout(),
    )
    secret_access_key: SecretStr = Field(
        title=N_("Secret key"), json_schema_extra=layout()
    )
    bucket: str = _bucket_field()
    prefix: str = _prefix_field()
    addressing: Addressing = _addressing_field()
    verify_tls: bool = _verify_field()


class S3CloudAccount(_S3Base):
    """One of the owner's AWS accounts: a session token, a role to assume or
    this server's own credentials are the account's, not the connection's
    (D451, D453). Its keys are asked again before they expire."""

    model_config = ConfigDict(title=N_("AWS account"))

    auth_method: Literal["aws_account"] = _auth_method_field("aws_account")
    account: str = aws_account_field()
    bucket: str = _bucket_field()
    prefix: str = _prefix_field()
    addressing: Addressing = _addressing_field()
    verify_tls: bool = _verify_field()


S3Options = Annotated[S3AccessKey | S3CloudAccount, Field(discriminator="auth_method")]
