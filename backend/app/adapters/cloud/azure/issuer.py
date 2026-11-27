"""What an Azure account is asked for, answered through azure-identity (D453, D454).

Synchronous: the caller runs every method in a thread. A token is a Microsoft
Entra access token for the scope a source names; Key Vault is read over its
REST API with a token for Key Vault, and only at Key Vault's own domains, so
a token never goes to an address somebody typed. Refusals are worded from the
exception's class and the HTTP status, never from Microsoft's text.
"""

from urllib.parse import quote, urlsplit

import requests
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import (
    ClientSecretCredential,
    CredentialUnavailableError,
    DefaultAzureCredential,
)
from pydantic import BaseModel

from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import AzureDefault, AzureServicePrincipal
from app.adapters.cloud.requests import EntraToken, StoredSecret
from app.adapters.cloud.stored import read_secret
from app.adapters.protocol import AdapterError
from app.core.translation import say

KEY_VAULT_SCOPE = "https://vault.azure.net/.default"
KEY_VAULT_API = "7.4"
# Key Vault's domains in Azure's clouds; a vault's token goes nowhere else.
KEY_VAULT_DOMAINS = (".vault.azure.net", ".vault.azure.cn", ".vault.usgovcloudapi.net")
# What a test asks for: a token every account may have, naming nothing.
TEST_SCOPE = "https://management.azure.com/.default"
TIMEOUT_SECONDS = 20

type AzureSettings = AzureServicePrincipal | AzureDefault


class AzureIssuer:
    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret:
        settings = _azure(account)
        try:
            if isinstance(request, EntraToken):
                return _token(_credential(settings), request.scope)
            if isinstance(request, StoredSecret):
                return _stored(_credential(settings), request)
        except (CredentialUnavailableError, ClientAuthenticationError, AzureError, requests.RequestException) as failure:
            raise _reduced(failure) from None
        raise AdapterError("config", say("An account of Microsoft Azure cannot be asked for this"))

    def test(self, account: BaseModel) -> str:
        settings = _azure(account)
        try:
            _token(_credential(settings), TEST_SCOPE)
        except (CredentialUnavailableError, ClientAuthenticationError, AzureError, requests.RequestException) as failure:
            raise _reduced(failure) from None
        if isinstance(settings, AzureServicePrincipal):
            return say("Signed in as {identity}", identity=settings.client_id)
        return say("Microsoft Entra issued a token for this account")


def _azure(account: BaseModel) -> AzureSettings:
    if not isinstance(account, AzureServicePrincipal | AzureDefault):
        raise AdapterError("config", say("An account of Microsoft Azure cannot be asked for this"))
    return account


def _credential(settings: AzureSettings) -> TokenCredential:
    if isinstance(settings, AzureServicePrincipal):
        return ClientSecretCredential(
            tenant_id=settings.tenant_id,
            client_id=settings.client_id,
            client_secret=settings.client_secret.get_secret_value(),
        )
    # This server's own identity: its environment, workload identity, managed
    # identity (a user-assigned one when named) or a signed-in Azure CLI (D452).
    return DefaultAzureCredential(managed_identity_client_id=settings.client_id or None)


def _token(credential: TokenCredential, scope: str) -> IssuedSecret:
    found = credential.get_token(scope)
    return IssuedSecret(value=found.token, expires_at=float(found.expires_on))


def _vault_address(name: str) -> str:
    """`vault/secret[/version]`, or the secret's identifier as the portal
    shows it; either way an address of Key Vault and of nothing else."""
    if name.startswith("https://"):
        parts = urlsplit(name)
        host = (parts.hostname or "").lower()
        path = [part for part in parts.path.split("/") if part]
        if (
            not host.endswith(KEY_VAULT_DOMAINS)
            or parts.port is not None
            or len(path) not in (2, 3)
            or path[0] != "secrets"
        ):
            raise AdapterError("config", say("Name the secret as VAULT/NAME, or by its Key Vault identifier"))
        return f"https://{host}/{'/'.join(quote(part, safe='') for part in path)}"
    path = [part for part in name.split("/") if part]
    if len(path) not in (2, 3):
        raise AdapterError("config", say("Name the secret as VAULT/NAME, or by its Key Vault identifier"))
    vault, *secret = path
    return f"https://{quote(vault, safe='')}.vault.azure.net/secrets/{'/'.join(quote(part, safe='') for part in secret)}"


def _stored(credential: TokenCredential, request: StoredSecret) -> IssuedSecret:
    address = _vault_address(request.name)
    token = credential.get_token(KEY_VAULT_SCOPE).token
    answer = requests.get(
        address,
        params={"api-version": KEY_VAULT_API},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )
    if answer.status_code in (401, 403):
        raise AdapterError("auth", say("Key Vault denied this; the account needs the Key Vault Secrets User role"))
    if answer.status_code == 404:
        raise AdapterError("config", say("Key Vault has no such secret or version"))
    if answer.status_code != 200:
        raise AdapterError("unknown", say("Key Vault refused the request; test the account in Preferences"))
    value = answer.json().get("value")
    if not isinstance(value, str):
        raise AdapterError("config", say("The secret holds no text; a password is kept as text"))
    return read_secret(value, request)


def _reduced(failure: Exception) -> AdapterError:
    if isinstance(failure, CredentialUnavailableError):
        return AdapterError("auth", say("This server has no Azure credentials of its own to sign in with"))
    if isinstance(failure, ClientAuthenticationError):
        return AdapterError(
            "auth", say("Microsoft Entra refused these credentials; check the tenant, client ID and secret")
        )
    return AdapterError("network", say("Azure could not be reached; check the network"))
