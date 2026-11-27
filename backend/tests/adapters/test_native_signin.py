"""Methods particular to one engine (D456): Kafka's OAUTHBEARER over OIDC and
MongoDB's X.509, proven by what their drivers are handed. Redis ACL users and
Kafka's mutual TLS are proven against servers in `test_tls_servers.py` and
`test_tls.py`."""

from typing import Any

import pytest

from app.adapters import options as options_schema
from app.adapters.kafka.console import client_properties
from app.adapters.kafka.options import KafkaOauthOidc, KafkaOptions
from app.adapters.kafka.session import KafkaSession
from app.adapters.mongodb import session as mongodb_session
from app.adapters.mongodb.options import MongodbX509
from app.adapters.mongodb.session import auth_query, make_client
from app.adapters.protocol import AdapterError

ENDPOINT = "https://login.example.com/oauth2/token"


@pytest.fixture(scope="module")
def pair() -> tuple[str, str]:
    """A self-signed client certificate and its key, as PEM."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "app")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    )


def _oidc(**changes: Any) -> KafkaOauthOidc:
    return KafkaOauthOidc.model_validate(
        {
            "auth_method": "oauthbearer_oidc",
            "bootstrap_servers": "broker:9093",
            "tls_mode": "verify_full",
            "token_endpoint": ENDPOINT,
            "client_id": "dataplayer",
            "client_secret": "oidc-s3cret",
            **changes,
        }
    )


def test_librdkafka_is_told_to_fetch_the_token_itself() -> None:
    config = KafkaSession(_oidc(scope="kafka")).config()

    assert config["security.protocol"] == "SASL_SSL"
    assert config["sasl.mechanism"] == "OAUTHBEARER" and config["sasl.oauthbearer.method"] == "oidc"
    assert config["sasl.oauthbearer.token.endpoint.url"] == ENDPOINT
    assert config["sasl.oauthbearer.client.id"] == "dataplayer"
    assert config["sasl.oauthbearer.client.secret"] == "oidc-s3cret"
    assert config["sasl.oauthbearer.scope"] == "kafka"
    assert "sasl.oauthbearer.scope" not in KafkaSession(_oidc()).config()


def test_the_client_secret_is_kept_as_a_secret() -> None:
    assert "client_secret" in options_schema.secret_field_names(KafkaOptions)


@pytest.mark.parametrize("endpoint", ["login.example.com/token", "ftp://login/token", "https://u:p@login/token"])
def test_a_token_endpoint_is_an_http_address_without_credentials(endpoint: str) -> None:
    with pytest.raises(ValueError, match="token endpoint"):
        _oidc(token_endpoint=endpoint)


def test_kafka_s_tools_say_they_cannot_sign_in_with_oidc_yet() -> None:
    with pytest.raises(AdapterError, match="cannot sign in with OIDC"):
        client_properties(_oidc())


def _x509(pair: tuple[str, str], **changes: Any) -> MongodbX509:
    certificate, key = pair
    return MongodbX509.model_validate(
        {
            "auth_method": "x509",
            "host": "db.example.com",
            "tls_mode": "verify_full",
            "tls_client_certificate": certificate,
            "tls_client_key": key,
            **changes,
        }
    )


async def test_mongodb_signs_in_by_its_certificate_and_sends_no_password(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[str, str]
) -> None:
    made: dict[str, Any] = {}
    monkeypatch.setattr(mongodb_session, "AsyncMongoClient", lambda **kwargs: made.update(kwargs))
    monkeypatch.setattr(mongodb_session, "_tls_arguments", lambda *_: {"tls": True})
    options = _x509(pair)

    signed = await options.sign_in(None)
    make_client("db.example.com", 27017, options, signed, pool_size=1)

    assert made["authMechanism"] == "MONGODB-X509" and made["authSource"] == "$external"
    assert "password" not in made and "username" not in made
    assert ("authMechanism", "MONGODB-X509") in auth_query(signed)


async def test_a_subject_named_is_the_user(monkeypatch: pytest.MonkeyPatch, pair: tuple[str, str]) -> None:
    made: dict[str, Any] = {}
    monkeypatch.setattr(mongodb_session, "AsyncMongoClient", lambda **kwargs: made.update(kwargs))
    monkeypatch.setattr(mongodb_session, "_tls_arguments", lambda *_: {"tls": True})
    options = _x509(pair, user="CN=app,OU=data,O=example")

    make_client("db.example.com", 27017, options, await options.sign_in(None), pool_size=1)

    assert made["username"] == "CN=app,OU=data,O=example" and "password" not in made


@pytest.mark.parametrize(
    ("changes", "said"),
    [
        # The TLS block refuses a certificate without TLS before X.509 asks.
        ({"tls_mode": "disabled"}, "A client certificate needs TLS switched on"),
        ({"tls_client_certificate": "", "tls_client_key": ""}, "X.509 sign-in needs TLS"),
    ],
)
def test_x509_needs_tls_and_a_client_certificate(
    changes: dict[str, Any], said: str, pair: tuple[str, str]
) -> None:
    with pytest.raises(ValueError, match=said):
        _x509(pair, **changes)
