"""HashiCorp Vault as the provider of an account's secrets (D454).

Against the Vault dev server (`vault` in compose.override.yml), skipped
without it. Its database secrets engine makes real roles in the suite's own
PostgreSQL, reached from Vault as `db`.
"""

import time
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import VaultAppRole, VaultToken
from app.adapters.cloud.requests import StoredSecret, VaultDatabaseCredentials
from app.adapters.cloud.vault.issuer import VaultIssuer
from app.adapters.postgres.options import PostgresVaultDynamic
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.core.config import settings
from tests.utils import services

ACCOUNT = str(uuid.uuid4())
ROLE = "dp-test"


class Vault:
    """The dev server, its root token, and a way to configure it."""

    def __init__(self) -> None:
        parts = urlsplit(services.VAULT.require())
        self.address = f"http://{parts.hostname}:{parts.port}"
        self.token = parts.username or ""

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = requests.request(
            method, f"{self.address}/v1/{path}", json=body, headers={"X-Vault-Token": self.token}, timeout=10
        )
        assert answer.status_code in (200, 204), (path, answer.status_code, answer.text)
        found: dict[str, Any] = answer.json() if answer.content else {}
        return found

    def enable(self, kind: str, path: str, body: dict[str, Any]) -> None:
        mounted = requests.get(
            f"{self.address}/v1/sys/{kind}", headers={"X-Vault-Token": self.token}, timeout=10
        ).json()
        if f"{path}/" not in mounted.get("data", mounted):
            self.call("POST", f"sys/{kind}/{path}", body)

    def account(self, token: str | None = None) -> VaultToken:
        return VaultToken(method="vault_token", address=self.address, token=token or self.token)


@pytest.fixture(scope="module")
def vault() -> Iterator[Vault]:
    found = Vault()
    found.enable("mounts", "kv1", {"type": "kv", "options": {"version": "1"}})
    found.call("POST", "secret/data/dp/db", {"data": {"username": "app", "password": "s3cret"}})
    found.call("POST", "kv1/dp/app", {"password": "plain-v1"})
    yield found


def test_a_kv2_secret_is_read_by_its_mount_and_path(vault: Vault) -> None:
    found = VaultIssuer().issue(vault.account(), StoredSecret("secret/dp/db"))

    assert (found.user, found.value) == ("app", "s3cret")


def test_a_kv1_secret_is_read_as_well(vault: Vault) -> None:
    found = VaultIssuer().issue(vault.account(), StoredSecret("kv1/dp/app"))

    assert (found.user, found.value) == (None, "plain-v1")


def test_a_test_says_who_signed_in(vault: Vault) -> None:
    assert VaultIssuer().test(vault.account()).startswith("Signed in as ")


def test_a_path_nothing_is_at_is_said_so(vault: Vault) -> None:
    with pytest.raises(AdapterError, match="nothing at this path"):
        VaultIssuer().issue(vault.account(), StoredSecret("secret/dp/missing"))
    with pytest.raises(AdapterError, match="MOUNT/PATH"):
        VaultIssuer().issue(vault.account(), StoredSecret("lonely"))


def test_a_token_without_the_policy_is_denied_in_words(vault: Vault) -> None:
    weak = vault.call("POST", "auth/token/create", {"policies": ["default"], "ttl": "5m"})["auth"]["client_token"]

    with pytest.raises(AdapterError) as refused:
        VaultIssuer().issue(vault.account(weak), StoredSecret("secret/dp/db"))

    assert refused.value.error_kind == "auth" and weak not in refused.value.message


def test_approle_logs_in_and_a_wrong_secret_id_is_refused(vault: Vault) -> None:
    vault.enable("auth", "approle", {"type": "approle"})
    vault.call("PUT", "sys/policies/acl/dp-read", {"policy": 'path "secret/data/dp/*" { capabilities = ["read"] }'})
    vault.call("POST", "auth/approle/role/dp", {"token_policies": ["default", "dp-read"]})
    role_id = vault.call("GET", "auth/approle/role/dp/role-id")["data"]["role_id"]
    secret_id = vault.call("POST", "auth/approle/role/dp/secret-id")["data"]["secret_id"]

    def account(secret: str) -> VaultAppRole:
        return VaultAppRole(method="vault_approle", address=vault.address, role_id=role_id, secret_id=secret)

    found = VaultIssuer().issue(account(secret_id), StoredSecret("secret/dp/db"))
    with pytest.raises(AdapterError, match="role ID or the secret ID"):
        VaultIssuer().issue(account("not-the-secret-id"), StoredSecret("secret/dp/db"))

    assert found.value == "s3cret"


def test_vault_out_of_reach_is_said_so() -> None:
    account = VaultToken(method="vault_token", address="http://127.0.0.1:1", token="t")

    with pytest.raises(AdapterError) as refused:
        VaultIssuer().issue(account, StoredSecret("secret/x"))

    assert refused.value.error_kind == "network"


# --- dynamic database credentials ------------------------------------------------


@pytest.fixture(scope="module")
def database_role(vault: Vault) -> str:
    """A role of Vault's database engine making logins in the suite's database."""
    url = settings.DATABASE_URL
    host = url.hosts()[0]
    database = (url.path or "/app").lstrip("/")
    vault.enable("mounts", "database", {"type": "database"})
    vault.call(
        "POST",
        "database/config/dp",
        {
            "plugin_name": "postgresql-database-plugin",
            # Vault reaches PostgreSQL as `db`, in compose and in CI alike.
            "connection_url": f"postgresql://{{{{username}}}}:{{{{password}}}}@db:5432/{database}?sslmode=disable",
            "username": host["username"],
            "password": host["password"],
            "allowed_roles": ROLE,
            "verify_connection": True,
        },
    )
    vault.call(
        "POST",
        f"database/roles/{ROLE}",
        {
            "db_name": "dp",
            "creation_statements": [
                "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';",
                f'GRANT CONNECT ON DATABASE "{database}" TO "{{{{name}}}}";',
            ],
            "default_ttl": "1h",
            "max_ttl": "2h",
        },
    )
    return database


@pytest.mark.usefixtures("database_role")
def test_vault_makes_a_login_for_the_asking_with_its_lease_as_its_life(vault: Vault) -> None:
    found = VaultIssuer().issue(vault.account(), VaultDatabaseCredentials("database", ROLE))

    assert found.user is not None and found.user.startswith("v-")
    assert found.expires_at is not None and 3500 < found.expires_at - time.time() <= 3600


class _Cloud:
    """The owner's Vault account, answered by the real provider."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.asked: list[SecretRequest] = []

    async def issue(self, account_id: Any, kinds: tuple[str, ...], request: SecretRequest) -> IssuedSecret:
        assert kinds == ("vault",)
        self.asked.append(request)
        return VaultIssuer().issue(self.vault.account(), request)


async def test_postgres_signs_in_as_the_login_vault_made(vault: Vault, database_role: str) -> None:
    url = settings.DATABASE_URL.hosts()[0]
    options = PostgresVaultDynamic(
        host=url["host"] or "localhost",
        port=url["port"] or 5432,
        database=database_role,
        account=ACCOUNT,
        role=ROLE,
    )
    cloud = _Cloud(vault)
    session = PostgresSession(options, cloud=cloud)

    rows = await session.query("SELECT current_user AS who")

    assert str(rows[0]["who"]).startswith("v-")
    assert cloud.asked == [VaultDatabaseCredentials("database", ROLE)]
    assert "v-" not in session.connection_string()
