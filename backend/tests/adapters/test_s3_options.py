"""The S3 connection form and the failures of the store, without a store (D379)."""

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import ValidationError

from app.adapters.protocol import AdapterError
from app.adapters.s3.client import reduced
from app.adapters.s3.options import S3Options

SECRET = "wJalrXUtnFEMI-secret-K7MDENG"
KEY_ID = "AKIAIOSFODNN7EXAMPLE"


def _options(**changes: object) -> S3Options:
    return S3Options.model_validate(
        {"access_key_id": KEY_ID, "secret_access_key": SECRET, **changes}
    )


def test_an_empty_form_reaches_amazon_s3_in_its_first_region() -> None:
    options = _options()

    assert options.endpoint == ""
    assert options.region_name == "us-east-1"
    assert options.path_style is False


def test_auto_addressing_is_path_style_on_any_other_endpoint() -> None:
    assert _options(endpoint="http://127.0.0.1:9000/").path_style is True
    assert (
        _options(endpoint="https://s3.example.com", addressing="virtual").path_style
        is False
    )
    assert _options(addressing="path").path_style is True


def test_the_endpoint_is_stored_without_a_trailing_slash() -> None:
    assert (
        _options(endpoint=" https://s3.example.com/ ").endpoint
        == "https://s3.example.com"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "s3.example.com",
        "ftp://s3.example.com",
        "https://key:secret@s3.example.com",
        "https://s3.example.com/bucket",
        "https://s3.example.com?region=x",
        "https://s3.example.com:99999",
        "https://",
    ],
)
def test_an_endpoint_is_an_origin_and_nothing_else(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        _options(endpoint=endpoint)


@pytest.mark.parametrize("bucket", ["a/b", "a\\b", "..", "C:"])
def test_a_bucket_is_one_name(bucket: str) -> None:
    with pytest.raises(ValidationError):
        _options(bucket=bucket)


@pytest.mark.parametrize("prefix", ["../up", "a/../../b", "C:/x", "a\\..\\b"])
def test_a_folder_stays_inside_the_bucket(prefix: str) -> None:
    with pytest.raises(ValidationError):
        _options(bucket="data", prefix=prefix)


def test_a_folder_is_stored_without_slashes_at_its_ends() -> None:
    assert _options(bucket="data", prefix="/reports/2026/").prefix == "reports/2026"
    assert _options(bucket="data", prefix="reports//2026").prefix == "reports/2026"


def test_a_folder_needs_its_bucket() -> None:
    with pytest.raises(ValidationError):
        _options(prefix="reports")


def test_the_secret_is_not_in_what_the_options_show() -> None:
    options = _options()

    assert SECRET not in repr(options)
    assert SECRET not in options.model_dump_json()


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": code,
                "Message": f"The key {KEY_ID} with {SECRET} at https://s3.internal.example:9000",
            },
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "GetObject",
    )


@pytest.mark.parametrize(
    ("code", "status", "kind"),
    [
        ("InvalidAccessKeyId", 403, "auth"),
        ("SignatureDoesNotMatch", 403, "auth"),
        ("AccessDenied", 403, "auth"),
        ("NoSuchBucket", 404, "config"),
        ("PermanentRedirect", 301, "config"),
        ("InvalidObjectState", 403, "unknown"),
        ("SomethingNew", 500, "unknown"),
    ],
)
def test_a_refusal_of_the_store_is_a_kind_that_names_nothing(
    code: str, status: int, kind: str
) -> None:
    failure = reduced(_client_error(code, status))

    assert isinstance(failure, AdapterError)
    assert failure.error_kind == kind
    for secret in (SECRET, KEY_ID, "s3.internal.example", "9000"):
        assert secret not in failure.message


def test_an_unreachable_endpoint_is_a_network_failure_that_names_no_address() -> None:
    failure = reduced(
        EndpointConnectionError(endpoint_url="https://s3.internal.example:9000/")
    )

    assert failure.error_kind == "network"
    assert "s3.internal.example" not in failure.message
