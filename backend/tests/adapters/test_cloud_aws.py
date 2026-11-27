"""Amazon Web Services as the provider of an account's secrets (D449, D453, D454).

STS and Secrets Manager answer through moto, in this process; RDS, ElastiCache
and MSK tokens are signed here and need no server. Nothing reaches AWS.
"""

import base64
import json
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.adapters import cloud
from app.adapters.cloud.accounts import AwsAccessKey, AwsDefaultChain, VaultToken
from app.adapters.cloud.aws.issuer import AwsIssuer
from app.adapters.cloud.requests import (
    CloudCredentials,
    ElastiCacheToken,
    MskToken,
    RdsAuthToken,
    StoredSecret,
)
from app.adapters.protocol import AdapterError

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def _key(**changes: Any) -> AwsAccessKey:
    return AwsAccessKey.model_validate(
        {
            "method": "aws_access_key",
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": SECRET,
            "region": "eu-west-1",
            **changes,
        }
    )


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # moto answers whatever key it is given; the environment's own is not read.
    for name in ("AWS_PROFILE", "AWS_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)
    with mock_aws():
        yield


def test_the_provider_of_aws_accounts_is_installed() -> None:
    import app.adapters  # noqa: F401 - registers every provider

    assert isinstance(cloud.issuer_for("aws"), AwsIssuer)


@pytest.mark.usefixtures("aws")
def test_a_test_says_who_the_account_signs_in_as() -> None:
    said = AwsIssuer().test(_key())

    assert said.startswith("Signed in as arn:aws:")


@pytest.mark.usefixtures("aws")
def test_a_role_is_assumed_and_its_keys_expire_with_its_session() -> None:
    account = _key(role_arn="arn:aws:iam::123456789012:role/reader", external_id="x-1")

    keys = AwsIssuer().issue(account, CloudCredentials(region=""))

    assert keys.user is not None and keys.user != "AKIAIOSFODNN7EXAMPLE"
    assert keys.session_token
    assert keys.expires_at is not None and keys.expires_at > time.time()


@pytest.mark.usefixtures("aws")
def test_a_static_key_is_handed_over_as_it_is_and_never_expires() -> None:
    keys = AwsIssuer().issue(_key(session_token="FwoGZXIvYXdz"), CloudCredentials(region=""))

    assert (keys.user, keys.value, keys.session_token) == ("AKIAIOSFODNN7EXAMPLE", SECRET, "FwoGZXIvYXdz")
    assert keys.expires_at is None


@pytest.mark.usefixtures("aws")
def test_a_json_secret_is_read_by_its_keys() -> None:
    manager = boto3.client("secretsmanager", region_name="eu-west-1")
    manager.create_secret(Name="prod/db", SecretString=json.dumps({"username": "app", "pwd": "s3cret"}))

    found = AwsIssuer().issue(_key(), StoredSecret("prod/db", password_key="pwd"))

    assert (found.user, found.value, found.expires_at) == ("app", "s3cret", None)


@pytest.mark.usefixtures("aws")
def test_a_secret_that_is_not_json_is_the_password_whole() -> None:
    boto3.client("secretsmanager", region_name="eu-west-1").create_secret(
        Name="plain", SecretString="just-a-password"
    )

    found = AwsIssuer().issue(_key(), StoredSecret("plain"))

    assert (found.user, found.value) == (None, "just-a-password")


@pytest.mark.usefixtures("aws")
def test_a_secret_without_the_key_named_says_which_key() -> None:
    boto3.client("secretsmanager", region_name="eu-west-1").create_secret(
        Name="other", SecretString=json.dumps({"secret": "s3cret"})
    )

    with pytest.raises(AdapterError) as refused:
        AwsIssuer().issue(_key(), StoredSecret("other"))

    assert refused.value.error_kind == "config"
    assert "password" in refused.value.message and "s3cret" not in refused.value.message


@pytest.mark.usefixtures("aws")
def test_a_missing_secret_is_said_as_missing() -> None:
    with pytest.raises(AdapterError) as refused:
        AwsIssuer().issue(_key(), StoredSecret("nothing/here"))

    assert refused.value.message == "AWS has no such secret in this region"


def test_an_rds_token_is_signed_for_the_host_port_and_user() -> None:
    token = AwsIssuer().issue(_key(), RdsAuthToken("db.example.com", 5432, "iam_user", "eu-west-1"))

    parts = urlsplit("https://" + token.value)
    query = parse_qs(parts.query)
    assert parts.netloc == "db.example.com:5432"
    assert query["Action"] == ["connect"] and query["DBUser"] == ["iam_user"]
    assert query["X-Amz-Expires"] == ["900"] and "X-Amz-Signature" in query
    assert "/eu-west-1/rds-db/" in query["X-Amz-Credential"][0]
    assert token.expires_at is not None and 890 < token.expires_at - time.time() <= 900


@pytest.mark.parametrize(("serverless", "service"), [(False, "elasticache"), (True, "memorydb")])
def test_an_elasticache_token_is_a_signed_connect_without_its_scheme(serverless: bool, service: str) -> None:
    token = AwsIssuer().issue(
        _key(), ElastiCacheToken("orders", "app-user", "eu-west-1", serverless, service)
    )

    parts = urlsplit("https://" + token.value)
    query = parse_qs(parts.query)
    assert not token.value.startswith("https://")
    assert parts.netloc == "orders"
    assert query["Action"] == ["connect"] and query["User"] == ["app-user"]
    assert ("ResourceType" in query) is serverless
    assert f"/eu-west-1/{service}/" in query["X-Amz-Credential"][0]


def test_an_msk_token_is_a_signed_connect_in_base64url() -> None:
    token = AwsIssuer().issue(_key(), MskToken("eu-west-1"))

    padded = token.value + "=" * (-len(token.value) % 4)
    url = base64.urlsafe_b64decode(padded).decode()
    query = parse_qs(urlsplit(url).query)
    assert url.startswith("https://kafka.eu-west-1.amazonaws.com/?")
    assert query["Action"] == ["kafka-cluster:Connect"] and query["User-Agent"] == ["dataplayer"]
    assert "/eu-west-1/kafka-cluster/" in query["X-Amz-Credential"][0]
    assert "=" not in token.value


def test_this_server_without_credentials_of_its_own_is_said_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", raising=False)
    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_FULL_URI", raising=False)

    with pytest.raises(AdapterError) as refused:
        AwsIssuer().issue(AwsDefaultChain(method="aws_default_chain"), CloudCredentials(region=""))

    assert refused.value.error_kind == "auth"
    assert "no AWS credentials" in refused.value.message


@pytest.mark.parametrize(
    ("code", "said"),
    [
        ("InvalidClientTokenId", "AWS does not accept this access key"),
        ("ExpiredToken", "These AWS credentials have expired"),
        ("AccessDenied", "AWS denied this"),
        ("Throttling", "AWS refused the request"),
    ],
)
def test_a_refusal_is_said_by_its_code_and_never_by_its_text(
    monkeypatch: pytest.MonkeyPatch, code: str, said: str
) -> None:
    class Refusing:
        def get_caller_identity(self) -> None:
            raise ClientError(
                {"Error": {"Code": code, "Message": f"The key {SECRET} is wrong"}}, "GetCallerIdentity"
            )

    monkeypatch.setattr(boto3.session.Session, "client", lambda *_, **__: Refusing())

    with pytest.raises(AdapterError) as refused:
        AwsIssuer().test(_key())

    assert refused.value.message.startswith(said)
    assert SECRET not in refused.value.message and "wrong" not in refused.value.message
    assert refused.value.__cause__ is None


def test_another_kind_s_account_or_question_is_refused() -> None:
    vault = VaultToken(method="vault_token", address="https://vault:8200", token="t")

    with pytest.raises(AdapterError):
        AwsIssuer().issue(vault, CloudCredentials(region=""))
    with pytest.raises(AdapterError):
        AwsIssuer().issue(_key(), cloud.SecretRequest())
