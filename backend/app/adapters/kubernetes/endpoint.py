"""What a way in resolves to: an API server, what to trust, how to sign (D464).

A kubeconfig is read as data. Of its chosen context only the cluster's
`server`, `certificate-authority-data` and `tls-server-name`, and the user's
`client-certificate-data`, `client-key-data` and `token` are taken; anything
that would run a program, open a file on this server or skip verification is
refused with a sentence that says what to do instead.
"""

import base64
import binascii
from dataclasses import dataclass
from typing import Any

import yaml

from app.adapters.kubernetes.options import (
    CertificateOptions,
    KubeconfigOptions,
    KubernetesConnection,
    TokenOptions,
    checked_server,
)
from app.adapters.protocol import AdapterError
from app.adapters.tls import CERTIFICATE, pem
from app.core.translation import say

_KEYS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY")
# A kubeconfig's `exec` command, and the cloud it belongs to.
_CLOUD_PLUGINS = {
    "gke-gcloud-auth-plugin": "gke",
    "aws": "aws",
    "aws-iam-authenticator": "aws",
    "kubelogin": "azure",
}
# Fields that name a file on the machine kubectl runs on.
_PATHS = ("certificate-authority", "client-certificate", "client-key", "tokenFile")


@dataclass(frozen=True)
class Endpoint:
    """An API server and how to be trusted by it. Never logged whole."""

    server: str
    # PEM, or None for the system's roots.
    ca: str | None
    # The name its certificate carries when it is not the server's host.
    server_name: str | None
    token: str | None
    client_certificate: str | None
    client_key: str | None
    # What the form shows of a kubeconfig: its context and cluster.
    context: str | None = None

    def __repr__(self) -> str:
        return f"Endpoint(server={self.server!r})"


def endpoint_of(options: KubernetesConnection) -> Endpoint:
    if isinstance(options, KubeconfigOptions):
        return from_kubeconfig(options.kubeconfig.get_secret_value(), options.context)
    if isinstance(options, TokenOptions):
        return Endpoint(
            server=options.server,
            ca=options.ca_certificate or None,
            server_name=None,
            token=options.token.get_secret_value(),
            client_certificate=None,
            client_key=None,
        )
    assert isinstance(options, CertificateOptions)
    return Endpoint(
        server=options.server,
        ca=options.ca_certificate or None,
        server_name=None,
        token=None,
        client_certificate=options.client_certificate,
        client_key=options.client_key.get_secret_value(),
    )


def _refused(text: str) -> AdapterError:
    return AdapterError("config", text)


def _named(entries: Any, name: str, what: str) -> dict[str, Any]:
    """The entry of a kubeconfig list (`clusters`, `users`, `contexts`) by name."""
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name") == name:
                body = entry.get(what)
                if isinstance(body, dict):
                    return body
    raise _refused(say("The kubeconfig names {name}, and does not have it", name=name))


def _data(body: dict[str, Any], key: str, kinds: tuple[str, ...]) -> str | None:
    """A `*-data` field: base64 of a PEM file."""
    value = body.get(key)
    if value is None:
        return None
    try:
        text = base64.b64decode(str(value), validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _refused(say("The kubeconfig's {field} is not base64 of a PEM file", field=key)) from None
    try:
        return pem(text, kinds, say("The kubeconfig's {field} is not base64 of a PEM file", field=key))
    except ValueError as problem:
        raise _refused(str(problem)) from None


def _program_refusal(user: dict[str, Any]) -> AdapterError | None:
    if "auth-provider" in user:
        return _refused(
            say("This kubeconfig signs in through a plugin, which this server does not run")
        )
    run = user.get("exec")
    if run is None:
        return None
    command = str(run.get("command") if isinstance(run, dict) else "").replace("\\", "/")
    cloud = _CLOUD_PLUGINS.get(command.rsplit("/", 1)[-1].removesuffix(".exe"))
    if cloud == "gke":
        return _refused(
            say(
                "This kubeconfig signs in through gcloud, which this server does not run; "
                "sign in to the cluster with a Google Cloud account instead"
            )
        )
    if cloud is not None:
        return _refused(
            say(
                "This kubeconfig signs in through its cloud's command, which this server "
                "does not run; use a token or a certificate instead"
            )
        )
    return _refused(
        say("This kubeconfig signs in by running a program, which this server does not do")
    )


def from_kubeconfig(text: str, wanted: str) -> Endpoint:
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError:
        raise _refused(say("The kubeconfig is not YAML")) from None
    if not isinstance(config, dict):
        raise _refused(say("The kubeconfig is not YAML"))
    name = wanted.strip() or str(config.get("current-context") or "")
    if not name:
        raise _refused(say("The kubeconfig has no current context; name the one to use"))
    context = _named(config.get("contexts"), name, "context")
    cluster = _named(config.get("clusters"), str(context.get("cluster") or ""), "cluster")
    user = _named(config.get("users"), str(context.get("user") or ""), "user")

    refusal = _program_refusal(user)
    if refusal is not None:
        raise refusal
    for body in (cluster, user):
        for key in _PATHS:
            if key in body:
                raise _refused(
                    say(
                        "The kubeconfig names a file instead of holding its data; "
                        "kubectl config view --minify --flatten writes one that holds it"
                    )
                )
    if cluster.get("insecure-skip-tls-verify"):
        raise _refused(
            say(
                "The kubeconfig skips checking the server's certificate, which is not done "
                "here; put the cluster's CA in it"
            )
        )
    if "username" in user or "password" in user:
        raise _refused(say("Kubernetes no longer signs in with a user name and password"))

    try:
        server = checked_server(str(cluster.get("server") or ""))
    except ValueError as problem:
        raise _refused(str(problem)) from None
    ca = _data(cluster, "certificate-authority-data", CERTIFICATE)
    certificate = _data(user, "client-certificate-data", CERTIFICATE)
    client_key = _data(user, "client-key-data", _KEYS)
    token = user.get("token")
    if token is not None and (not isinstance(token, str) or not token.strip()):
        raise _refused(say("The kubeconfig's token is empty"))
    if (certificate is None) != (client_key is None):
        raise _refused(say("The kubeconfig has a client certificate without its key, or a key without one"))
    if token is None and certificate is None:
        raise _refused(say("The kubeconfig's user has neither a token nor a client certificate"))
    server_name = cluster.get("tls-server-name")
    return Endpoint(
        server=server,
        ca=ca,
        server_name=str(server_name) if server_name else None,
        token=token.strip() if isinstance(token, str) else None,
        client_certificate=certificate,
        client_key=client_key,
        context=name,
    )
