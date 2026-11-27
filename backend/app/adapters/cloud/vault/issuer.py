"""What a Vault account is asked for: a KV secret, or database credentials
made for the asking (D454).

Synchronous: the caller runs every method in a thread. The account signs in
with its token, or logs in with AppRole for one; a dynamic credential's lease
is its expiry, so the cache of issued secrets hands it to every connection
until a minute before Vault lets it lapse. Refusals are worded from the HTTP
status, never from Vault's text.
"""

import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from app.adapters.cloud import IssuedSecret, SecretRequest
from app.adapters.cloud.accounts import VaultAppRole, VaultToken
from app.adapters.cloud.requests import StoredSecret, VaultDatabaseCredentials
from app.adapters.cloud.stored import read_secret
from app.adapters.protocol import AdapterError
from app.core.translation import say

TIMEOUT_SECONDS = 20

type VaultSettings = VaultToken | VaultAppRole


class VaultIssuer:
    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret:
        settings = _vault(account)
        if not isinstance(request, StoredSecret | VaultDatabaseCredentials):
            raise AdapterError("config", say("An account of HashiCorp Vault cannot be asked for this"))
        try:
            with _Session(settings) as vault:
                if isinstance(request, VaultDatabaseCredentials):
                    return _database(vault, request)
                return _stored(vault, request)
        except requests.RequestException:
            raise AdapterError("network", say("Vault could not be reached; check its address and the network")) from None

    def test(self, account: BaseModel) -> str:
        settings = _vault(account)
        try:
            with _Session(settings) as vault:
                found = vault.get("auth/token/lookup-self")
        except requests.RequestException:
            raise AdapterError("network", say("Vault could not be reached; check its address and the network")) from None
        name = found.get("data", {}).get("display_name")
        return say("Signed in as {identity}", identity=str(name or "Vault"))


def _vault(account: BaseModel) -> VaultSettings:
    if not isinstance(account, VaultToken | VaultAppRole):
        raise AdapterError("config", say("An account of HashiCorp Vault cannot be asked for this"))
    return account


@contextmanager
def _authorities(pem: str) -> Iterator[str | bool]:
    """What `requests` verifies against: the system's, or the account's CA
    written to a private file for as long as the call lasts (D447)."""
    if not pem:
        yield True
        return
    folder = tempfile.mkdtemp(prefix="dp-vault-")
    try:
        path = Path(folder) / "ca.pem"
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w", encoding="ascii") as file:
            file.write(pem)
        yield str(path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class _Session:
    """Calls to one Vault, signed in with the account's token or AppRole."""

    def __init__(self, settings: VaultSettings) -> None:
        self._settings = settings
        self._token = ""
        self._verify: str | bool = True
        self._files = _authorities(settings.ca_certificate)

    def __enter__(self) -> _Session:
        self._verify = self._files.__enter__()
        settings = self._settings
        if isinstance(settings, VaultToken):
            self._token = settings.token.get_secret_value()
        else:
            answer = self._call(
                "POST",
                f"auth/{settings.mount}/login",
                {"role_id": settings.role_id, "secret_id": settings.secret_id.get_secret_value()},
                signed=False,
            )
            token = answer.get("auth", {}).get("client_token")
            if not isinstance(token, str):
                raise AdapterError("auth", say("Vault refused the role ID or the secret ID"))
            self._token = token
        return self

    def __exit__(self, *failure: object) -> None:
        self._files.__exit__(None, None, None)

    def get(self, path: str) -> dict[str, Any]:
        return self._call("GET", path, None, signed=True)

    def _call(self, method: str, path: str, body: dict[str, Any] | None, *, signed: bool) -> dict[str, Any]:
        headers = {}
        if signed:
            headers["X-Vault-Token"] = self._token
        if self._settings.namespace:
            headers["X-Vault-Namespace"] = self._settings.namespace
        answer = requests.request(
            method,
            f"{self._settings.address}/v1/{path}",
            json=body,
            headers=headers,
            verify=self._verify,
            timeout=TIMEOUT_SECONDS,
        )
        if answer.status_code in (200, 204):
            found: dict[str, Any] = answer.json() if answer.content else {}
            return found
        raise _refusal(answer.status_code, login=not signed)


def _refusal(status: int, *, login: bool) -> AdapterError:
    if login and status in (400, 401, 403):
        return AdapterError("auth", say("Vault refused the role ID or the secret ID"))
    if status in (401, 403):
        return AdapterError("auth", say("Vault denied this; check the token's or the role's policy"))
    if status == 404:
        return AdapterError("config", say("Vault has nothing at this path"))
    if status == 503:
        return AdapterError("unknown", say("Vault is sealed or not ready"))
    return AdapterError("unknown", say("Vault refused the request; test the account in Preferences"))


def _stored(vault: _Session, request: StoredSecret) -> IssuedSecret:
    """A KV secret at `mount/path`, version 1 or 2 as the mount says."""
    path = request.name.strip("/")
    if "/" not in path:
        raise AdapterError("config", say("Name the secret as MOUNT/PATH"))
    mount_info = vault.get(f"sys/internal/ui/mounts/{path}").get("data", {})
    mount = str(mount_info.get("path", "")).strip("/")
    if not mount or not path.startswith(mount + "/"):
        raise AdapterError("config", say("Vault has nothing at this path"))
    rest = path[len(mount) + 1 :]
    if str(mount_info.get("options", {}).get("version", "1")) == "2":
        data = vault.get(f"{mount}/data/{rest}").get("data", {}).get("data")
    else:
        data = vault.get(f"{mount}/{rest}").get("data")
    if not isinstance(data, dict):
        raise AdapterError("config", say("Vault has nothing at this path"))
    return read_secret(json.dumps(data), request)


def _database(vault: _Session, request: VaultDatabaseCredentials) -> IssuedSecret:
    """Credentials Vault makes for this asking; the lease is their life."""
    answer = vault.get(f"{request.mount.strip('/')}/creds/{request.role}")
    data = answer.get("data", {})
    user, password = data.get("username"), data.get("password")
    if not isinstance(user, str) or not isinstance(password, str):
        raise AdapterError("config", say("This Vault role does not make database credentials"))
    lease = answer.get("lease_duration")
    expires_at = time.time() + float(lease) if isinstance(lease, int | float) and lease > 0 else None
    return IssuedSecret(value=password, user=user, expires_at=expires_at)
