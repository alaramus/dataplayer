"""A secret a cloud issues for a connection, asked for at every new one (D449).

Driver-free. A source whose options name one of its owner's cloud accounts
asks `AdapterContext.cloud` for an `IssuedSecret` each time it opens a physical
connection and keeps none: an RDS token lives fifteen minutes, and a pool
outlives it. Which provider issues it is a `CredentialIssuer` registered for
the account's kind; its SDK stays in a package of its own (`.importlinter`).
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.adapters.layout import layout
from app.adapters.options import CLOUD_ACCOUNT_KIND, CLOUD_ACCOUNT_REFERENCE
from app.adapters.protocol import AdapterError
from app.core.translation import say

AccountKind = Literal["aws", "gcp", "azure", "vault"]


@dataclass(frozen=True)
class IssuedSecret:
    """A password or token, when it stops being accepted, and whose it is.

    `expires_at` is seconds since the epoch, None for a secret that does not
    expire by itself (one read from a secret store). `user` is the name to
    sign in as, when the issuer decides it (Vault's dynamic credentials).
    """

    value: str
    expires_at: float | None
    user: str | None = None
    # Temporary AWS credentials' third part (`CloudCredentials`).
    session_token: str | None = None

    def __repr__(self) -> str:
        return "IssuedSecret(<hidden>)"


@dataclass(frozen=True)
class SecretRequest:
    """What is asked of an account. A provider's subclass names the rest.

    Frozen, so it is hashable and keys the cache of issued secrets: two
    connections asking the same thing of one account share one token.
    """


@runtime_checkable
class CloudAccess(Protocol):
    """The cloud accounts of the person who owns a connection (D451).

    Raises `AdapterError` of kind `config` when the account is gone, is
    somebody else's or is of none of the kinds the connection takes, and
    whatever the issuer refuses with, already reduced to a safe sentence.
    """

    async def issue(
        self, account_id: uuid.UUID, kinds: tuple[AccountKind, ...], request: SecretRequest
    ) -> IssuedSecret: ...


class CredentialIssuer(Protocol):
    """A provider: what an account of its kind can be asked for.

    Synchronous, because every cloud SDK is; the caller runs it in a thread.
    Every failure is raised as an `AdapterError` naming what to check, never
    the SDK's text, which can carry a key or a signed request.
    """

    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret: ...

    def test(self, account: BaseModel) -> str:
        """The cheapest harmless call, and a sentence saying what it found."""
        ...


_issuers: dict[AccountKind, CredentialIssuer] = {}


def register_issuer(kind: AccountKind, issuer: CredentialIssuer) -> None:
    _issuers[kind] = issuer


def issuer_for(kind: AccountKind) -> CredentialIssuer | None:
    """The provider of a kind, or None while none is installed."""
    return _issuers.get(kind)


def account_field(
    *kinds: AccountKind, title: str, description: str | None = None
) -> Any:
    """A connection's field naming one of its owner's accounts of these kinds.

    The kinds travel in the schema, so the form offers only accounts of them
    and the server checks the account when the connection is saved and again
    when it opens (D451). A secret store takes four kinds (D454).
    """
    extra = layout(purpose=CLOUD_ACCOUNT_REFERENCE)
    extra[CLOUD_ACCOUNT_KIND] = list(kinds)
    return Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        title=title,
        description=description,
        json_schema_extra=extra,
    )


async def issue(
    cloud: CloudAccess | None,
    account: str,
    kinds: tuple[AccountKind, ...],
    request: SecretRequest,
) -> IssuedSecret:
    """What a source asks at every new connection; refused without access."""
    if cloud is None:
        raise AdapterError(
            "config", say("This connection signs in with a cloud account, and none is at hand")
        )
    return await cloud.issue(uuid.UUID(account), kinds, request)
