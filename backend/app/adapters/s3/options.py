"""How to reach an S3 store, and with which key (D379).

The keys sign every request and never leave the server: the secret is a
`SecretStr`, encrypted at rest like every other. Where browsing stands — a
bucket and a prefix in it, or every bucket the key may list — is judged by the
containment rule node ids are, so a prefix cannot be a way out of the root.
"""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.adapters.addresses import http_origin
from app.adapters.explorer.storage import is_plain_name, stays_inside_root
from app.adapters.layout import layout
from app.core.translation import N_, say

# Virtual-hosted on AWS and path everywhere else, which every compatible store
# accepts; the other two say so outright.
Addressing = Literal["auto", "path", "virtual"]

DEFAULT_REGION = "us-east-1"


class S3Options(BaseModel):
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
    access_key_id: str = Field(
        min_length=1,
        max_length=256,
        title=N_("Access key"),
        json_schema_extra=layout(),
    )
    secret_access_key: SecretStr = Field(
        title=N_("Secret key"), json_schema_extra=layout()
    )
    bucket: str = Field(
        default="",
        max_length=255,
        title=N_("Bucket"),
        description=N_("Empty shows every bucket this key may list"),
        json_schema_extra=layout(row="bucket"),
    )
    prefix: str = Field(
        default="",
        max_length=1024,
        title=N_("Folder"),
        description=N_("Where browsing starts inside the bucket"),
        json_schema_extra=layout(row="bucket"),
    )
    addressing: Addressing = Field(
        default="auto",
        title=N_("Addressing"),
        description=N_("Auto is virtual-hosted on Amazon S3 and path-style elsewhere"),
        json_schema_extra=layout(row="transport"),
    )
    verify_tls: bool = Field(
        default=True,
        title=N_("Verify the certificate"),
        description=N_("Off only for a store with a certificate of its own making"),
        json_schema_extra=layout(row="transport"),
    )

    @field_validator("endpoint")
    @classmethod
    def _an_address(cls, value: str) -> str:
        """An origin and nothing else: the bucket and the folder have their
        own fields, and a key in the address would be stored in clear."""
        return http_origin(value, say("The endpoint must be an http or https address"))

    @field_validator("bucket")
    @classmethod
    def _one_name(cls, value: str) -> str:
        value = value.strip()
        if value != "" and not is_plain_name(value):
            raise ValueError(say("A bucket is one name, without slashes"))
        return value

    @field_validator("prefix")
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
    def _prefix_in_a_bucket(self) -> S3Options:
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
