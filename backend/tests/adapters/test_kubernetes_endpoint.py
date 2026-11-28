"""A kubeconfig is read as data, and every way it could run, read or skip
something is refused with a sentence of its own (D464)."""

import base64
from typing import Any

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from app.adapters.kubernetes.endpoint import endpoint_of, from_kubeconfig
from app.adapters.kubernetes.options import (
    CertificateOptions,
    KubeconfigOptions,
    TokenOptions,
)
from app.adapters.protocol import AdapterError

# A self-signed certificate made for these tests; nothing trusts it.
CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIBdjCCAR2gAwIBAgIBADAKBggqhkjOPQQDAjAjMSEwHwYDVQQDDBhrM3Mtc2Vy
dmVyLWNhQDE3NjQzMTIyNTQwHhcNMjUxMTI4MDYzNzM0WhcNMzUxMTI2MDYzNzM0
WjAjMSEwHwYDVQQDDBhrM3Mtc2VydmVyLWNhQDE3NjQzMTIyNTQwWTATBgcqhkjO
PQIBBggqhkjOPQMBBwNCAATh5BGqGRxlQS1dSN1hxv4ufTlQUW1lgo0NnGv79nQJ
I7d8Mcb1YW2t9tfqRnYmbF5DyY2Y5D7oPm1ZpAN3P0vCo0IwQDAOBgNVHQ8BAf8E
BAMCAqQwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4EFgQUdA8lWhZ+V7p0cY6r3G4Q
rKWzm1IwCgYIKoZIzj0EAwIDRwAwRAIgRZ4q0cN2v8u1D8h0K0A1lY7E9TjJm0x6
rKmQqQ5WqCQCIFVY8n4cQb1a6PZb6Y4rDO3cX5xWmY0Q3Yt7cJ2Zr2qS
-----END CERTIFICATE-----
"""
KEY = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgevZzL1gmWDO0q8QP
-----END PRIVATE KEY-----
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _config(user: dict[str, Any], cluster: dict[str, Any] | None = None, **top: Any) -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": "here",
            "contexts": [{"name": "here", "context": {"cluster": "one", "user": "me"}},
                         {"name": "other", "context": {"cluster": "one", "user": "token"}}],
            "clusters": [
                {
                    "name": "one",
                    "cluster": cluster
                    or {"server": "https://k8s.example:6443", "certificate-authority-data": _b64(CERTIFICATE)},
                }
            ],
            "users": [{"name": "me", "user": user}, {"name": "token", "user": {"token": "abc.def"}}],
            **top,
        }
    )


def test_a_kubeconfig_with_a_certificate_reads_its_data() -> None:
    endpoint = from_kubeconfig(
        _config({"client-certificate-data": _b64(CERTIFICATE), "client-key-data": _b64(KEY)}), ""
    )
    assert endpoint.server == "https://k8s.example:6443"
    assert endpoint.ca is not None and "BEGIN CERTIFICATE" in endpoint.ca
    assert endpoint.client_key is not None and "PRIVATE KEY" in endpoint.client_key
    assert endpoint.token is None
    assert endpoint.context == "here"
    # The endpoint never shows its secrets.
    assert "PRIVATE" not in repr(endpoint)


def test_the_context_named_wins_over_the_current_one() -> None:
    endpoint = from_kubeconfig(_config({"token": "x"}), "other")
    assert endpoint.token == "abc.def"
    assert endpoint.context == "other"


@pytest.mark.parametrize(
    ("user", "cluster", "words"),
    [
        ({"exec": {"command": "gke-gcloud-auth-plugin"}}, None, "Google Cloud account"),
        ({"exec": {"command": "/usr/local/bin/aws"}}, None, "its cloud's command"),
        ({"exec": {"command": "my-helper"}}, None, "running a program"),
        ({"auth-provider": {"name": "oidc"}}, None, "plugin"),
        ({"client-certificate": "/home/me/crt", "client-key": "/home/me/key"}, None, "--flatten"),
        ({"token": "x"}, {"server": "https://k8s.example", "certificate-authority": "/etc/ca"}, "--flatten"),
        ({"token": "x"}, {"server": "https://k8s.example", "insecure-skip-tls-verify": True}, "CA"),
        ({"username": "me", "password": "pw"}, None, "user name and password"),
        ({}, None, "neither a token nor a client certificate"),
        ({"client-certificate-data": _b64(CERTIFICATE)}, None, "without its key"),
        ({"token": "x"}, {"server": "http://k8s.example"}, "https://"),
        ({"client-key-data": "not base64!", "client-certificate-data": _b64(CERTIFICATE)}, None, "base64"),
    ],
)
def test_what_a_kubeconfig_cannot_be_is_refused(
    user: dict[str, Any], cluster: dict[str, Any] | None, words: str
) -> None:
    with pytest.raises(AdapterError) as refused:
        from_kubeconfig(_config(user, cluster), "")
    assert refused.value.error_kind == "config"
    assert words in refused.value.message


def test_a_missing_context_and_a_file_that_is_not_yaml_are_said() -> None:
    with pytest.raises(AdapterError, match="does not have it"):
        from_kubeconfig(_config({"token": "x"}), "nowhere")
    with pytest.raises(AdapterError, match="not YAML"):
        from_kubeconfig("[unclosed", "")
    with pytest.raises(AdapterError, match="no current context"):
        from_kubeconfig(_config({"token": "x"}, **{"current-context": ""}), "")


def test_a_token_and_a_certificate_way_in_resolve_without_a_file() -> None:
    token = endpoint_of(TokenOptions(server="https://k8s.example/", token=SecretStr(" abc ")))
    assert token.server == "https://k8s.example"
    assert token.token == "abc"
    assert token.ca is None
    pair = endpoint_of(
        CertificateOptions(
            server="https://10.0.0.1:6443",
            ca_certificate=CERTIFICATE,
            client_certificate=CERTIFICATE,
            client_key=SecretStr(KEY),
        )
    )
    assert pair.client_certificate is not None and pair.token is None


@pytest.mark.parametrize(
    "fields",
    [
        {"server": "http://k8s.example", "token": "x"},
        {"server": "https://user:pw@k8s.example", "token": "x"},
        {"server": "https://k8s.example?x=1", "token": "x"},
        {"server": "https://k8s.example", "token": "two words"},
        {"server": "https://k8s.example", "token": "x", "namespace": "Not_A_Label"},
        {"server": "https://k8s.example", "token": "x", "ca_certificate": "not a pem"},
    ],
)
def test_a_form_that_cannot_reach_a_cluster_safely_does_not_validate(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TokenOptions.model_validate(fields)


def test_a_kubeconfig_field_is_bounded() -> None:
    with pytest.raises(ValidationError):
        KubeconfigOptions(kubeconfig=SecretStr(" "))
    with pytest.raises(ValidationError):
        KubeconfigOptions(kubeconfig=SecretStr("x" * (256 * 1024 + 1)))
