"""How a daemon is reached: its socket through an SSH connection (D405), or
TCP with mutual TLS (D418).

The form chooses the transport first; the rest of the type does not know which
it has. The daemon this server runs on is never a source, and a daemon on TCP
without TLS is refused: there is no option for either.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

from app.adapters.layout import layout
from app.adapters.options import TUNNEL_REFERENCE
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_, say

DEFAULT_SOCKET = "/var/run/docker.sock"
PODMAN_SOCKET = "/run/podman/podman.sock"
TLS_PORT = 2376

_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_SOCKET = re.compile(r"^/[^\x00]*$")
# Every PEM block in a text, its kind and its base64 however it was wrapped.
_BLOCK = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.DOTALL)
_CERTIFICATE = "CERTIFICATE"
_KEYS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY")
_MAX_PEM = 64 * 1024


def socket_problem(path: str) -> str | None:
    """Why a socket path is not one to forward, or nothing."""
    if not _SOCKET.match(path) or len(path.encode()) > 255:
        return say("A socket is an absolute path of at most 255 bytes")
    if any(part in {".", ".."} for part in path.split("/")):
        return say("A socket path has no . or .. parts")
    return None


def _transport_field(transport: str) -> Any:
    return Field(default=transport, title=N_("Transport"), json_schema_extra=layout())


class DockerSshOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", title=N_("Socket through SSH"))

    transport: Literal["ssh"] = _transport_field("ssh")
    # Required: there is no "directly" — this server's own daemon is never a
    # source (D405).
    ssh_connection: str = Field(
        pattern=_UUID,
        title=N_("SSH connection"),
        description=N_(
            "One of your SSH connections, signed in to the machine the daemon runs on"
        ),
        json_schema_extra=layout(purpose=TUNNEL_REFERENCE),
    )
    socket: str = Field(
        default=DEFAULT_SOCKET,
        title=N_("Socket"),
        description=N_(
            "The daemon's socket on that machine; rootless Docker and Podman keep it elsewhere"
        ),
        json_schema_extra=layout(),
    )

    @field_validator("socket")
    @classmethod
    def _socket_is_a_path(cls, path: str) -> str:
        problem = socket_problem(path)
        if problem is not None:
            raise ValueError(problem)
        return path

    @property
    def tunnel(self) -> str:
        """The SSH connection a container's server is reached through (D417)."""
        return self.ssh_connection


def _pem(text: str, kinds: tuple[str, ...], problem: str) -> str:
    """The blocks of the kinds asked for, each wrapped at 64 as OpenSSL reads it.

    Rewrapped because a one-line field — the form's secret field is one — drops
    the line breaks of what is pasted into it, and OpenSSL cannot read a body
    on one line.
    """
    if len(text) > _MAX_PEM:
        raise ValueError(problem)
    blocks = []
    for kind, body in _BLOCK.findall(text):
        if kind not in kinds:
            continue
        joined = "".join(body.split())
        lines = [joined[i : i + 64] for i in range(0, len(joined), 64)]
        blocks.append("\n".join([f"-----BEGIN {kind}-----", *lines, f"-----END {kind}-----"]))
    if not blocks:
        raise ValueError(problem)
    return "\n".join(blocks) + "\n"


class DockerTlsOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", title=N_("TCP with TLS"))

    transport: Literal["tls"] = _transport_field("tls")
    host: str = Field(
        title=N_("Host"),
        min_length=1,
        max_length=255,
        description=N_("As the daemon's certificate names it"),
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=TLS_PORT, ge=1, le=65535, title=N_("Port"), json_schema_extra=layout(row="address")
    )
    ssh_tunnel: str = ssh_tunnel_field()
    # Not secret: a CA certificate is what everybody is meant to have.
    ca_certificate: str = Field(
        title=N_("CA certificate"),
        description=N_("PEM: ca.pem, the authority that signed the daemon's certificate"),
        json_schema_extra=layout(multiline=True),
    )
    client_certificate: str = Field(
        title=N_("Client certificate"),
        description=N_("PEM: cert.pem, which the daemon accepts"),
        json_schema_extra=layout(multiline=True),
    )
    client_key: SecretStr = Field(
        title=N_("Client key"),
        description=N_("PEM: key.pem, not encrypted"),
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("host")
    @classmethod
    def _plain_host(cls, text: str) -> str:
        host = text.strip()
        bracketed = host.startswith("[") and host.endswith("]")
        if host == "" or (not bracketed and any(mark in host for mark in "/@ :?#")):
            raise ValueError(say("A host is a name or an address, nothing more"))
        return host

    @field_validator("ca_certificate", "client_certificate")
    @classmethod
    def _certificate(cls, text: str) -> str:
        return _pem(text, (_CERTIFICATE,), say("Paste a certificate in PEM, BEGIN CERTIFICATE and all"))

    @field_validator("client_key")
    @classmethod
    def _key(cls, key: SecretStr) -> SecretStr:
        text = key.get_secret_value()
        if "ENCRYPTED" in text:
            raise ValueError(say("The key is encrypted; paste one without a passphrase"))
        return SecretStr(_pem(text, _KEYS, say("Paste a private key in PEM, BEGIN PRIVATE KEY and all")))

    @property
    def tunnel(self) -> str:
        """The SSH connection a container's server is reached through, if any (D417)."""
        return self.ssh_tunnel


type DockerConnection = DockerSshOptions | DockerTlsOptions


def _ssh_by_default(value: Any) -> Any:
    """Options stored before the transport was a choice are the socket's."""
    if isinstance(value, dict) and "transport" not in value:
        return {"transport": "ssh", **value}
    return value


DockerOptions = Annotated[
    DockerSshOptions | DockerTlsOptions,
    Field(discriminator="transport"),
    BeforeValidator(_ssh_by_default),
]
