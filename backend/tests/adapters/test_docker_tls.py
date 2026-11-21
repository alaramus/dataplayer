"""A daemon on TCP with mutual TLS, and one without TLS refused (D418).

The live tests need `docker compose up -d docker-tls`, and the tunnel's also
`docker compose up -d docker-remote`. Certificates other than the stand's are
made here, so a wrong CA and a client the daemon does not know are real ones.
"""

import asyncio
import datetime
import ssl
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pydantic import TypeAdapter, ValidationError

from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.connect import address
from app.adapters.docker.options import (
    DockerOptions,
    DockerSshOptions,
    DockerTlsOptions,
)
from app.adapters.docker.session import DockerSession
from app.adapters.options import secret_field_names
from app.adapters.protocol import AdapterError
from app.adapters.terminal import OpensTerminal, TerminalSize
from tests.adapters.docker_stand import THROUGH, Through, open_through
from tests.utils import services

ALPINE = "alpine:3.20"


def _pem(certificate: x509.Certificate) -> str:
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def _key_pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _issued(
    name: str, key: ec.EllipticCurvePrivateKey, issuer: tuple[x509.Name, ec.EllipticCurvePrivateKey] | None = None
) -> x509.Certificate:
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    signer_name, signer_key = issuer or (subject, key)
    now = datetime.datetime.now(datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(signer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=issuer is None, path_length=None), critical=True)
    )
    return builder.sign(signer_key, hashes.SHA256())


def _stranger() -> tuple[str, str, str]:
    """A CA nobody trusts, and a client certificate and key it signed."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = _issued("stranger CA", ca_key)
    client_key = ec.generate_private_key(ec.SECP256R1())
    client = _issued("stranger", client_key, (ca.subject, ca_key))
    return _pem(ca), _pem(client), _key_pem(client_key)


def _stand_files() -> tuple[str, str, str]:
    services.DOCKER_TLS.require()
    folder: Path = services.docker_tls_certificates()
    return tuple(  # type: ignore[return-value] # three files, read in order
        (folder / name).read_text() for name in ("ca.pem", "cert.pem", "key.pem")
    )


def _options(
    host: str = "localhost",
    tunnel: str = "",
    *,
    ca: str | None = None,
    certificate: str | None = None,
    key: str | None = None,
) -> DockerTlsOptions:
    stand_ca, stand_certificate, stand_key = _stand_files()
    port = 2376 if tunnel else int(services.DOCKER_TLS.url().rsplit(":", 1)[1])
    return DockerTlsOptions.model_validate(
        {
            "transport": "tls",
            "host": host,
            "port": port,
            "ssh_tunnel": tunnel,
            "ca_certificate": ca or stand_ca,
            "client_certificate": certificate or stand_certificate,
            "client_key": key or stand_key,
        }
    )


# --- the stand -----------------------------------------------------------------


async def test_a_daemon_with_tls_is_read_directly() -> None:
    adapter = DockerAdapter(_options(), None)
    checked = await adapter.check_connection()
    assert checked.ok, checked.message
    names = [node.id for node in await adapter.list_children(None)]
    assert "containers" in names


async def test_the_certificate_is_checked_against_the_daemon_s_name_through_a_tunnel() -> None:
    through: Through = await open_through()
    adapter = DockerAdapter(_options("docker-tls", THROUGH), through)
    checked = await adapter.check_connection()
    assert checked.ok, checked.message


async def test_a_ca_that_did_not_sign_the_daemon_is_said_so() -> None:
    ca, _, _ = _stranger()
    checked = await DockerAdapter(_options(ca=ca), None).check_connection()
    assert not checked.ok
    assert checked.message == "The Docker server's certificate is not signed by the CA certificate"


async def test_a_client_the_daemon_does_not_know_is_said_so() -> None:
    _, certificate, key = _stranger()
    checked = await DockerAdapter(
        _options(certificate=certificate, key=key), None
    ).check_connection()
    assert not checked.ok
    assert checked.error_kind == "auth"
    assert checked.message == "The Docker server did not accept the client certificate"


async def test_a_key_that_is_not_the_certificate_s_is_said_before_dialling() -> None:
    _, _, key = _stranger()
    checked = await DockerAdapter(_options(key=key), None).check_connection()
    assert not checked.ok
    assert checked.message == "The client certificate and key could not be read, or are not a pair"


async def test_a_terminal_opens_over_tls() -> None:
    session = DockerSession(_options(), None)
    engine = await session.engine()
    repository, _, tag = ALPINE.partition(":")
    await engine.request(
        "POST", "/images/create", params={"fromImage": repository, "tag": tag},
        expected=(200,), seconds=300,
    )
    name = f"dp-tls-{uuid.uuid4().hex[:8]}"
    made = await engine.request(
        "POST", "/containers/create", params={"name": name},
        json={"Image": ALPINE, "Cmd": ["sleep", "600"]}, expected=(201,),
    )
    container = str(made.json()["Id"])
    try:
        await engine.request("POST", f"/containers/{container}/start", expected=(204,))
        adapter = DockerAdapter(_options(), None)
        action = adapter.action("docker_terminal")
        assert isinstance(action, OpensTerminal)
        terminal = await action.open_terminal(
            f"container:{container}", {"shell": "/bin/sh"}, TerminalSize(cols=80, rows=24)
        )
        try:
            await terminal.write(b"echo dp-$((6*7)); exit\n")
            seen = b""
            async with asyncio.timeout(10):
                while chunk := await terminal.read():
                    seen += chunk
            assert b"dp-42" in seen
        finally:
            await terminal.close()
    finally:
        await engine.request(
            "DELETE", f"/containers/{container}", params={"force": "true"}, expected=(204, 404)
        )


# --- without a daemon ------------------------------------------------------------


@pytest.fixture
async def plain_daemon() -> AsyncIterator[int]:
    """Something answering HTTP without TLS, as dockerd on port 2375 does."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.read(4096)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port


def _offline(port: int) -> DockerTlsOptions:
    ca, certificate, key = _stranger()
    return DockerTlsOptions(
        host="127.0.0.1",
        port=port,
        ca_certificate=ca,
        client_certificate=certificate,
        client_key=key,  # type: ignore[arg-type] # pydantic makes the SecretStr
    )


async def test_a_daemon_without_tls_is_refused_and_says_why(plain_daemon: int) -> None:
    checked = await DockerAdapter(_offline(plain_daemon), None).check_connection()
    assert not checked.ok
    assert checked.message == (
        "This Docker server listens without TLS, which is refused: whoever reaches its port owns the machine"
    )


async def test_a_name_the_certificate_lacks_is_named() -> None:
    session = DockerSession(_offline(1), None)
    mismatch = ssl.SSLCertVerificationError("certificate verify failed")
    mismatch.verify_message = "Hostname mismatch, certificate is not valid for '127.0.0.1'."
    failure = await session._not_reached(mismatch)  # the one place the handshake is read
    assert isinstance(failure, AdapterError)
    assert failure.message == (
        "The Docker server's certificate is not for 127.0.0.1; use the name it was issued for"
    )


def test_options_stored_before_the_choice_are_the_socket_s() -> None:
    stored = TypeAdapter(DockerOptions).validate_python(
        {"ssh_connection": THROUGH, "socket": "/var/run/docker.sock"}
    )
    assert isinstance(stored, DockerSshOptions)


def test_the_client_key_is_a_secret() -> None:
    assert secret_field_names(DockerOptions) == {"client_key"}


@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("ca_certificate", "not a certificate", "BEGIN CERTIFICATE"),
        ("client_key", "-----BEGIN ENCRYPTED PRIVATE KEY-----\nx\n", "encrypted"),
        ("client_key", "nothing", "BEGIN PRIVATE KEY"),
        ("host", "tcp://daemon:2375", "a name or an address"),
    ],
)
def test_what_is_not_pem_or_a_host_is_refused(field: str, value: str, problem: str) -> None:
    ca, certificate, key = _stranger()
    raw = {
        "transport": "tls",
        "host": "daemon",
        "ca_certificate": ca,
        "client_certificate": certificate,
        "client_key": key,
        field: value,
    }
    with pytest.raises(ValidationError, match=problem):
        TypeAdapter(DockerOptions).validate_python(raw)


@pytest.mark.parametrize(
    ("bindings", "where"),
    [
        ([{"HostIp": "0.0.0.0", "HostPort": "15432"}], ("daemon.example", 15432)),
        # On the daemon's loopback: out of reach from here.
        ([{"HostIp": "127.0.0.1", "HostPort": "15432"}], None),
        ([{"HostIp": "10.1.2.3", "HostPort": "5433"}], ("10.1.2.3", 5433)),
        # Only a network's own address: out of reach without a tunnel.
        (None, None),
    ],
)
def test_without_a_tunnel_a_container_is_seen_from_outside_its_machine(
    bindings: list[dict[str, str]] | None, where: tuple[str, int] | None
) -> None:
    inspected = {
        "NetworkSettings": {
            "Ports": {"5432/tcp": bindings},
            "Networks": {"app": {"IPAddress": "172.18.0.5"}},
        }
    }
    assert address(inspected, 5432, "daemon.example") == where


async def test_pem_pasted_into_a_one_line_field_is_read_with_its_lines() -> None:
    """A secret field drops the line breaks of what is pasted into it."""
    ca, certificate, key = _stand_files()
    flat = DockerAdapter(
        _options(
            ca=ca.replace("\n", ""),
            certificate=certificate.replace("\n", " "),
            key=key.replace("\n", ""),
        ),
        None,
    )
    checked = await flat.check_connection()
    assert checked.ok, checked.message
