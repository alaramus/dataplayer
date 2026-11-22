"""TLS as every server source states it (D446), and the files it may need (D447).

Driver-free: a source puts one of the blocks below on its base model and asks
this module for an `ssl.SSLContext`, for files, or for the PEMs themselves,
whichever its driver takes. The fields are flat (D16) and sit on the "tls"
page of the connection window, so the form keeps the address and the choice of
method together on the first.
"""

import hashlib
import os
import re
import shutil
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from cryptography.hazmat.primitives import serialization
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.adapters.layout import layout
from app.adapters.protocol import AdapterError
from app.core.translation import N_, say

TLS_GROUP = "tls"

TlsMode = Literal["disabled", "preferred", "required", "verify_ca", "verify_full"]
TlsTrust = Literal["system", "certificate", "amazon_rds"]

# Every Amazon RDS region's root authorities, from
# https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem on
# 2026-11-22, Beta and Preview regions and expired roots left out. They are in
# no system store, and `verify_full` against RDS or DocumentDB needs them.
AMAZON_RDS_BUNDLE = Path(__file__).parent / "authorities" / "amazon-rds.pem"

# Every PEM block in a text, its kind and its base64 however it was wrapped.
_BLOCK = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.DOTALL)
CERTIFICATE = ("CERTIFICATE",)
PRIVATE_KEYS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "ENCRYPTED PRIVATE KEY")
_MAX_PEM = 64 * 1024


def pem(text: str, kinds: tuple[str, ...], problem: str) -> str:
    """The blocks of the kinds asked for, each wrapped at 64 as OpenSSL reads it.

    Rewrapped because a one-line field — a secret field is one — drops the line
    breaks of what is pasted into it, and OpenSSL cannot read a body on one
    line. Legacy encrypted keys keep their `Proc-Type` headers.
    """
    if len(text) > _MAX_PEM:
        raise ValueError(problem)
    blocks = []
    for kind, body in _BLOCK.findall(text):
        if kind not in kinds:
            continue
        headers, _, data = body.rpartition("\n\n") if "Proc-Type:" in body else ("", "", body)
        joined = "".join(data.split())
        lines = [joined[i : i + 64] for i in range(0, len(joined), 64)]
        head = [line.strip() for line in headers.strip().splitlines()]
        blocks.append(
            "\n".join(
                [f"-----BEGIN {kind}-----", *head, *([""] if head else []), *lines, f"-----END {kind}-----"]
            )
        )
    if not blocks:
        raise ValueError(problem)
    return "\n".join(blocks) + "\n"


MODE_TITLES: dict[str, str] = {
    "disabled": N_("Off"),
    "preferred": N_("When the server offers it"),
    "required": N_("Required, not verified"),
    "verify_ca": N_("Verify CA"),
    "verify_full": N_("Verify full"),
}

TRUST_TITLES: dict[str, str] = {
    "system": N_("The system's authorities"),
    "certificate": N_("A CA certificate"),
    "amazon_rds": N_("Amazon RDS"),
}


def _choices(titles: dict[str, str], values: tuple[str, ...]) -> list[Any]:
    return [{"value": value, "label": titles[value]} for value in values]


def unlocked(key: str, passphrase: str) -> str:
    """The key as PKCS#8 without a passphrase, for a driver or a program that takes none.

    libpq, kazoo and every program in a container take a passphrase in a way of
    their own, or not at all; one opened key serves them all, and it is only
    ever written where D447 writes. A passphrase is ignored for a key that
    needs none: an edit keeps the stored one when its box is left empty.
    Raises ValueError when the key cannot be opened.
    """
    try:
        try:
            loaded = serialization.load_pem_private_key(key.encode(), password=None)
        except TypeError:
            loaded = serialization.load_pem_private_key(
                key.encode(), password=passphrase.encode() or None
            )
    except (ValueError, TypeError):
        raise ValueError(say("The passphrase does not open the client key")) from None
    return loaded.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _mode_field(default: str, modes: tuple[str, ...]) -> Any:
    return Field(
        default=default,
        title=N_("TLS"),
        description=N_(
            "Verify CA checks who signed the server's certificate; Verify full also checks the name in it"
        ),
        json_schema_extra={**layout(group=TLS_GROUP), "x-ui-choices": _choices(MODE_TITLES, modes)},
    )


def _trust_field(trusts: tuple[str, ...]) -> Any:
    return Field(
        default="system",
        title=N_("Trusted authorities"),
        json_schema_extra={**layout(group=TLS_GROUP), "x-ui-choices": _choices(TRUST_TITLES, trusts)},
    )


def _ca_field() -> Any:
    # Not secret: a CA certificate is what everybody is meant to have.
    return Field(
        default="",
        title=N_("CA certificate"),
        description=N_("PEM, when the trusted authority is a certificate of your own"),
        json_schema_extra=layout(group=TLS_GROUP, multiline=True),
    )


def _client_certificate_field() -> Any:
    return Field(
        default="",
        title=N_("Client certificate"),
        description=N_("PEM, for a server that asks who connects by certificate"),
        json_schema_extra=layout(group=TLS_GROUP, multiline=True),
    )


def _client_key_field() -> Any:
    return Field(
        default=SecretStr(""),
        title=N_("Client key"),
        description=N_("PEM, the private key of the client certificate"),
        json_schema_extra=layout(group=TLS_GROUP, multiline=True),
    )


def _passphrase_field() -> Any:
    return Field(
        default=SecretStr(""),
        title=N_("Key passphrase"),
        description=N_("Only when the client key is encrypted"),
        json_schema_extra=layout(group=TLS_GROUP),
    )


@dataclass(frozen=True)
class TlsSettings:
    """What a driver is told, every PEM already checked and rewrapped.

    `ca` is None for the system's authorities; `client_key` is already opened
    (`unlocked`). Nothing here may reach a log, so the `repr` names the mode
    and no more.
    """

    mode: TlsMode
    ca: str | None
    client_certificate: str | None
    client_key: str | None

    def __repr__(self) -> str:
        return f"TlsSettings({self.mode})"

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def verifies(self) -> bool:
        return self.mode in ("verify_ca", "verify_full")

    def fingerprint(self) -> str:
        """The block as a short name, for a pool's key: it changes when any PEM does."""
        text = "\0".join(
            [self.mode, *(part or "" for part in (self.ca, self.client_certificate, self.client_key))]
        )
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


class _TlsFields(BaseModel):
    """What every block shares; each narrows the mode and the trust it offers."""

    tls_mode: TlsMode = _mode_field("disabled", ("disabled", "required", "verify_ca", "verify_full"))
    tls_trust: TlsTrust = _trust_field(("system", "certificate"))
    tls_ca_certificate: str = _ca_field()
    tls_client_certificate: str = _client_certificate_field()
    tls_client_key: SecretStr = _client_key_field()
    tls_client_key_passphrase: SecretStr = _passphrase_field()

    @field_validator("tls_ca_certificate", "tls_client_certificate")
    @classmethod
    def _certificate(cls, text: str) -> str:
        if text.strip() == "":
            return ""
        return pem(text, CERTIFICATE, say("Paste a certificate in PEM, BEGIN CERTIFICATE and all"))

    @field_validator("tls_client_key")
    @classmethod
    def _key(cls, key: SecretStr) -> SecretStr:
        text = key.get_secret_value()
        if text.strip() == "":
            return SecretStr("")
        return SecretStr(
            pem(text, PRIVATE_KEYS, say("Paste a private key in PEM, BEGIN PRIVATE KEY and all"))
        )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.tls_trust == "certificate" and self.tls_ca_certificate == "":
            raise ValueError(say("Paste the CA certificate, or trust the system's authorities"))
        certificate = self.tls_client_certificate != ""
        key = self.tls_client_key.get_secret_value() != ""
        if certificate and not key:
            raise ValueError(say("A client certificate and its key go together"))
        if key and not certificate:
            # An edit fills an empty secret box with the stored value, so the
            # key cannot be emptied by hand; emptying the certificate is how a
            # client certificate is taken away, key and passphrase with it.
            self.tls_client_key = SecretStr("")
            self.tls_client_key_passphrase = SecretStr("")
            key = False
        if certificate and self.tls_mode == "disabled":
            raise ValueError(say("A client certificate needs TLS switched on"))
        if key:
            unlocked(
                self.tls_client_key.get_secret_value(),
                self.tls_client_key_passphrase.get_secret_value(),
            )
        return self

    def tls(self) -> TlsSettings:
        trust = self.tls_trust
        ca: str | None = None
        if trust == "certificate":
            ca = self.tls_ca_certificate
        elif trust == "amazon_rds":
            ca = AMAZON_RDS_BUNDLE.read_text(encoding="ascii")
        key = self.tls_client_key.get_secret_value()
        return TlsSettings(
            mode=self.tls_mode,
            ca=ca,
            client_certificate=self.tls_client_certificate or None,
            client_key=unlocked(key, self.tls_client_key_passphrase.get_secret_value())
            if key
            else None,
        )


class TlsOptions(_TlsFields):
    """The block of a source whose driver cannot fall back to plain text."""

    tls_mode: Literal["disabled", "required", "verify_ca", "verify_full"] = _mode_field(
        "disabled", ("disabled", "required", "verify_ca", "verify_full")
    )
    tls_trust: Literal["system", "certificate"] = _trust_field(("system", "certificate"))


class TlsOptionsRds(_TlsFields):
    """The same, where Amazon's own authorities may be needed (DocumentDB)."""

    tls_mode: Literal["disabled", "required", "verify_ca", "verify_full"] = _mode_field(
        "disabled", ("disabled", "required", "verify_ca", "verify_full")
    )
    tls_trust: Literal["system", "certificate", "amazon_rds"] = _trust_field(
        ("system", "certificate", "amazon_rds")
    )


class TlsOptionsWithFallback(_TlsFields):
    """PostgreSQL and MySQL: encrypted when the server offers it, by default.

    `preferred` is what both did before there was a choice — libpq's `prefer`,
    and MySQL's context that verified nothing — so it is the default, and an
    old connection is unchanged without a migration.
    """

    tls_mode: TlsMode = _mode_field(
        "preferred", ("disabled", "preferred", "required", "verify_ca", "verify_full")
    )
    tls_trust: TlsTrust = _trust_field(("system", "certificate", "amazon_rds"))


class _NamedContext(ssl.SSLContext):
    """A context that verifies the server's own name whatever address is dialled.

    A tunnel's end is a port on loopback while the certificate names the server
    (D448). Every driver given a context asks it to wrap a socket or a BIO with
    the host it dialled; this one answers with the form's host instead.
    """

    server_name: str | None = None

    def wrap_socket(self, sock: Any, *args: Any, **kwargs: Any) -> Any:
        if self.server_name is not None:
            kwargs["server_hostname"] = self.server_name
        return super().wrap_socket(sock, *args, **kwargs)

    def wrap_bio(self, incoming: Any, outgoing: Any, *args: Any, **kwargs: Any) -> Any:
        if self.server_name is not None:
            kwargs["server_hostname"] = self.server_name
        return super().wrap_bio(incoming, outgoing, *args, **kwargs)


def ssl_context(settings: TlsSettings, server_name: str | None = None) -> ssl.SSLContext | None:
    """The context a driver that takes one is handed, None when TLS is off.

    `server_name` is the host the certificate is checked against when it is not
    the one dialled. Blocking for a moment — a client key is loaded through a
    file — so an async caller builds it in a thread or once per pool.
    """
    if not settings.enabled:
        return None
    context = _NamedContext(ssl.PROTOCOL_TLS_CLIENT)
    context.server_name = server_name
    if settings.verifies:
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = settings.mode == "verify_full"
        try:
            if settings.ca is None:
                context.load_default_certs(ssl.Purpose.SERVER_AUTH)
            else:
                context.load_verify_locations(cadata=settings.ca)
        except ssl.SSLError:
            raise AdapterError("config", say("The CA certificate could not be read")) from None
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    if settings.client_certificate is not None and settings.client_key is not None:
        with TlsFiles(settings) as files:
            try:
                context.load_cert_chain(str(files.certificate), str(files.key))
            except ssl.SSLError:
                raise AdapterError(
                    "config",
                    say("The client certificate and key could not be read, or are not a pair"),
                ) from None
    return context


def _write(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)


class TlsFiles:
    """The PEMs of a block written where only this process may read them (D447).

    For a driver that reads files rather than a context. The directory is made
    by `mkdtemp` (0700) and each file is 0600; `close` removes them, and the
    owner — a pool, a held client or one `with` block — decides when.
    """

    def __init__(self, settings: TlsSettings) -> None:
        self.ca: Path | None = None
        self.certificate: Path | None = None
        self.key: Path | None = None
        # The certificate and its key in one file, as pymongo takes them.
        self.pair: Path | None = None
        self._folder: Path | None = None
        wanted = [
            ("ca.pem", settings.ca),
            ("cert.pem", settings.client_certificate),
            ("key.pem", settings.client_key),
        ]
        if all(text is None for _, text in wanted):
            return
        self._folder = Path(tempfile.mkdtemp(prefix="dp-tls-"))
        try:
            for name, text in wanted:
                if text is None:
                    continue
                path = self._folder / name
                _write(path, text)
                if name == "ca.pem":
                    self.ca = path
                elif name == "cert.pem":
                    self.certificate = path
                else:
                    self.key = path
            if settings.client_certificate is not None and settings.client_key is not None:
                self.pair = self._folder / "pair.pem"
                _write(self.pair, settings.client_certificate + settings.client_key)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._folder is not None:
            shutil.rmtree(self._folder, ignore_errors=True)
            self._folder = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def name_not_verifiable(settings: TlsSettings, tunnel: str) -> None:
    """Refuse Verify full through a tunnel, for a driver that cannot name the server (D448)."""
    if tunnel and settings.mode == "verify_full":
        raise AdapterError(
            "config",
            say(
                "Through an SSH tunnel this source cannot check the server's name; choose Verify CA"
            ),
        )


# Where a program run in a container of its own (a console, a backup) finds
# the PEMs: written by its shell from the environment under umask 077, the
# variables unset before the program starts, so nothing lands in an argument.
PROGRAM_FOLDER = "/tmp/dp-tls"
# The certificate and its key in one file, for a program that takes them so.
PROGRAM_PAIR = f"{PROGRAM_FOLDER}/pair.pem"
_PROGRAM_FILES = (
    ("DP_TLS_CA", "ca.pem"),
    ("DP_TLS_CERT", "cert.pem"),
    ("DP_TLS_KEY", "key.pem"),
)


@dataclass(frozen=True)
class ProgramPaths:
    """Where each PEM is inside the program's container, None when there is none."""

    ca: str | None
    certificate: str | None
    key: str | None


def program_paths(settings: TlsSettings) -> ProgramPaths:
    def at(name: str, text: str | None) -> str | None:
        return None if text is None or not settings.enabled else f"{PROGRAM_FOLDER}/{name}"

    return ProgramPaths(
        ca=at("ca.pem", settings.ca),
        certificate=at("cert.pem", settings.client_certificate),
        key=at("key.pem", settings.client_key),
    )


def with_program_files(
    argv: tuple[str, ...], settings: TlsSettings
) -> tuple[tuple[str, ...], dict[str, str]]:
    """The program started by a shell that writes its PEMs first, and their variables.

    Unchanged when there is nothing to write. The program's own arguments are
    passed through `"$@"`, so nothing is quoted twice.
    """
    texts = (settings.ca, settings.client_certificate, settings.client_key)
    environment = {
        variable: text
        for (variable, _), text in zip(_PROGRAM_FILES, texts, strict=True)
        if text is not None and settings.enabled
    }
    if not environment:
        return argv, {}
    writes = "".join(
        f'[ -n "${variable}" ] && printf "%s" "${variable}" > {PROGRAM_FOLDER}/{name}; '
        for variable, name in _PROGRAM_FILES
    )
    pair = (
        f"[ -f {PROGRAM_FOLDER}/cert.pem ] && "
        f"cat {PROGRAM_FOLDER}/cert.pem {PROGRAM_FOLDER}/key.pem > {PROGRAM_PAIR}; "
    )
    unset = " ".join(variable for variable, _ in _PROGRAM_FILES)
    script = (
        f"umask 077; mkdir -p {PROGRAM_FOLDER}; {writes}{pair}unset {unset}; "
        'exec "$@"'
    )
    return ("sh", "-c", script, "sh", *argv), environment
