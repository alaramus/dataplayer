"""What an AWS account is asked for, answered through boto3 (D449, D453, D454, D461).

Synchronous: the caller runs every method in a thread. Every refusal is worded
here from botocore's error code, never from its message, which can quote a
key id or a signed request (D184).

boto3 reads `AWS_ENDPOINT_URL` and its per-service forms from the environment;
the test stand points them at LocalStack, and nothing a person types can.
"""

import base64
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import boto3
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.credentials import ReadOnlyCredentials
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
)
from pydantic import BaseModel

from app.adapters.cloud import IssuedSecret, Region, SecretRequest
from app.adapters.cloud.accounts import AwsAccessKey, AwsDefaultChain
from app.adapters.cloud.aws.regions import account_regions, published_regions
from app.adapters.cloud.requests import (
    CloudCredentials,
    ElastiCacheToken,
    MskToken,
    RdsAuthToken,
    StoredSecret,
)
from app.adapters.cloud.stored import read_secret
from app.adapters.protocol import AdapterError
from app.core.translation import say

DEFAULT_REGION = "us-east-1"
# What RDS, ElastiCache and MSK accept a signed token for.
TOKEN_SECONDS = 900
_CONFIG = Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 2, "mode": "standard"})

# Error codes by what a person should check. Codes, not messages: a message
# can quote the key id.
_DENIED = {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}
_BAD_KEY = {
    "InvalidClientTokenId",
    "UnrecognizedClientException",
    "SignatureDoesNotMatch",
    "IncompleteSignature",
    "InvalidSignatureException",
}
_EXPIRED = {"ExpiredToken", "ExpiredTokenException", "RequestExpired", "TokenRefreshRequired"}
_MISSING = {"ResourceNotFoundException", "NoSuchEntity"}
_DECRYPTION = {"DecryptionFailure", "KMSAccessDeniedException"}


class AwsIssuer:
    def issue(self, account: BaseModel, request: SecretRequest) -> IssuedSecret:
        settings = _aws(account)
        try:
            return self._issue(settings, request)
        except AdapterError:
            raise
        except (ClientError, BotoCoreError) as failure:
            raise _reduced(failure) from None

    def test(self, account: BaseModel) -> str:
        settings = _aws(account)
        try:
            found = _session(settings).session.client("sts", config=_CONFIG).get_caller_identity()
        except (ClientError, BotoCoreError) as failure:
            raise _reduced(failure) from None
        return say("Signed in as {identity}", identity=str(found.get("Arn", "")))

    def regions(self, account: BaseModel | None) -> list[Region]:
        if account is None:
            return published_regions()
        try:
            session = _session(_aws(account)).session
        except (AdapterError, ClientError, BotoCoreError):
            return published_regions()
        return account_regions(session, _CONFIG)

    def _issue(self, settings: AwsAccessKey | AwsDefaultChain, request: SecretRequest) -> IssuedSecret:
        if isinstance(request, StoredSecret):
            return _stored(_session(settings).session, request)
        if isinstance(request, RdsAuthToken):
            session = _session(settings, request.region).session
            token = session.client("rds", region_name=_region(request.region, settings)).generate_db_auth_token(
                DBHostname=request.host,
                Port=request.port,
                DBUsername=request.user,
                Region=_region(request.region, settings),
            )
            return IssuedSecret(value=str(token), expires_at=time.time() + TOKEN_SECONDS)
        if isinstance(request, ElastiCacheToken):
            return _elasticache(
                _session(settings, request.region).session, request, _region(request.region, settings)
            )
        if isinstance(request, MskToken):
            return _msk(_session(settings, request.region).session, _region(request.region, settings))
        if isinstance(request, CloudCredentials):
            return _credentials(_session(settings, request.region))
        raise AdapterError("config", say("An account of Amazon Web Services cannot be asked for this"))


def _aws(account: BaseModel) -> AwsAccessKey | AwsDefaultChain:
    if not isinstance(account, AwsAccessKey | AwsDefaultChain):
        raise AdapterError("config", say("An account of Amazon Web Services cannot be asked for this"))
    return account


def _region(asked: str, settings: AwsAccessKey | AwsDefaultChain) -> str:
    return asked or settings.region or DEFAULT_REGION


@dataclass(frozen=True)
class _Signed:
    """A session, and when its keys stop working when that is known: an
    assumed role's do with its session."""

    session: boto3.session.Session
    expires_at: float | None


def _session(settings: AwsAccessKey | AwsDefaultChain, region: str = "") -> _Signed:
    """The account signed in, and the role assumed over it when one is named."""
    region_name = _region(region, settings)
    if isinstance(settings, AwsAccessKey):
        session = boto3.session.Session(
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key.get_secret_value(),
            aws_session_token=settings.session_token.get_secret_value() or None,
            region_name=region_name,
        )
    else:
        session = boto3.session.Session(region_name=region_name)
        if session.get_credentials() is None:
            raise AdapterError("auth", say("This server has no AWS credentials of its own to sign in with"))
    if not settings.role_arn:
        return _Signed(session, None)
    arguments: dict[str, Any] = {
        "RoleArn": settings.role_arn,
        "RoleSessionName": settings.session_name,
        "DurationSeconds": settings.duration_minutes * 60,
    }
    if settings.external_id:
        arguments["ExternalId"] = settings.external_id
    try:
        found = session.client("sts", config=_CONFIG).assume_role(**arguments)["Credentials"]
    except ClientError as failure:
        if _code(failure) in _DENIED:
            raise AdapterError(
                "auth",
                say("The role could not be assumed; check its trust policy and the external ID"),
            ) from None
        raise
    return _Signed(
        boto3.session.Session(
            aws_access_key_id=found["AccessKeyId"],
            aws_secret_access_key=found["SecretAccessKey"],
            aws_session_token=found["SessionToken"],
            region_name=region_name,
        ),
        found["Expiration"].timestamp(),
    )


def _stored(session: boto3.session.Session, request: StoredSecret) -> IssuedSecret:
    """A secret of Secrets Manager: JSON read by its keys, or the password whole."""
    found = session.client("secretsmanager", config=_CONFIG).get_secret_value(SecretId=request.name)
    text = found.get("SecretString")
    if not isinstance(text, str):
        raise AdapterError("config", say("The secret holds no text; a password is kept as text"))
    return read_secret(text, request)


def _frozen(session: boto3.session.Session) -> ReadOnlyCredentials:
    credentials = session.get_credentials()
    if credentials is None:
        raise AdapterError("auth", say("This server has no AWS credentials of its own to sign in with"))
    return credentials.get_frozen_credentials()


def _presigned(url: str, service: str, region: str, credentials: ReadOnlyCredentials) -> str:
    request = AWSRequest(method="GET", url=url)
    SigV4QueryAuth(credentials, service, region, expires=TOKEN_SECONDS).add_auth(request)
    return str(request.url)


def _elasticache(session: boto3.session.Session, request: ElastiCacheToken, region: str) -> IssuedSecret:
    """A signed `connect` for one cache and user, without its scheme, as
    ElastiCache and MemoryDB take it for the password."""
    query = {"Action": "connect", "User": request.user}
    if request.serverless:
        query["ResourceType"] = "ServerlessCache"
    url = f"https://{request.cache_name}/?{urlencode(query)}"
    signed = _presigned(url, request.service, region, _frozen(session))
    return IssuedSecret(value=signed.removeprefix("https://"), expires_at=time.time() + TOKEN_SECONDS)


def _msk(session: boto3.session.Session, region: str) -> IssuedSecret:
    """MSK's OAUTHBEARER token: a signed `kafka-cluster:Connect`, base64url."""
    url = f"https://kafka.{region}.amazonaws.com/?{urlencode({'Action': 'kafka-cluster:Connect'})}"
    signed = _presigned(url, "kafka-cluster", region, _frozen(session))
    signed += "&" + urlencode({"User-Agent": "dataplayer"})
    token = base64.urlsafe_b64encode(signed.encode()).decode().rstrip("=")
    return IssuedSecret(value=token, expires_at=time.time() + TOKEN_SECONDS)


def _credentials(signed: _Signed) -> IssuedSecret:
    """The keys a driver signs with itself. Temporary ones expire with the
    role's session; a static key is read again within minutes."""
    session = signed.session
    frozen = _frozen(session)
    if frozen.secret_key is None or frozen.access_key is None:
        raise AdapterError("auth", say("This server has no AWS credentials of its own to sign in with"))
    expires_at = signed.expires_at
    if expires_at is None:
        # Refreshable credentials of this server's own chain, a role among them.
        expiry = getattr(session.get_credentials(), "_expiry_time", None)
        expires_at = expiry.timestamp() if expiry is not None else None
    return IssuedSecret(
        value=frozen.secret_key,
        user=frozen.access_key,
        session_token=frozen.token,
        expires_at=expires_at,
    )


def _code(failure: ClientError) -> str:
    return str(failure.response.get("Error", {}).get("Code", ""))


def _reduced(failure: ClientError | BotoCoreError) -> AdapterError:
    """botocore's failure as what to check."""
    if isinstance(failure, NoCredentialsError | PartialCredentialsError):
        return AdapterError("auth", say("This server has no AWS credentials of its own to sign in with"))
    if isinstance(failure, NoRegionError):
        return AdapterError("config", say("Name the AWS region of the account or the connection"))
    if isinstance(failure, EndpointConnectionError):
        return AdapterError("network", say("AWS could not be reached; check the region and the network"))
    if not isinstance(failure, ClientError):
        return AdapterError("unknown", say("AWS did not answer as expected"))
    code = _code(failure)
    if code in _BAD_KEY:
        return AdapterError("auth", say("AWS does not accept this access key; check the key and its secret"))
    if code in _EXPIRED:
        return AdapterError("auth", say("These AWS credentials have expired; give the account fresh ones"))
    if code in _DENIED:
        return AdapterError("auth", say("AWS denied this; check the policy of the account or the role"))
    if code in _MISSING:
        return AdapterError("config", say("AWS has no such secret in this region"))
    if code in _DECRYPTION:
        return AdapterError("auth", say("The secret's KMS key may not be used by this account"))
    return AdapterError("unknown", say("AWS refused the request; test the account in Preferences"))
