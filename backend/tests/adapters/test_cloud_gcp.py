"""Google Cloud as the provider of an account's secrets (D453–D455).

Google's token, impersonation and Secret Manager endpoints answer through
`responses` in this process, and the key file carries a real RSA key so the
service account's assertion is signed for real. Nothing reaches Google.
"""

import base64
import json
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs

import google.auth
import pytest
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth.exceptions import DefaultCredentialsError

from app.adapters import cloud
from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import GcpDefault, GcpServiceAccount
from app.adapters.cloud.gcp.issuer import SQL_LOGIN, GcpIssuer
from app.adapters.cloud.requests import CloudSqlToken, StoredSecret
from app.adapters.mysql.options import MysqlGcpIam
from app.adapters.mysql.session import MysqlSession
from app.adapters.postgres.options import PostgresGcpIam
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError

TOKEN_URI = "https://oauth2.googleapis.com/token"
SECRETS = "https://secretmanager.googleapis.com/v1"
EMAIL = "reader@orders-prod.iam.gserviceaccount.com"
TARGET = "cloudsql@orders-prod.iam.gserviceaccount.com"
ACCOUNT = "6f1d6c52-6c0e-4b52-9b3b-2a8a8c2c1a11"


@pytest.fixture(scope="module")
def key_file() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "orders-prod",
            "private_key_id": "1",
            "private_key": pem,
            "client_email": EMAIL,
            "client_id": "1",
            "token_uri": TOKEN_URI,
        }
    )


def _account(key_file: str, **changes: Any) -> GcpServiceAccount:
    return GcpServiceAccount.model_validate({"method": "gcp_service_account", "key_json": key_file, **changes})


@pytest.fixture
def google_api() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.add(responses.POST, TOKEN_URI, json={"access_token": "ya29.own", "expires_in": 3600, "token_type": "Bearer"})
        yield mock


def _scope_asked(mock: responses.RequestsMock) -> str:
    """The scope a service account's signed assertion asked for."""
    raw = mock.calls[0].request.body
    body = parse_qs(raw.decode() if isinstance(raw, bytes) else str(raw))
    claims = body["assertion"][0].split(".")[1]
    return str(json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["scope"])


def test_the_provider_of_google_cloud_accounts_is_installed() -> None:
    import app.adapters  # noqa: F401 - registers every provider

    assert isinstance(cloud.issuer_for("gcp"), GcpIssuer)


def test_cloud_sql_is_given_a_token_for_its_login_scope(key_file: str, google_api: responses.RequestsMock) -> None:
    token = GcpIssuer().issue(_account(key_file), CloudSqlToken())

    assert token.value == "ya29.own"
    assert token.expires_at is not None and 3500 < token.expires_at - time.time() <= 3600
    assert _scope_asked(google_api) == SQL_LOGIN


def test_a_token_is_issued_as_another_service_account(key_file: str, google_api: responses.RequestsMock) -> None:
    google_api.add(
        responses.POST,
        f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{TARGET}:generateAccessToken",
        json={"accessToken": "ya29.acting", "expireTime": "2030-01-01T00:00:00Z"},
    )

    token = GcpIssuer().issue(_account(key_file, impersonate=TARGET), CloudSqlToken())

    assert token.value == "ya29.acting"
    asked = json.loads(google_api.calls[-1].request.body or b"{}")
    assert asked["scope"] == [SQL_LOGIN]


@pytest.mark.usefixtures("google_api")
def test_a_test_says_which_service_account_signed_in(key_file: str) -> None:
    assert GcpIssuer().test(_account(key_file)) == f"Signed in as {EMAIL}"


@pytest.mark.parametrize(
    ("asked", "path"),
    [
        ("db", "projects/orders-prod/secrets/db/versions/latest"),
        ("projects/other/secrets/db", "projects/other/secrets/db/versions/latest"),
        ("projects/other/secrets/db/versions/7", "projects/other/secrets/db/versions/7"),
    ],
)
def test_a_secret_is_read_by_its_name_in_the_key_s_project(
    key_file: str, google_api: responses.RequestsMock, asked: str, path: str
) -> None:
    payload = base64.b64encode(json.dumps({"username": "app", "password": "s3cret"}).encode()).decode()
    google_api.add(responses.GET, f"{SECRETS}/{path}:access", json={"payload": {"data": payload}})

    found = GcpIssuer().issue(_account(key_file), StoredSecret(asked))

    assert (found.user, found.value) == ("app", "s3cret")


@pytest.mark.parametrize(
    ("status", "said"),
    [(403, "the account needs the Secret Accessor role"), (404, "no such secret"), (500, "refused the request")],
)
def test_a_refused_secret_is_said_by_its_status(
    key_file: str, google_api: responses.RequestsMock, status: int, said: str
) -> None:
    google_api.add(
        responses.GET,
        f"{SECRETS}/projects/orders-prod/secrets/db/versions/latest:access",
        status=status,
        json={"error": {"message": f"Permission denied for {EMAIL}"}},
    )

    with pytest.raises(AdapterError) as refused:
        GcpIssuer().issue(_account(key_file), StoredSecret("db"))

    assert said in refused.value.message
    assert EMAIL not in refused.value.message


def test_a_key_google_refuses_is_said_without_google_s_text(key_file: str) -> None:
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, TOKEN_URI, status=400, json={"error": "invalid_grant", "error_description": f"Bad key for {EMAIL}"})

        with pytest.raises(AdapterError) as refused:
            GcpIssuer().issue(_account(key_file), CloudSqlToken())

    assert refused.value.error_kind == "auth"
    assert refused.value.message.startswith("Google refused these credentials")
    assert EMAIL not in refused.value.message and refused.value.__cause__ is None


def test_this_server_without_google_credentials_is_said_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def nothing(**_: Any) -> None:
        raise DefaultCredentialsError("No credentials at /home/someone/.config/gcloud")

    monkeypatch.setattr(google.auth, "default", nothing)

    with pytest.raises(AdapterError) as refused:
        GcpIssuer().issue(GcpDefault(method="gcp_adc"), CloudSqlToken())

    assert "no Google credentials" in refused.value.message and "someone" not in refused.value.message


def test_a_secret_named_without_a_project_and_no_key_to_take_one_from_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class Own:
        token = "ya29.own"
        expiry = None

        def refresh(self, _request: Any) -> None:
            return None

        def before_request(self, *_: Any) -> None:
            return None

    monkeypatch.setattr(google.auth, "default", lambda **_: (Own(), None))

    with pytest.raises(AdapterError, match="projects/PROJECT/secrets/NAME"):
        GcpIssuer().issue(GcpDefault(method="gcp_adc"), StoredSecret("db"))


def test_another_kind_s_account_or_question_is_refused(key_file: str) -> None:
    with pytest.raises(AdapterError):
        GcpIssuer().issue(_account(key_file), SecretRequest())


class _Cloud:
    def __init__(self) -> None:
        self.asked: list[SecretRequest] = []

    async def issue(self, account_id: Any, kinds: tuple[str, ...], request: SecretRequest) -> IssuedSecret:
        assert kinds == ("gcp",)
        self.asked.append(request)
        return IssuedSecret(value="ya29.sql", expires_at=time.time() + 3600)


async def test_postgres_signs_in_to_cloud_sql_with_the_token_as_its_password() -> None:
    options = PostgresGcpIam(host="10.1.2.3", database="orders", user=EMAIL.removesuffix(".gserviceaccount.com"), account=ACCOUNT)
    access = _Cloud()

    credentials = await PostgresSession(options, cloud=access).credentials()

    assert credentials == {"user": "reader@orders-prod.iam", "password": "ya29.sql"}
    assert access.asked == [CloudSqlToken()]
    with pytest.raises(ValueError, match="needs TLS"):
        PostgresGcpIam(host="h", database="d", user="u", account=ACCOUNT, tls_mode="disabled")


async def test_mysql_sends_the_token_in_the_clear_and_only_over_verified_tls() -> None:
    options = MysqlGcpIam(host="10.1.2.3", database="orders", user="reader", account=ACCOUNT, tls_mode="verify_ca")

    credentials = await MysqlSession(options, cloud=_Cloud())._credentials()  # noqa: SLF001 - what aiomysql is handed

    assert credentials["auth_plugin"] == "mysql_clear_password" and credentials["password"] == "ya29.sql"
    with pytest.raises(ValueError, match="in the clear"):
        MysqlGcpIam(host="h", database="d", user="u", account=ACCOUNT, tls_mode="preferred")
