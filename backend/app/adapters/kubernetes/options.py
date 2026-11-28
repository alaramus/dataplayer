"""How a cluster is reached and signed in to (D464).

The form chooses the way in first; the rest of the type knows only the
endpoint it resolves to (`endpoint.py`). A kubeconfig is parsed on the server
and only its data is read: nothing in it is run and no file it names is
opened.
"""

import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.layout import PEM_FILE, layout
from app.adapters.tls import CERTIFICATE, pem
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_, say

KUBECONFIG_FILE = ".yaml,.yml,.conf,.config,.kubeconfig"
# A namespace is a DNS label (RFC 1123).
NAMESPACE = r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
_NAMESPACE = re.compile(NAMESPACE)
# A cluster's key is pasted without a passphrase, as kubectl takes it.
_KEYS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY")
_MAX_KUBECONFIG = 256 * 1024
_MAX_TOKEN = 16 * 1024


def _auth_field(auth: str) -> Any:
    return Field(default=auth, title=N_("Sign in with"), json_schema_extra=layout())


def _namespace_field() -> Any:
    return Field(
        default="",
        title=N_("Namespace"),
        max_length=63,
        description=N_(
            "Empty to see every namespace you may list; one name when you may work only in it"
        ),
        json_schema_extra=layout(),
    )


def _server_field() -> Any:
    return Field(
        title=N_("API server"),
        min_length=1,
        max_length=2048,
        description=N_("Its HTTPS address, as a kubeconfig names it: https://host:6443"),
        json_schema_extra=layout(),
    )


def _ca_field() -> Any:
    # Not secret: a CA certificate is what everybody is meant to have.
    return Field(
        default="",
        title=N_("CA certificate"),
        description=N_(
            "PEM: the authority that signed the API server's certificate; empty for a public one"
        ),
        json_schema_extra=layout(multiline=True, file=PEM_FILE),
    )


def checked_namespace(text: str) -> str:
    name = text.strip()
    if name and not _NAMESPACE.match(name):
        raise ValueError(say("A namespace is lowercase letters, digits and hyphens"))
    return name


def checked_server(text: str) -> str:
    """An https origin and nothing after it but an optional path prefix."""
    address = text.strip().rstrip("/")
    parts = urlsplit(address)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(say("The API server is an https:// address"))
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(say("The API server is an https:// address"))
    try:
        parts.port  # noqa: B018 - raises on a port that is not a number
    except ValueError:
        raise ValueError(say("The API server is an https:// address")) from None
    return address


def checked_ca(text: str) -> str:
    if not text.strip():
        return ""
    return pem(text, CERTIFICATE, say("Paste a certificate in PEM, BEGIN CERTIFICATE and all"))


class _Common(BaseModel):
    """What every way in checks. The fields themselves are declared last in
    each variant: a base class's fields would come first in the form, before
    the choice of how to sign in."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("namespace", check_fields=False)
    @classmethod
    def _namespace(cls, text: str) -> str:
        return checked_namespace(text)


class KubeconfigOptions(_Common):
    model_config = ConfigDict(extra="forbid", title=N_("A kubeconfig"))

    auth: Literal["kubeconfig"] = _auth_field("kubeconfig")
    kubeconfig: SecretStr = Field(
        title=N_("Kubeconfig"),
        description=N_(
            "The file's text, with its certificates and keys in it: "
            "kubectl config view --minify --flatten writes one"
        ),
        json_schema_extra=layout(multiline=True, file=KUBECONFIG_FILE),
    )
    context: str = Field(
        default="",
        title=N_("Context"),
        max_length=253,
        description=N_("Empty for the file's current context"),
        json_schema_extra=layout(),
    )
    namespace: str = _namespace_field()
    ssh_tunnel: str = ssh_tunnel_field()

    @field_validator("kubeconfig")
    @classmethod
    def _bounded(cls, value: SecretStr) -> SecretStr:
        text = value.get_secret_value()
        if not text.strip() or len(text) > _MAX_KUBECONFIG:
            raise ValueError(say("Paste a kubeconfig of at most 256 KB"))
        return value


class TokenOptions(_Common):
    model_config = ConfigDict(extra="forbid", title=N_("A token"))

    auth: Literal["token"] = _auth_field("token")
    server: str = _server_field()
    ca_certificate: str = _ca_field()
    token: SecretStr = Field(
        title=N_("Token"),
        description=N_("A bearer token the cluster accepts, a service account's for instance"),
        json_schema_extra=layout(),
    )
    namespace: str = _namespace_field()
    ssh_tunnel: str = ssh_tunnel_field()

    @field_validator("server")
    @classmethod
    def _server(cls, text: str) -> str:
        return checked_server(text)

    @field_validator("ca_certificate")
    @classmethod
    def _ca(cls, text: str) -> str:
        return checked_ca(text)

    @field_validator("token")
    @classmethod
    def _token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value().strip()
        if not token or len(token) > _MAX_TOKEN or any(c.isspace() for c in token):
            raise ValueError(say("A token is one word of at most 16 KB"))
        return SecretStr(token)


class CertificateOptions(_Common):
    model_config = ConfigDict(extra="forbid", title=N_("A client certificate"))

    auth: Literal["certificate"] = _auth_field("certificate")
    server: str = _server_field()
    ca_certificate: str = _ca_field()
    client_certificate: str = Field(
        title=N_("Client certificate"),
        description=N_("PEM: a certificate the cluster accepts"),
        json_schema_extra=layout(multiline=True, file=PEM_FILE),
    )
    client_key: SecretStr = Field(
        title=N_("Client key"),
        description=N_("PEM: its key, not encrypted"),
        json_schema_extra=layout(multiline=True, file=PEM_FILE),
    )
    namespace: str = _namespace_field()
    ssh_tunnel: str = ssh_tunnel_field()

    @field_validator("server")
    @classmethod
    def _server(cls, text: str) -> str:
        return checked_server(text)

    @field_validator("ca_certificate")
    @classmethod
    def _ca(cls, text: str) -> str:
        return checked_ca(text)

    @field_validator("client_certificate")
    @classmethod
    def _certificate(cls, text: str) -> str:
        return pem(text, CERTIFICATE, say("Paste a certificate in PEM, BEGIN CERTIFICATE and all"))

    @field_validator("client_key")
    @classmethod
    def _key(cls, key: SecretStr) -> SecretStr:
        text = key.get_secret_value()
        if "ENCRYPTED" in text:
            raise ValueError(say("The key is encrypted; paste one without a passphrase"))
        return SecretStr(pem(text, _KEYS, say("Paste a private key in PEM, BEGIN PRIVATE KEY and all")))


type KubernetesConnection = KubeconfigOptions | TokenOptions | CertificateOptions

KubernetesOptions = Annotated[
    KubeconfigOptions | TokenOptions | CertificateOptions,
    Field(discriminator="auth"),
]
