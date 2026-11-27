"""Microsoft Azure as the provider of an account's secrets (D453, D454).

Microsoft Entra's token endpoint and Key Vault answer through `responses` in
this process; azure-identity and msal speak HTTP to them as they would to
Azure. Nothing reaches Microsoft.
"""

import json
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs

import pytest
import responses
from azure.identity import CredentialUnavailableError, DefaultAzureCredential

from app.adapters import cloud
from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import AzureDefault, AzureServicePrincipal
from app.adapters.cloud.azure.issuer import AzureIssuer
from app.adapters.cloud.requests import EntraToken, StoredSecret
from app.adapters.cloud.signin import AZURE_DATABASE_SCOPE, AZURE_REDIS_SCOPE
from app.adapters.mysql.options import MysqlAzureEntra
from app.adapters.mysql.session import MysqlSession
from app.adapters.postgres.options import PostgresAzureEntra
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.redis.options import RedisAzureEntra

TENANT = "8d2a1b3c-0000-4000-8000-000000000001"
CLIENT = "5e1f9c2a-0000-4000-8000-000000000002"
SECRET = "Ent~ra.secret-value_1234"
ACCOUNT = "6f1d6c52-6c0e-4b52-9b3b-2a8a8c2c1a11"
LOGIN = "https://login.microsoftonline.com"


def _account() -> AzureServicePrincipal:
    return AzureServicePrincipal(
        method="azure_service_principal", tenant_id=TENANT, client_id=CLIENT, client_secret=SECRET
    )


def _token_endpoint(mock: responses.RequestsMock, **answer: Any) -> None:
    mock.add(
        responses.GET,
        re.compile(rf"{LOGIN}/{TENANT}/v2\.0/\.well-known/openid-configuration.*"),
        json={
            "token_endpoint": f"{LOGIN}/{TENANT}/oauth2/v2.0/token",
            "authorization_endpoint": f"{LOGIN}/{TENANT}/oauth2/v2.0/authorize",
            "issuer": f"{LOGIN}/{TENANT}/v2.0",
        },
    )
    mock.add(
        responses.POST,
        f"{LOGIN}/{TENANT}/oauth2/v2.0/token",
        **(answer or {"json": {"access_token": "eyJ.entra", "expires_in": 3600, "token_type": "Bearer"}}),
    )


@pytest.fixture
def entra() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        _token_endpoint(mock)
        yield mock


def _asked_scope(mock: responses.RequestsMock) -> str:
    posted = next(call for call in mock.calls if call.request.method == "POST")
    raw = posted.request.body
    body = parse_qs(raw.decode() if isinstance(raw, bytes) else str(raw))
    return body["scope"][0]


def test_the_provider_of_azure_accounts_is_installed() -> None:
    import app.adapters  # noqa: F401 - registers every provider

    assert isinstance(cloud.issuer_for("azure"), AzureIssuer)


def test_a_database_is_given_a_token_for_its_scope(entra: responses.RequestsMock) -> None:
    token = AzureIssuer().issue(_account(), EntraToken(AZURE_DATABASE_SCOPE))

    assert token.value == "eyJ.entra"
    assert token.expires_at is not None and 3500 < token.expires_at - time.time() <= 3600
    assert AZURE_DATABASE_SCOPE in _asked_scope(entra)


@pytest.mark.usefixtures("entra")
def test_a_test_says_which_application_signed_in() -> None:
    assert AzureIssuer().test(_account()) == f"Signed in as {CLIENT}"


@pytest.mark.parametrize(
    ("asked", "address"),
    [
        ("orders-kv/db-password", "https://orders-kv.vault.azure.net/secrets/db-password"),
        ("orders-kv/db-password/abc123", "https://orders-kv.vault.azure.net/secrets/db-password/abc123"),
        (
            "https://orders-kv.vault.azure.net/secrets/db-password",
            "https://orders-kv.vault.azure.net/secrets/db-password",
        ),
    ],
)
def test_a_key_vault_secret_is_read_by_its_name(entra: responses.RequestsMock, asked: str, address: str) -> None:
    entra.add(responses.GET, address, json={"value": json.dumps({"username": "app", "password": "s3cret"})})

    found = AzureIssuer().issue(_account(), StoredSecret(asked))

    assert (found.user, found.value) == ("app", "s3cret")
    read = next(call for call in entra.calls if call.request.url.startswith(address))
    assert read.request.headers["Authorization"] == "Bearer eyJ.entra"
    assert "https://vault.azure.net/.default" in _asked_scope(entra)


@pytest.mark.parametrize(
    "asked",
    ["https://attacker.example.com/secrets/x", "https://orders-kv.vault.azure.net:8443/secrets/x", "just-a-name"],
)
def test_a_vault_token_goes_nowhere_but_key_vault(entra: responses.RequestsMock, asked: str) -> None:
    with pytest.raises(AdapterError, match="VAULT/NAME"):
        AzureIssuer().issue(_account(), StoredSecret(asked))

    assert not any("attacker" in call.request.url for call in entra.calls)


@pytest.mark.parametrize(
    ("status", "said"),
    [(403, "Key Vault Secrets User"), (404, "no such secret"), (500, "refused the request")],
)
def test_a_refused_secret_is_said_by_its_status(entra: responses.RequestsMock, status: int, said: str) -> None:
    entra.add(
        responses.GET,
        "https://orders-kv.vault.azure.net/secrets/db",
        status=status,
        json={"error": {"message": f"Caller {CLIENT} is not authorized"}},
    )

    with pytest.raises(AdapterError) as refused:
        AzureIssuer().issue(_account(), StoredSecret("orders-kv/db"))

    assert said in refused.value.message and CLIENT not in refused.value.message


def test_a_secret_entra_refuses_is_said_without_microsoft_s_text() -> None:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        _token_endpoint(
            mock,
            status=401,
            json={"error": "invalid_client", "error_description": f"AADSTS7000215: Invalid secret {SECRET}"},
        )

        with pytest.raises(AdapterError) as refused:
            AzureIssuer().issue(_account(), EntraToken(AZURE_DATABASE_SCOPE))

    assert refused.value.error_kind == "auth"
    assert refused.value.message.startswith("Microsoft Entra refused these credentials")
    assert SECRET not in refused.value.message and "AADSTS" not in refused.value.message
    assert refused.value.__cause__ is None


def test_this_server_without_azure_credentials_is_said_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def nothing(*_: Any, **__: Any) -> None:
        raise CredentialUnavailableError("EnvironmentCredential: AZURE_CLIENT_ID is not set for someone")

    monkeypatch.setattr(DefaultAzureCredential, "get_token", nothing)

    with pytest.raises(AdapterError) as refused:
        AzureIssuer().issue(AzureDefault(method="azure_default"), EntraToken(AZURE_DATABASE_SCOPE))

    assert "no Azure credentials" in refused.value.message and "someone" not in refused.value.message


def test_another_kind_s_question_is_refused() -> None:
    with pytest.raises(AdapterError):
        AzureIssuer().issue(_account(), SecretRequest())


class _Cloud:
    def __init__(self) -> None:
        self.asked: list[SecretRequest] = []

    async def issue(self, account_id: Any, kinds: tuple[str, ...], request: SecretRequest) -> IssuedSecret:
        assert kinds == ("azure",)
        self.asked.append(request)
        return IssuedSecret(value="eyJ.db", expires_at=time.time() + 3600)


async def test_postgres_signs_in_with_an_entra_token_for_azure_s_databases() -> None:
    access = _Cloud()
    options = PostgresAzureEntra(host="orders.postgres.database.azure.com", database="orders", user="app-readers", account=ACCOUNT)

    credentials = await PostgresSession(options, cloud=access).credentials()

    assert credentials == {"user": "app-readers", "password": "eyJ.db"}
    assert access.asked == [EntraToken(AZURE_DATABASE_SCOPE)]


async def test_mysql_sends_an_entra_token_in_the_clear_only_over_verified_tls() -> None:
    options = MysqlAzureEntra(host="orders.mysql.database.azure.com", database="orders", user="app", account=ACCOUNT, tls_mode="verify_full")

    credentials = await MysqlSession(options, cloud=_Cloud())._credentials()  # noqa: SLF001 - what aiomysql is handed

    assert credentials["auth_plugin"] == "mysql_clear_password"
    with pytest.raises(ValueError, match="in the clear"):
        MysqlAzureEntra(host="h", database="d", user="u", account=ACCOUNT, tls_mode="required")


async def test_azure_cache_for_redis_takes_a_token_for_its_own_scope() -> None:
    access = _Cloud()
    options = RedisAzureEntra(host="orders.redis.cache.windows.net", port=6380, user="0f6a", account=ACCOUNT, tls_mode="verify_full")

    signed = await options.sign_in(access)

    assert (signed.user, signed.password) == ("0f6a", "eyJ.db")
    assert access.asked == [EntraToken(AZURE_REDIS_SCOPE)]
    with pytest.raises(ValueError, match="needs TLS"):
        RedisAzureEntra(host="h", user="u", account=ACCOUNT, tls_mode="disabled")
