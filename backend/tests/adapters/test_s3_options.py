"""The S3 connection form and the failures of the store, without a store (D379)."""

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import ValidationError

import app.adapters  # noqa: F401 - registers the source types
from app.adapters import registry
from app.adapters.protocol import AdapterError
from app.adapters.s3.adapter import S3Adapter
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


# --- the address, and the cards (D382) -------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("s3://reports", {"bucket": "reports", "prefix": ""}),
        ("s3://reports/2026/q1", {"bucket": "reports", "prefix": "2026/q1"}),
        (
            "https://reports.s3.eu-central-1.amazonaws.com/2026",
            {"endpoint": "", "region": "eu-central-1"},
        ),
        (
            "https://s3.eu-west-2.amazonaws.com/reports",
            {"endpoint": "", "region": "eu-west-2"},
        ),
        ("https://s3-us-west-1.amazonaws.com", {"endpoint": "", "region": "us-west-1"}),
        ("https://reports.s3.amazonaws.com", {"endpoint": "", "region": ""}),
        (
            "http://127.0.0.1:9000/reports/2026",
            {"endpoint": "http://127.0.0.1:9000"},
        ),
        (
            "https://storage.yandexcloud.net",
            {"endpoint": "https://storage.yandexcloud.net"},
        ),
    ],
)
def test_an_address_fills_where_the_store_is(
    url: str, expected: dict[str, str]
) -> None:
    found = S3Adapter.options_from_url(url)

    assert found == expected
    _options(**found)


def test_a_part_erased_from_the_address_is_erased_from_the_form() -> None:
    """The form merges what the address answers into what it holds, so a part
    left unanswered would come back as it was before it was erased."""
    assert S3Adapter.options_from_url("s3://reports/") == {
        "bucket": "reports",
        "prefix": "",
    }
    assert S3Adapter.options_from_url("https://s3.amazonaws.com")["region"] == ""


@pytest.mark.parametrize(
    "url",
    [
        "s3://key:secret@reports",
        "https://key@s3.example.com/reports",
        "https://s3.example.com/reports?X-Amz-Signature=abc",
        "ftp://s3.example.com/reports",
        "https://ec2.eu-central-1.amazonaws.com/",
        "not an address",
    ],
)
def test_an_address_with_a_key_or_not_of_s3_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        S3Adapter.options_from_url(url)


def test_the_address_shown_is_the_store_and_carries_no_key() -> None:
    aws = _options(region="eu-central-1", bucket="reports", prefix="2026/q1")
    elsewhere = _options(endpoint="http://127.0.0.1:9000", bucket="reports")

    assert (
        S3Adapter.draft_connection_string(aws.model_dump())
        == "https://s3.eu-central-1.amazonaws.com"
    )
    assert (
        S3Adapter.draft_connection_string(elsewhere.model_dump())
        == "http://127.0.0.1:9000"
    )
    assert S3Adapter.draft_connection_string(_options().model_dump()) is None
    for options in (aws, elsewhere):
        text = S3Adapter.draft_connection_string(options.model_dump()) or ""
        assert SECRET not in text and KEY_ID not in text
        found = S3Adapter.options_from_url(text)
        assert {name: getattr(options, name) for name in found} == found


def test_every_card_is_one_form_filled_in_and_starts_nothing() -> None:
    kind = registry.get("s3")

    assert [face.key for face in kind.faces] == [
        "s3",
        "minio",
        "rustfs",
        "cloudflare-r2",
        "backblaze-b2",
        "wasabi",
        "digitalocean-spaces",
        "gcs",
        "yandex-object-storage",
        "vk-cloud",
        "selectel",
        "hetzner",
    ]
    for face in kind.faces:
        assert face.templates == ()
        assert face.note and face.note_link and face.note_link.startswith("https://")
        _options(**face.options)
