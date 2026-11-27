"""A person's cloud accounts: write-only, owned, gated and asked for (D449, D451, D452)."""

import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Literal

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import cloud, registry
from app.adapters.cloud import IssuedSecret, SecretRequest, account_field
from app.adapters.cloud.accounts import AwsAccessKey
from app.adapters.protocol import AdapterError
from app.connectors import cloud_accounts
from app.connectors.access import context_for
from app.connectors.cloud_accounts import CloudAccount, OwnerCloud
from app.core.config import settings
from app.users import crud
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/cloud-accounts"
CONNECTORS = f"{settings.API_V1_STR}/connectors"

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
KEY = {"method": "aws_access_key", "access_key_id": "AKIAIOSFODNN7EXAMPLE", "secret_access_key": SECRET}
VAULT = {"method": "vault_token", "address": "https://vault.example.com:8200", "token": "hvs.s3cret"}


@dataclass(frozen=True)
class Token(SecretRequest):
    host: str


class FakeIssuer:
    """Issues `<secret>-<n>` so a test sees which credentials and how often."""

    def __init__(self) -> None:
        self.calls = 0
        self.fails: Exception | None = None

    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret:
        if self.fails is not None:
            raise self.fails
        self.calls += 1
        assert isinstance(account, AwsAccessKey)
        secret = account.secret_access_key.get_secret_value()
        return IssuedSecret(value=f"{secret}-{self.calls}", expires_at=None)

    def test(self, account: BaseModel) -> str:
        if self.fails is not None:
            raise self.fails
        return "Signed in as arn:aws:iam::123456789012:user/test"


@pytest.fixture
def issuer() -> Generator[FakeIssuer]:
    fake = FakeIssuer()
    saved = dict(cloud._issuers)
    cloud.register_issuer("aws", fake)
    try:
        yield fake
    finally:
        cloud._issuers.clear()
        cloud._issuers.update(saved)


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _owner(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    return uuid.UUID(me.json()["id"])


async def _make(
    client: AsyncClient, headers: dict[str, str], settings_: dict[str, Any] | None = None, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"account {uuid.uuid4().hex[:8]}", "settings": settings_ or KEY} | body,
    )
    assert response.status_code == 200, response.text
    made: dict[str, Any] = response.json()
    return made


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "db"


class _CloudyIam(_Base):
    auth_method: Literal["aws_iam"] = "aws_iam"
    account: str = account_field("aws", title="Account")


class _Cloudy:
    def __init__(self, options: Any, context: registry.AdapterContext) -> None:
        self.context = context


@pytest.fixture
def cloudy(isolated_registry: None) -> str:  # noqa: ARG001 - restores the registry
    registry.register(
        name="cloudy",
        title="Cloudy",
        category="sql",
        description="A source whose password a cloud issues.",
        options_schema=_CloudyIam,
        adapter_class=_Cloudy,  # type: ignore[arg-type]  # a stand-in names no capability
    )(_Cloudy)  # type: ignore[arg-type]  # the same stand-in, as the factory
    return "cloudy"


async def _connection(
    client: AsyncClient, headers: dict[str, str], account: str
) -> Any:
    return await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"cloudy {uuid.uuid4().hex[:8]}",
            "adapter_type": "cloudy",
            "options": {"auth_method": "aws_iam", "account": account},
        },
    )


async def test_an_account_shows_its_settings_and_none_of_its_secrets(
    client: AsyncClient, person: dict[str, str], db: AsyncSession
) -> None:
    made = await _make(client, person, KEY | {"session_token": "FwoGZXIvYXdz", "region": "eu-west-1"})
    listed = await client.get(f"{BASE}/", headers=person)
    row = await db.get(CloudAccount, uuid.UUID(made["id"]))

    assert made["kind"] == "aws"
    assert made["settings"]["region"] == "eu-west-1"
    assert made["stored_secrets"] == ["secret_access_key", "session_token"]
    assert made["ambient"] is False
    assert SECRET not in listed.text and "FwoGZXIvYXdz" not in listed.text
    assert row is not None
    assert SECRET.encode() not in row.secrets
    assert SECRET not in str(row.settings)


async def test_a_refused_setting_does_not_echo_a_secret(
    client: AsyncClient, person: dict[str, str]
) -> None:
    refused = await client.post(
        f"{BASE}/",
        headers=person,
        json={"name": "bad", "settings": KEY | {"access_key_id": "lower", "role_arn": "nope"}},
    )

    assert refused.status_code == 422
    assert SECRET not in refused.text
    assert {tuple(error["loc"]) for error in refused.json()["detail"]} >= {
        ("body", "settings", "aws_access_key", "access_key_id"),
    }
    role = next(error for error in refused.json()["detail"] if error["loc"][-1] == "role_arn")
    assert role["msg"].startswith("A role is named by its ARN")


async def test_a_name_is_one_account_per_person(
    client: AsyncClient, person: dict[str, str], normal_user_token_headers: dict[str, str]
) -> None:
    name = f"prod {uuid.uuid4().hex[:6]}"
    await _make(client, person, name=name)

    again = await client.post(f"{BASE}/", headers=person, json={"name": name, "settings": VAULT})
    elsewhere = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"name": name, "settings": VAULT}
    )

    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "cloud_accounts.name_taken"
    assert elsewhere.status_code == 200


async def test_somebody_else_s_account_answers_as_a_missing_one(
    client: AsyncClient, person: dict[str, str], normal_user_token_headers: dict[str, str]
) -> None:
    made = await _make(client, person)

    for response in (
        await client.patch(f"{BASE}/{made['id']}", headers=normal_user_token_headers, json={"name": "x"}),
        await client.delete(f"{BASE}/{made['id']}", headers=normal_user_token_headers),
        await client.post(f"{BASE}/{made['id']}/test", headers=normal_user_token_headers),
    ):
        assert response.status_code == 404
    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    assert made["id"] not in [one["id"] for one in listed.json()]


async def test_an_edit_keeps_a_secret_left_empty_and_makes_a_new_version(
    client: AsyncClient, person: dict[str, str], db: AsyncSession
) -> None:
    made = await _make(client, person)

    changed = await client.patch(
        f"{BASE}/{made['id']}",
        headers=person,
        json={"settings": KEY | {"secret_access_key": "", "region": "us-west-2"}},
    )
    row = await db.get(CloudAccount, uuid.UUID(made["id"]))
    assert row is not None
    await db.refresh(row)

    assert changed.status_code == 200, changed.text
    assert changed.json()["settings"]["region"] == "us-west-2"
    assert row.version == 2
    assert cloud_accounts.secrets_of(row)["secret_access_key"] == SECRET


async def test_an_account_keeps_its_kind(client: AsyncClient, person: dict[str, str]) -> None:
    made = await _make(client, person)

    refused = await client.patch(f"{BASE}/{made['id']}", headers=person, json={"settings": VAULT})

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "cloud_accounts.kind_fixed"


async def test_the_server_s_own_identity_is_refused_while_the_installation_does_not_lend_it(
    client: AsyncClient,
    person: dict[str, str],
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = {"method": "aws_default_chain"}
    monkeypatch.setattr(settings, "CLOUD_AMBIENT_CREDENTIALS", False)

    off = await client.post(f"{BASE}/", headers=superuser_token_headers, json={"name": "x", "settings": chain})
    schema = await client.get(f"{BASE}/schema", headers=superuser_token_headers)

    assert off.status_code == 403
    assert off.json()["detail"]["code"] == "cloud_accounts.ambient_off"
    assert schema.json()["ambient"] is False
    assert "aws_default_chain" not in schema.text

    monkeypatch.setattr(settings, "CLOUD_AMBIENT_CREDENTIALS", True)
    not_super = await client.post(f"{BASE}/", headers=person, json={"name": "x", "settings": chain})
    offered = await client.get(f"{BASE}/schema", headers=superuser_token_headers)
    not_offered = await client.get(f"{BASE}/schema", headers=person)
    made = await _make(client, superuser_token_headers, chain)

    assert not_super.status_code == 403
    assert not_super.json()["detail"]["code"] == "cloud_accounts.ambient_superuser"
    assert "aws_default_chain" in offered.text
    assert "aws_default_chain" not in not_offered.text
    assert made["ambient"] is True
    await client.delete(f"{BASE}/{made['id']}", headers=superuser_token_headers)


async def test_without_a_provider_an_account_cannot_be_tested_yet(
    client: AsyncClient, person: dict[str, str]
) -> None:
    made = await _make(client, person, VAULT)

    refused = await client.post(f"{BASE}/{made['id']}/test", headers=person)

    assert made["testable"] is False
    assert refused.status_code == 501
    assert refused.json()["detail"]["code"] == "cloud_accounts.untestable"


async def test_a_test_says_what_the_provider_found_and_never_its_text(
    client: AsyncClient, person: dict[str, str], issuer: FakeIssuer
) -> None:
    made = await _make(client, person)

    passed = await client.post(f"{BASE}/{made['id']}/test", headers=person)
    issuer.fails = RuntimeError(f"InvalidClientTokenId: {SECRET}")
    failed = await client.post(f"{BASE}/{made['id']}/test", headers=person)
    issuer.fails = AdapterError("auth", "Amazon refused these credentials")
    refused = await client.post(f"{BASE}/{made['id']}/test", headers=person)

    assert made["testable"] is True
    assert passed.json() == {"ok": True, "message": "Signed in as arn:aws:iam::123456789012:user/test"}
    assert failed.json()["ok"] is False
    assert SECRET not in failed.text and "InvalidClientTokenId" not in failed.text
    assert refused.json() == {"ok": False, "message": "Amazon refused these credentials"}


@pytest.mark.usefixtures("cloudy")
async def test_a_connection_names_only_its_owner_s_accounts_of_its_kind(
    client: AsyncClient, person: dict[str, str], normal_user_token_headers: dict[str, str]
) -> None:
    mine = await _make(client, person)
    vault = await _make(client, person, VAULT)
    theirs = await _make(client, normal_user_token_headers)

    good = await _connection(client, person, mine["id"])
    wrong_kind = await _connection(client, person, vault["id"])
    not_mine = await _connection(client, person, theirs["id"])
    moved = await client.patch(
        f"{CONNECTORS}/{good.json()['id']}",
        headers=person,
        json={"options": {"auth_method": "aws_iam", "account": vault["id"]}},
    )

    assert good.status_code == 200, good.text
    assert wrong_kind.status_code == 422
    assert "is not an account of Amazon Web Services" in wrong_kind.text
    assert not_mine.status_code == 422
    assert moved.status_code == 422


@pytest.mark.usefixtures("cloudy")
async def test_an_account_in_use_is_not_deleted_and_the_refusal_names_the_connection(
    client: AsyncClient, person: dict[str, str]
) -> None:
    made = await _make(client, person)
    connection = (await _connection(client, person, made["id"])).json()

    listed = await client.get(f"{BASE}/", headers=person)
    refused = await client.delete(f"{BASE}/{made['id']}", headers=person)
    await client.delete(f"{CONNECTORS}/{connection['id']}", headers=person)
    deleted = await client.delete(f"{BASE}/{made['id']}", headers=person)

    used_by = next(one["used_by"] for one in listed.json() if one["id"] == made["id"])
    assert used_by == [{"id": connection["id"], "name": connection["name"]}]
    assert refused.status_code == 409
    assert connection["name"] in refused.json()["detail"]["message"]
    assert deleted.status_code == 200


async def test_every_source_is_handed_its_owner_s_accounts() -> None:
    owner = uuid.uuid4()

    assert isinstance(context_for(owner).cloud, OwnerCloud)
    assert isinstance(context_for(owner).cloud, cloud.CloudAccess)


@pytest.mark.usefixtures("issuer")
async def test_a_secret_is_issued_from_the_owner_s_account_and_reused(
    client: AsyncClient, person: dict[str, str]
) -> None:
    made = await _make(client, person)
    access = OwnerCloud(await _owner(client, person))
    account = uuid.UUID(made["id"])

    first = await access.issue(account, ("aws",), Token("db.example.com"))
    again = await access.issue(account, ("aws",), Token("db.example.com"))
    other = await access.issue(account, ("aws",), Token("other.example.com"))

    assert first.value == f"{SECRET}-1"
    assert again.value == first.value
    assert other.value == f"{SECRET}-2"


@pytest.mark.usefixtures("issuer")
async def test_a_changed_account_is_never_answered_with_what_the_old_one_issued(
    client: AsyncClient,
    person: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cloud_accounts, "KEPT_SECONDS", 0.0)
    made = await _make(client, person)
    access = OwnerCloud(await _owner(client, person))
    account = uuid.UUID(made["id"])

    before = await access.issue(account, ("aws",), Token("db"))
    await client.patch(
        f"{BASE}/{made['id']}", headers=person, json={"settings": KEY | {"secret_access_key": "rotated-key"}}
    )
    after = await access.issue(account, ("aws",), Token("db"))

    assert before.value.startswith(SECRET)
    assert after.value.startswith("rotated-key")


@pytest.mark.usefixtures("issuer")
async def test_issuing_refuses_a_wrong_kind_a_stranger_and_a_deleted_account(
    client: AsyncClient,
    person: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    made = await _make(client, person)
    account = uuid.UUID(made["id"])
    stranger = OwnerCloud(await _owner(client, normal_user_token_headers))
    owner = OwnerCloud(await _owner(client, person))

    with pytest.raises(AdapterError) as wrong_kind:
        await owner.issue(account, ("gcp",), Token("db"))
    with pytest.raises(AdapterError) as not_theirs:
        await stranger.issue(account, ("aws",), Token("db"))
    await client.delete(f"{BASE}/{made['id']}", headers=person)
    with pytest.raises(AdapterError) as gone:
        await OwnerCloud(await _owner(client, person)).issue(account, ("aws",), Token("db"))

    assert wrong_kind.value.error_kind == "config"
    assert not_theirs.value.message == gone.value.message
    assert "gone" in gone.value.message


async def test_an_sdk_failure_is_said_without_its_text(
    client: AsyncClient, person: dict[str, str], issuer: FakeIssuer
) -> None:
    made = await _make(client, person)
    issuer.fails = RuntimeError(f"SignatureDoesNotMatch for {SECRET}")

    with pytest.raises(AdapterError) as failed:
        await OwnerCloud(await _owner(client, person)).issue(uuid.UUID(made["id"]), ("aws",), Token("db"))

    assert SECRET not in failed.value.message
    assert "SignatureDoesNotMatch" not in failed.value.message
    assert failed.value.__cause__ is None
    assert failed.value.__suppress_context__


async def test_the_server_s_own_identity_stops_when_the_installation_withdraws_it(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    issuer: FakeIssuer,
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    monkeypatch.setattr(settings, "CLOUD_AMBIENT_CREDENTIALS", True)
    made = await _make(client, superuser_token_headers, {"method": "aws_default_chain"})
    superuser = await crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert superuser is not None
    monkeypatch.setattr(settings, "CLOUD_AMBIENT_CREDENTIALS", False)

    with pytest.raises(AdapterError) as withdrawn:
        await OwnerCloud(superuser.id).issue(uuid.UUID(made["id"]), ("aws",), Token("db"))

    assert "no longer allowed" in withdrawn.value.message
    assert issuer.calls == 0
    await client.delete(f"{BASE}/{made['id']}", headers=superuser_token_headers)
