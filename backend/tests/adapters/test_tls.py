"""The TLS block (D446), its files (D447) and a name through a tunnel (D448)."""

import datetime
import json
import os
import ssl
import uuid
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pydantic import SecretStr

from app.adapters import options as options_schema
from app.adapters import registry
from app.adapters.cassandra.console import cqlshrc
from app.adapters.kafka.options import KafkaNoAuth
from app.adapters.kafka.session import KafkaSession
from app.adapters.mongodb.options import MongodbNoPassword
from app.adapters.mongodb.session import make_client, program_tls
from app.adapters.mysql.options import MysqlUserPassword
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.redis.console import console_program as redis_console
from app.adapters.redis.options import RedisPassword
from app.adapters.tls import (
    AMAZON_RDS_BUNDLE,
    PROGRAM_FOLDER,
    TlsFiles,
    TlsOptions,
    TlsOptionsWithFallback,
    name_not_verifiable,
    program_paths,
    ssl_context,
    with_program_files,
)
from app.adapters.zookeeper.console import tls_flags
from app.connectors import service
from app.core import crypto


def _pair(name: str = "client") -> tuple[str, str, str]:
    """A certificate, its key, and the same key encrypted under `secret`."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    plain = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    locked = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"secret"),
    ).decode()
    return certificate.public_bytes(serialization.Encoding.PEM).decode(), plain, locked


@pytest.fixture(scope="module")
def pair() -> tuple[str, str, str]:
    return _pair()


def _postgres(**block: Any) -> PostgresUserPassword:
    return PostgresUserPassword(
        host="db.example.com", database="d", user="u", password=SecretStr("pw"), **block
    )


def test_postgres_and_mysql_prefer_tls_as_before() -> None:
    assert _postgres().tls().mode == "preferred"
    assert MysqlUserPassword(host="h", user="u", password=SecretStr("p")).tls_mode == "preferred"


def test_a_source_without_fallback_does_not_offer_it() -> None:
    with pytest.raises(ValueError):
        TlsOptions(tls_mode="preferred")  # type: ignore[arg-type]  # the refusal is the point


def test_every_mode_is_offered_with_a_title() -> None:
    schema = options_schema.json_schema(TlsOptionsWithFallback)["properties"]["tls_mode"]
    assert [choice["value"] for choice in schema["x-ui-choices"]] == schema["enum"]
    assert schema["group"] == "tls"


def test_a_certificate_pasted_on_one_line_is_rewrapped(pair: tuple[str, str, str]) -> None:
    certificate, _, _ = pair
    one_line = certificate.replace("\n", " ")

    block = TlsOptions(tls_mode="verify_ca", tls_trust="certificate", tls_ca_certificate=one_line)

    assert block.tls_ca_certificate == certificate
    assert ssl_context(block.tls()) is not None


def test_trusting_a_certificate_needs_one() -> None:
    with pytest.raises(ValueError, match="CA certificate"):
        TlsOptions(tls_mode="verify_full", tls_trust="certificate")


def test_a_client_certificate_needs_its_key(pair: tuple[str, str, str]) -> None:
    certificate, _, _ = pair
    with pytest.raises(ValueError, match="go together"):
        TlsOptions(tls_mode="required", tls_client_certificate=certificate)


def test_emptying_the_certificate_takes_the_key_with_it(pair: tuple[str, str, str]) -> None:
    """An edit fills an empty secret from the stored one, so this is how a
    client certificate is taken away."""
    _, key, _ = pair
    block = TlsOptions(
        tls_mode="required",
        tls_client_key=SecretStr(key),
        tls_client_key_passphrase=SecretStr("secret"),
    )

    assert block.tls_client_key.get_secret_value() == ""
    assert block.tls().client_key is None


def test_an_encrypted_key_is_opened_once(pair: tuple[str, str, str]) -> None:
    certificate, _, locked = pair
    block = TlsOptions(
        tls_mode="required",
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(locked),
        tls_client_key_passphrase=SecretStr("secret"),
    )

    opened = block.tls().client_key
    assert opened is not None and "ENCRYPTED" not in opened
    assert ssl_context(block.tls()) is not None


def test_a_passphrase_left_from_before_is_ignored_by_a_plain_key(
    pair: tuple[str, str, str],
) -> None:
    certificate, key, _ = pair
    block = TlsOptions(
        tls_mode="required",
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(key),
        tls_client_key_passphrase=SecretStr("stale"),
    )

    assert block.tls().client_key is not None


def test_a_wrong_passphrase_is_refused(pair: tuple[str, str, str]) -> None:
    certificate, _, locked = pair
    with pytest.raises(ValueError, match="passphrase"):
        TlsOptions(
            tls_mode="required",
            tls_client_certificate=certificate,
            tls_client_key=SecretStr(locked),
            tls_client_key_passphrase=SecretStr("wrong"),
        )


def test_amazon_rds_is_a_bundle_shipped_here() -> None:
    settings = TlsOptionsWithFallback(tls_mode="verify_full", tls_trust="amazon_rds").tls()

    context = ssl_context(settings)

    assert AMAZON_RDS_BUNDLE.stat().st_size < 200_000
    assert context is not None and len(context.get_ca_certs()) > 50


@pytest.mark.parametrize(
    ("mode", "verify", "hostname"),
    [
        ("required", ssl.CERT_NONE, False),
        ("verify_ca", ssl.CERT_REQUIRED, False),
        ("verify_full", ssl.CERT_REQUIRED, True),
    ],
)
def test_a_context_checks_what_its_mode_says(
    mode: str, verify: ssl.VerifyMode, hostname: bool
) -> None:
    context = ssl_context(TlsOptions(tls_mode=mode).tls())  # type: ignore[arg-type]  # one of the modes

    assert context is not None
    assert context.verify_mode == verify
    assert context.check_hostname is hostname


def test_off_is_no_context() -> None:
    assert ssl_context(TlsOptions().tls()) is None


def test_the_name_checked_is_the_form_s_whatever_is_dialled() -> None:
    """A tunnel's end is loopback; the certificate names the server (D448)."""
    context = ssl_context(TlsOptions(tls_mode="verify_full").tls(), server_name="db.example.com")
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()

    wrapped = context.wrap_bio(incoming, outgoing, server_hostname="127.0.0.1")  # type: ignore[union-attr]  # a context, verify_full

    assert wrapped.server_hostname == "db.example.com"


def test_a_driver_that_cannot_name_the_server_refuses_verify_full_through_a_tunnel() -> None:
    settings = TlsOptions(tls_mode="verify_full").tls()

    with pytest.raises(AdapterError, match="Verify CA"):
        name_not_verifiable(settings, str(uuid.uuid4()))
    name_not_verifiable(settings, "")
    name_not_verifiable(TlsOptions(tls_mode="verify_ca").tls(), str(uuid.uuid4()))


def test_files_are_private_and_go_when_closed(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    settings = TlsOptions(
        tls_mode="verify_ca",
        tls_trust="certificate",
        tls_ca_certificate=certificate,
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(key),
    ).tls()

    with TlsFiles(settings) as files:
        written = [files.ca, files.certificate, files.key, files.pair]
        assert all(path is not None and path.exists() for path in written)
        if os.name == "posix":
            assert all(path.stat().st_mode & 0o077 == 0 for path in written if path)
            assert written[0] is not None and written[0].parent.stat().st_mode & 0o077 == 0
    assert not any(path is not None and path.exists() for path in written)


def test_nothing_is_written_for_a_block_without_pems() -> None:
    files = TlsFiles(TlsOptions(tls_mode="verify_full").tls())

    assert files.ca is None and files.key is None
    files.close()


def test_the_block_s_repr_says_no_more_than_its_mode(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    settings = TlsOptions(
        tls_mode="required", tls_client_certificate=certificate, tls_client_key=SecretStr(key)
    ).tls()

    assert repr(settings) == "TlsSettings(required)"


def test_a_program_writes_its_pems_from_the_environment(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    settings = TlsOptions(
        tls_mode="verify_full",
        tls_trust="certificate",
        tls_ca_certificate=certificate,
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(key),
    ).tls()

    argv, environment = with_program_files(("psql", "host=x"), settings)

    assert argv[:2] == ("sh", "-c") and argv[-2:] == ("psql", "host=x")
    assert "umask 077" in argv[2] and "unset DP_TLS_CA DP_TLS_CERT DP_TLS_KEY" in argv[2]
    assert environment["DP_TLS_KEY"] == key
    assert not any(key in part for part in argv)
    assert program_paths(settings).key == f"{PROGRAM_FOLDER}/key.pem"


def test_a_program_without_pems_runs_as_it_was() -> None:
    assert with_program_files(("psql",), TlsOptions(tls_mode="verify_full").tls()) == (("psql",), {})


def test_the_client_key_is_a_secret_of_every_source() -> None:
    for kind in ("postgres", "mysql", "clickhouse", "redis", "mongodb", "cassandra", "zookeeper", "kafka", "rabbitmq"):
        names = options_schema.secret_field_names(registry.get(kind).options_schema)
        assert {"tls_client_key", "tls_client_key_passphrase"} <= names, kind


def test_the_client_key_is_encrypted_at_rest(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    config, secrets = service.split_options(
        registry.get("postgres"),
        {
            "auth_method": "user_password",
            "host": "h",
            "database": "d",
            "user": "u",
            "password": "pw",
            "tls_mode": "verify_full",
            "tls_client_certificate": certificate,
            "tls_client_key": key,
        },
    )

    assert "tls_client_key" not in config
    assert "PRIVATE KEY" not in json.dumps(config)
    assert b"PRIVATE KEY" not in secrets
    assert json.loads(crypto.decrypt(secrets, purpose="connector"))["tls_client_key"] == key


def test_libpq_is_told_the_mode_and_the_name_through_a_tunnel() -> None:
    tunnel = str(uuid.uuid4())
    session = PostgresSession(_postgres(tls_mode="verify_full", ssh_tunnel=tunnel))

    conninfo = session.conninfo(("127.0.0.1", 40001))

    assert "sslmode=verify-full" in conninfo
    assert "sslrootcert=system" in conninfo
    assert "host=db.example.com" in conninfo and "hostaddr=127.0.0.1" in conninfo


def test_a_pool_s_key_names_the_pems_not_where_they_are(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    options = _postgres(
        tls_mode="verify_ca",
        tls_trust="certificate",
        tls_ca_certificate=certificate,
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(key),
    )
    session = PostgresSession(options)

    key_source = session.conninfo(("db.example.com", 5432))
    with TlsFiles(options.tls()) as files:
        dialled = session.conninfo(("db.example.com", 5432), files)

    assert key_source == PostgresSession(options).conninfo(("db.example.com", 5432))
    assert "dp-tls" not in key_source and "dp-tls" in dialled
    assert "sslcert=" in dialled and "sslkey=" in dialled


async def test_mongodb_is_told_how_much_to_check() -> None:
    client = make_client(
        "db", 27017, MongodbNoPassword(host="db", tls_mode="verify_ca"), pool_size=1
    )
    try:
        context = client.options.pool_options._ssl_context  # noqa: SLF001 - what pymongo built
        assert context is not None and not context.check_hostname
    finally:
        await client.close()
    assert ("tlsAllowInvalidHostnames", "true") in program_tls(
        MongodbNoPassword(host="db", tls_mode="verify_ca").tls()
    )


def test_kafka_takes_every_pem_inline(pair: tuple[str, str, str]) -> None:
    certificate, key, _ = pair
    options = KafkaNoAuth(
        tls_mode="verify_ca",
        tls_trust="certificate",
        tls_ca_certificate=certificate,
        tls_client_certificate=certificate,
        tls_client_key=SecretStr(key),
    )

    config = KafkaSession(options).config()

    assert config["security.protocol"] == "SSL"
    assert config["ssl.endpoint.identification.algorithm"] == "none"
    assert config["ssl.ca.pem"] == certificate and config["ssl.key.pem"] == key


def test_redis_cli_is_given_the_user_and_tls() -> None:
    options = RedisPassword(host="cache", user="reader", password=SecretStr("p"), tls_mode="required")

    program = redis_console(options)

    assert "--tls" in program.argv and "--insecure" in program.argv
    assert program.argv[program.argv.index("--user") + 1] == "reader"


def test_cqlsh_reads_the_block_from_its_settings() -> None:
    text = cqlshrc(TlsOptions(tls_mode="verify_ca").tls())

    assert "validate = true" in text and "check_hostname = false" in text


def test_zkcli_refuses_what_it_cannot_do() -> None:
    with pytest.raises(AdapterError):
        tls_flags(TlsOptions(tls_mode="required").tls())
    assert "hostnameVerification=true" in tls_flags(TlsOptions(tls_mode="verify_full").tls())
