"""An FTP server for the FTP source's tests, run in this process (D386).

pyftpdlib, a development dependency: pure Python, so the tests need no
container and CI no service. It speaks MLSD; a handler without MLSD and MLST
answers LIST alone, as vsftpd does, so both ways a listing is read are tested.
With `tls` it requires explicit TLS on both channels, under a certificate made
for the test; it has no implicit TLS.
"""

import datetime
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pyftpdlib.authorizers import DummyAuthorizer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

USER = "alice"
PASSWORD = "wonderland"

Listing = Literal["mlsd", "list"]


@contextmanager
def ftp_server(
    root: Path, listing: Listing = "mlsd", *, tls: bool = False
) -> Iterator[int]:
    """A server over a folder, on a free port of the loopback; yields the port."""
    authorizer = DummyAuthorizer()
    authorizer.add_user(USER, PASSWORD, str(root), perm="elradfmwMT")
    authorizer.add_anonymous(str(root))
    commands = dict(FTPHandler.proto_cmds)
    if listing == "list":
        commands.pop("MLSD")
        commands.pop("MLST")
    base: type[FTPHandler] = TLS_FTPHandler if tls else FTPHandler
    settings: dict[str, object] = {
        "authorizer": authorizer,
        "proto_cmds": {**base.proto_cmds, **commands} if tls else commands,
        "banner": "test server",
    }
    if tls:
        settings |= {
            "certfile": str(_certificate(root.parent / "certificate.pem")),
            "tls_control_required": True,
            "tls_data_required": True,
        }
    handler = type("Handler", (base,), settings)
    server = ThreadedFTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"timeout": 0.05, "handle_exit": False},
        daemon=True,
    )
    thread.start()
    try:
        yield server.address[1]
    finally:
        server.close_all()
        thread.join(timeout=5)


def _certificate(path: Path) -> Path:
    """A key and a certificate of its own making for 127.0.0.1, in one file."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        + certificate.public_bytes(serialization.Encoding.PEM)
    )
    return path
