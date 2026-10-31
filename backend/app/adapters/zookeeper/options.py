"""How to reach a ZooKeeper server, and who is asking (D297).

The flat union MySQL and MongoDB have, for the same reason (D16): a digest
user and an anonymous session are different sets of fields. A ZooKeeper
ensemble is reached through one of its servers; the rest of it answers through
that one.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.layout import layout
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_, say


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


def chroot_problem(chroot: str) -> str | None:
    """Why a chroot is not a path ZooKeeper would accept, or nothing."""
    if chroot == "":
        return None
    if not chroot.startswith("/") or chroot.endswith("/"):
        return say("A root path starts with / and does not end with one")
    if any(part in {"", ".", ".."} for part in chroot[1:].split("/")):
        return say("A root path has no empty, . or .. parts")
    return None


class _ZookeeperBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=2181,
        title=N_("Port"),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    # A confinement, unlike a database elsewhere: ZooKeeper's client resolves
    # every path under it, and nothing above it is reachable (D297).
    chroot: str = Field(
        default="",
        title=N_("Root path"),
        description=N_(
            "Everything is read under this path, as if it were the top; empty for the whole tree"
        ),
        json_schema_extra=layout(),
    )
    tls: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("Encrypted, with the server's certificate verified"),
        json_schema_extra=layout(),
    )
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()

    @field_validator("chroot")
    @classmethod
    def _chroot_is_a_path(cls, chroot: str) -> str:
        problem = chroot_problem(chroot)
        if problem is not None:
            raise ValueError(problem)
        return chroot


class ZookeeperDigest(_ZookeeperBase):
    """A user of ZooKeeper's digest scheme, added to the session as it opens."""

    model_config = ConfigDict(title=N_("Digest"))

    auth_method: Literal["digest"] = _auth_method_field("digest")
    user: str = Field(title=N_("User"), min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class ZookeeperAnonymous(_ZookeeperBase):
    """A session with no identity but its address, which is how most are opened."""

    model_config = ConfigDict(title=N_("Anonymous"))

    auth_method: Literal["anonymous"] = _auth_method_field("anonymous")


ZookeeperOptions = Annotated[
    ZookeeperDigest | ZookeeperAnonymous,
    Field(discriminator="auth_method"),
]
