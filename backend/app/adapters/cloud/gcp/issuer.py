"""What a Google Cloud account is asked for, answered through google-auth (D453–D455).

Synchronous: the caller runs every method in a thread. A token is an OAuth 2
access token for the scope the question needs; Secret Manager is read over its
REST API with that token, so no gRPC client is installed. Refusals are worded
from the exception's class and the HTTP status, never from Google's text.
"""

import base64
import json
from datetime import UTC, datetime
from typing import Any

import google.auth
import requests
from google.auth import impersonated_credentials
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import service_account
from pydantic import BaseModel

from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import GcpDefault, GcpServiceAccount
from app.adapters.cloud.requests import CloudSqlToken, StoredSecret
from app.adapters.cloud.stored import read_secret
from app.adapters.protocol import AdapterError
from app.core.translation import say

CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"
# What Cloud SQL's IAM database authentication takes for a password.
SQL_LOGIN = "https://www.googleapis.com/auth/sqlservice.login"
SECRET_MANAGER = "https://secretmanager.googleapis.com/v1"
TIMEOUT_SECONDS = 20
# An impersonated token's life; Google's longest without an organisation policy.
IMPERSONATED_SECONDS = 3600

type GcpSettings = GcpServiceAccount | GcpDefault


class GcpIssuer:
    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret:
        settings = _gcp(account)
        try:
            if isinstance(request, CloudSqlToken):
                return _token(_credentials(settings, SQL_LOGIN))
            if isinstance(request, StoredSecret):
                return _stored(settings, request)
        except (RefreshError, DefaultCredentialsError, TransportError, requests.RequestException) as failure:
            raise _reduced(failure) from None
        raise AdapterError("config", say("An account of Google Cloud cannot be asked for this"))

    def test(self, account: BaseModel) -> str:
        settings = _gcp(account)
        try:
            credentials = _credentials(settings, CLOUD_PLATFORM)
            credentials.refresh(Request())
        except (RefreshError, DefaultCredentialsError, TransportError, requests.RequestException) as failure:
            raise _reduced(failure) from None
        identity = settings.impersonate or getattr(credentials, "service_account_email", "")
        if isinstance(identity, str) and identity and identity != "default":
            return say("Signed in as {identity}", identity=identity)
        return say("Google issued a token for this account")


def _gcp(account: BaseModel) -> GcpSettings:
    if not isinstance(account, GcpServiceAccount | GcpDefault):
        raise AdapterError("config", say("An account of Google Cloud cannot be asked for this"))
    return account


def _credentials(settings: GcpSettings, scope: str) -> Credentials:
    """The account's credentials for one scope, acting as another service
    account when one is named."""
    scopes = [CLOUD_PLATFORM] if settings.impersonate else [scope]
    if isinstance(settings, GcpServiceAccount):
        try:
            info = json.loads(settings.key_json.get_secret_value())
            source: Credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        except (ValueError, KeyError):
            raise AdapterError("config", say("The key file could not be read; paste it again")) from None
    else:
        source, _ = google.auth.default(scopes=scopes)
    if not settings.impersonate:
        return source
    return impersonated_credentials.Credentials(
        source_credentials=source,
        target_principal=settings.impersonate,
        target_scopes=[scope],
        lifetime=IMPERSONATED_SECONDS,
    )


def _token(credentials: Credentials) -> IssuedSecret:
    credentials.refresh(Request())
    token = credentials.token
    if not isinstance(token, str):
        raise AdapterError("auth", say("Google issued no token for this account"))
    # google-auth keeps the expiry naive, in UTC.
    expiry = credentials.expiry
    expires_at = expiry.replace(tzinfo=UTC).timestamp() if isinstance(expiry, datetime) else None
    return IssuedSecret(value=token, expires_at=expires_at)


def _secret_name(settings: GcpSettings, name: str) -> str:
    """`projects/p/secrets/s/versions/v`, completed from what was typed: the
    latest version when none is named, the key file's project when no project is."""
    if name.startswith("projects/"):
        return name if "/versions/" in name else f"{name}/versions/latest"
    project = ""
    if isinstance(settings, GcpServiceAccount):
        info: dict[str, Any] = json.loads(settings.key_json.get_secret_value())
        project = str(info.get("project_id", ""))
    if not project:
        raise AdapterError(
            "config", say("Name the secret as projects/PROJECT/secrets/NAME")
        )
    return f"projects/{project}/secrets/{name}/versions/latest"


def _stored(settings: GcpSettings, request: StoredSecret) -> IssuedSecret:
    session = AuthorizedSession(_credentials(settings, CLOUD_PLATFORM))
    answer = session.get(f"{SECRET_MANAGER}/{_secret_name(settings, request.name)}:access", timeout=TIMEOUT_SECONDS)
    if answer.status_code in (401, 403):
        raise AdapterError("auth", say("Google denied this; the account needs the Secret Accessor role"))
    if answer.status_code == 404:
        raise AdapterError("config", say("Google has no such secret or version"))
    if answer.status_code != 200:
        raise AdapterError("unknown", say("Google refused the request; test the account in Preferences"))
    data = answer.json().get("payload", {}).get("data", "")
    try:
        text = base64.b64decode(data).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise AdapterError("config", say("The secret holds no text; a password is kept as text")) from None
    return read_secret(text, request)


def _reduced(failure: Exception) -> AdapterError:
    if isinstance(failure, DefaultCredentialsError):
        return AdapterError("auth", say("This server has no Google credentials of its own to sign in with"))
    if isinstance(failure, RefreshError):
        return AdapterError(
            "auth",
            say("Google refused these credentials; check the key and, to act as another service account, its Token Creator role"),
        )
    return AdapterError("network", say("Google could not be reached; check the network"))
