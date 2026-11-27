"""What a source may ask of a cloud account (D449, D453, D454).

Driver-free and provider-neutral where the question is: a stored secret is
asked of AWS, Google, Azure or Vault alike, and each provider answers it its
own way. A question only one cloud can answer says so in its name. A provider
asked something it does not answer refuses with `config`.
"""

from dataclasses import dataclass

from app.adapters.cloud import SecretRequest


@dataclass(frozen=True)
class StoredSecret(SecretRequest):
    """A password kept in a secret store, and the user beside it (D454).

    `name` is the secret's name or ARN (AWS), its resource name (Google),
    its name (Key Vault) or its path (Vault KV). A secret that is JSON is read
    by the two keys; one that is not is the password itself.
    """

    name: str
    password_key: str = "password"
    user_key: str = "username"


@dataclass(frozen=True)
class RdsAuthToken(SecretRequest):
    """An RDS or Aurora IAM token: a request to connect, signed for this host,
    port and user, valid fifteen minutes."""

    host: str
    port: int
    user: str
    region: str


@dataclass(frozen=True)
class ElastiCacheToken(SecretRequest):
    """An ElastiCache or MemoryDB IAM token: a signed `connect` for one cache
    and user, valid fifteen minutes; the connection it opens lasts twelve hours."""

    cache_name: str
    user: str
    region: str
    serverless: bool
    service: str = "elasticache"


@dataclass(frozen=True)
class MskToken(SecretRequest):
    """An MSK IAM token for SASL/OAUTHBEARER, signed for the region."""

    region: str


@dataclass(frozen=True)
class CloudSqlToken(SecretRequest):
    """A Google OAuth 2 access token for Cloud SQL's IAM database sign-in
    (scope `sqlservice.login`), valid an hour; the same for every instance."""


@dataclass(frozen=True)
class CloudCredentials(SecretRequest):
    """The account's own credentials as a driver signs with them: AWS's access
    key in `user`, its secret in `value`, its session token in `session_token`."""

    region: str
