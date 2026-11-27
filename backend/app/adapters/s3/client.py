"""The boto3 client a connection signs its requests with, and its failures as
kinds (D379).

`boto3`, `botocore` and `s3transfer` are imported by this package and by
nothing else, the rule `psycopg` follows.

A client is made once per set of options and kept: making one loads the
service model, a tenth of a second spent on every request otherwise. boto3's
clients are safe to share between threads; making one is not, hence the lock.
"""

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import boto3
import botocore.session
from botocore.config import Config
from botocore.credentials import DeferredRefreshableCredentials
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
    SSLError,
)
from pydantic import SecretStr

from app.adapters.cloud import IssuedSecret
from app.adapters.errors import ErrorKind
from app.adapters.protocol import AdapterError
from app.adapters.s3.options import S3AccessKey, S3Options
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

if TYPE_CHECKING:
    # The stubs are a development dependency; at run time the client is untyped.
    from types_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)

# Enough for every connection one person has open at once; an evicted client
# is made again on the next request.
_KEPT = 32
_clients: OrderedDict[str, S3Client] = OrderedDict()
_lock = threading.Lock()


# The keys an account signs with now, asked from a worker thread (D453).
type Keys = Callable[[], IssuedSecret]

# botocore asks for an account's keys this long before they expire; the cache
# of issued secrets renews a minute before, so the keys it answers are new.
_RENEW_SECONDS = 50


def identity_of(options: S3Options) -> str:
    """One string for a store, a key or an account, and where browsing stands.

    Hashed because it holds the secret. Two keys may read different objects,
    so the copies of their files are kept apart by it (D152). An account is
    named by its id, never by keys it was issued: those change every hour.
    """
    revealed = {
        name: value.get_secret_value() if isinstance(value, SecretStr) else value
        for name, value in options
    }
    dumped = json.dumps(revealed, sort_keys=True, default=str)
    return hashlib.sha256(dumped.encode()).hexdigest()


def client_for(options: S3Options, keys: Keys | None = None) -> S3Client:
    key = identity_of(options)
    with _lock:
        found = _clients.get(key)
        if found is not None:
            _clients.move_to_end(key)
            return found
        made = _made(options, keys)
        _clients[key] = made
        while len(_clients) > _KEPT:
            _clients.popitem(last=False)
        return made


def _made(options: S3Options, keys: Keys | None) -> S3Client:
    config = Config(
        region_name=options.region_name,
        s3={"addressing_style": "path" if options.path_style else "virtual"},
        # Since 1.36 boto3 sends and checks CRC checksums by default, and
        # several compatible stores refuse or mangle them.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        connect_timeout=10,
        read_timeout=60,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    session = _session(options, keys)
    return session.client(
        "s3",
        endpoint_url=options.endpoint or None,
        verify=options.verify_tls,
        config=config,
    )


def _session(options: S3Options, keys: Keys | None) -> boto3.session.Session:
    if isinstance(options, S3AccessKey):
        return boto3.session.Session(
            aws_access_key_id=options.access_key_id,
            aws_secret_access_key=options.secret_access_key.get_secret_value(),
            region_name=options.region_name,
        )
    if keys is None:
        raise AdapterError(
            "config", say("This connection signs in with a cloud account, and none is at hand")
        )
    asked = keys

    def refresh() -> dict[str, str | None]:
        found = asked()
        expires = found.expires_at if found.expires_at is not None else time.time() + 3600
        return {
            "access_key": found.user,
            "secret_key": found.value,
            "token": found.session_token,
            "expiry_time": datetime.fromtimestamp(expires, UTC).isoformat(),
        }

    # Asked at the first request, which runs in a worker thread, and again
    # before the keys expire: a role's session lasts an hour, the client longer.
    credentials = _AccountKeys(refresh_using=refresh, method="dataplayer-account")
    core = botocore.session.get_session()
    # boto3 takes credentials only as values; refreshing ones go on the core
    # session, which is where botocore's own providers put theirs.
    core._credentials = credentials  # type: ignore[attr-defined]  # botocore's own slot, undeclared in its stubs
    return boto3.session.Session(botocore_session=core, region_name=options.region_name)


class _AccountKeys(DeferredRefreshableCredentials):
    """Asked again just before they expire rather than ten minutes before:
    the issued secrets' cache keeps them until a minute before (D449)."""

    _advisory_refresh_timeout = _RENEW_SECONDS
    _mandatory_refresh_timeout = _RENEW_SECONDS


def error_code(failure: ClientError) -> str:
    return str(failure.response.get("Error", {}).get("Code", ""))


def status_of(failure: ClientError) -> int:
    return int(failure.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))


def is_missing(failure: BaseException) -> bool:
    """A key or a bucket that is not there, which a HEAD says only by its status."""
    return isinstance(failure, ClientError) and (
        error_code(failure) in ("NoSuchKey", "NotFound", "404")
        or status_of(failure) == 404
    )


def reduced(failure: BaseException) -> AdapterError:
    """botocore's failure as a kind and a sentence of this repository's.

    Logged here and never passed on: botocore's words name the endpoint, the
    bucket and the access key id.
    """
    known = _known(failure)
    if known is not None:
        logger.warning("S3 failed: %r", failure)
        return known
    ref = record_failure(logger, "S3: an unexpected failure", failure)
    return AdapterError("unknown", with_ref(say("The store could not do that"), ref))


_BY_CODE: dict[str, tuple[ErrorKind, str]] = {
    "InvalidAccessKeyId": ("auth", N_("The store does not know this access key")),
    "SignatureDoesNotMatch": (
        "auth",
        N_("The secret key does not match the access key"),
    ),
    "AccessDenied": ("auth", N_("The store does not let this key do that")),
    "AllAccessDisabled": ("auth", N_("The store does not let this key do that")),
    "NoSuchBucket": ("config", N_("There is no such bucket in this store")),
    "PermanentRedirect": (
        "config",
        N_("The bucket is in another region than this connection names"),
    ),
    "AuthorizationHeaderMalformed": (
        "config",
        N_("The bucket is in another region than this connection names"),
    ),
    "InvalidObjectState": (
        "unknown",
        N_("This object is archived and has to be restored first"),
    ),
}


def _known(failure: BaseException) -> AdapterError | None:
    if isinstance(failure, ClientError):
        found = _BY_CODE.get(error_code(failure))
        if found is not None:
            kind, sentence = found
            return AdapterError(kind, say(sentence))
        if status_of(failure) == 403:
            return AdapterError("auth", say("The store does not let this key do that"))
        if is_missing(failure):
            return AdapterError("unknown", say("That is no longer in the store"))
        return None
    if isinstance(failure, SSLError):
        return AdapterError("config", say("The store's certificate was not accepted"))
    if isinstance(failure, ConnectTimeoutError | ReadTimeoutError):
        return AdapterError("timeout", say("The store did not answer in time"))
    if isinstance(failure, EndpointConnectionError):
        return AdapterError("network", say("Could not reach the store"))
    if isinstance(failure, BotoCoreError):
        return AdapterError("network", say("Could not reach the store"))
    return None
