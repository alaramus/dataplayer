"""Connections to an FTP server, kept between requests, and their failures as
kinds (D384).

`ftplib` is the standard library's and blocks, which is what a storage does
(D151). It is imported by this package and by nothing else, the rule `psycopg`
follows. A control connection serves one command at a time, so connections
are lent from a pool per set of options: a request takes one, and gives it back
when it is done.

Two things the standard library does not do on its own:

- **Names in any bytes.** ftplib decodes the control and data channels as
  strict UTF-8, so one file named in Windows-1251 would fail a whole listing.
  Both are read with `surrogateescape` here, and a name that is not UTF-8 is
  left out of a listing rather than breaking it.
- **TLS on the data channel resumes the control channel's session.** vsftpd,
  FileZilla Server and pure-ftpd refuse a data connection that does not, and
  ftplib does not do it.
"""

import ftplib
import hashlib
import json
import logging
import socket
import ssl
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Literal

from app.adapters.ftp.options import FtpOptions, FtpPassword
from app.adapters.protocol import AdapterError
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
# How many connections one set of options may hold open at once. A server
# commonly limits the connections from one address, and the explorer rarely
# needs more than a listing and a file being read at the same time.
MOST_CONNECTIONS = 4
# How long a request waits for a connection the others hold.
WAIT_SECONDS = 60
# A connection idle for longer is asked NOOP before it is lent again: a server
# closes an idle one after a few minutes, and says so only to the next command.
FRESH_SECONDS = 15
# Kept idle no longer than this; past it a connection is closed, not tried.
IDLE_SECONDS = 120
_KEPT_POOLS = 32

# What a broken connection raises, as opposed to an answer of the server.
BROKEN = (
    EOFError,
    ConnectionError,
    TimeoutError,
    ssl.SSLError,
    ftplib.error_proto,
    ftplib.error_reply,
)

CRLF = "\r\n"


class _Lenient(ftplib.FTP):
    """Plain FTP, whose names are carried as bytes whatever they are."""

    encoding = "utf-8"

    def putline(self, line: str) -> None:
        if "\r" in line or "\n" in line:
            raise ValueError(
                say("A name with a line break in it cannot be sent to the server")
            )
        assert self.sock is not None, "a line is sent only once connected"
        self.sock.sendall((line + CRLF).encode(self.encoding, "surrogateescape"))

    def lenient(self) -> None:
        """The control channel read again, past whatever ftplib opened it as."""
        assert self.sock is not None, "read again only once connected"
        self.file = self.sock.makefile(
            "r", encoding=self.encoding, errors="surrogateescape"
        )


class _Explicit(_Lenient, ftplib.FTP_TLS):
    """TLS asked for with AUTH TLS, on the data channel as on the control one."""

    def ntransfercmd(
        self, cmd: str, rest: int | str | None = None
    ) -> tuple[socket.socket, int | None]:
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:  # type: ignore[attr-defined]  # FTP_TLS keeps it private and undeclared
            session = getattr(self.sock, "session", None)
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=session
            )
        return conn, size


class _Implicit(_Explicit):
    """The older FTPS: TLS from the first byte, on its own port."""

    def connect(
        self,
        host: str = "",
        port: int = 0,
        timeout: float = -999,
        source_address: tuple[str, int] | None = None,
    ) -> str:
        self.host, self.port = host, port
        if timeout != -999:
            self.timeout = timeout
        raw = socket.create_connection(
            (host, port), self.timeout, source_address=source_address
        )
        self.af = raw.family
        self.sock = self.context.wrap_socket(raw, server_hostname=host)
        self.lenient()
        self.welcome = self.getresp()
        return self.welcome


@dataclass
class Connection:
    """One signed-in control connection and what is known of it."""

    ftp: _Lenient
    # The folder the server signed this user into: where a relative folder of
    # the options is below.
    home: str
    features: frozenset[str]
    transfer_type: Literal["A", "I"] | None = None
    used_at: float = field(default_factory=time.monotonic)
    # Something went wrong while it was lent; asked NOOP before it is lent again.
    doubtful: bool = False
    # Lent before: the server may have closed it since, which only the next
    # command finds out.
    reused: bool = False

    def binary(self) -> None:
        self._type("I")

    def text(self) -> None:
        self._type("A")

    def _type(self, wanted: Literal["A", "I"]) -> None:
        if self.transfer_type != wanted:
            self.ftp.voidcmd(f"TYPE {wanted}")
            self.transfer_type = wanted

    def has(self, feature: str) -> bool:
        return feature in self.features

    def close(self) -> None:
        with suppress(Exception):
            self.ftp.close()

    def in_step(self, *, transfer_open: bool = False) -> bool:
        """Whether the next reply read will be the answer to the next command.

        After a transfer cut short, a server answers it with 426, 226 or both,
        and an extra reply left unread would be taken for the answer to every
        command after. NOOP is sent and replies read until its 200. With a
        transfer just closed, its own reply is waited for first: a server may
        answer NOOP before it notices the transfer ended, and the 226 arriving
        after the 200 would answer the next command instead.
        """
        try:
            if transfer_open:
                with suppress(ftplib.error_temp, ftplib.error_perm):
                    self.ftp.getresp()
            self.ftp.putcmd("NOOP")
            for _ in range(4):
                try:
                    reply = self.ftp.getresp()
                except ftplib.error_temp, ftplib.error_perm:
                    continue
                if reply.startswith("200"):
                    return True
        except (*BROKEN, OSError):
            return False
        return False


class FtpPool:
    """The connections of one set of options, lent one request at a time."""

    def __init__(self, options: FtpOptions) -> None:
        self.options = options
        self._idle: list[Connection] = []
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(MOST_CONNECTIONS)

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """A connection for one request, given back when it ends.

        An answer of the server — a missing file, a refusal — leaves the
        connection to be lent again after a NOOP; a dropped one is closed.
        """
        lent = self.take()
        try:
            yield lent
        except BaseException as failure:
            self.give(lent, broken=isinstance(failure, BROKEN), doubtful=True)
            raise
        else:
            self.give(lent)

    def take(self, *, checked: bool = False) -> Connection:
        """A connection to lend. `checked` asks NOOP of a kept one first, for
        a caller that cannot simply try again on a new one."""
        if not self._slots.acquire(timeout=WAIT_SECONDS):
            raise AdapterError("timeout", say("Every connection to the server is busy"))
        try:
            while True:
                with self._lock:
                    found = self._idle.pop() if self._idle else None
                if found is None:
                    return connected(self.options)
                idle_for = time.monotonic() - found.used_at
                if idle_for > IDLE_SECONDS:
                    found.close()
                    continue
                if (
                    found.doubtful or checked or idle_for > FRESH_SECONDS
                ) and not found.in_step():
                    found.close()
                    continue
                found.doubtful = False
                return found
        except BaseException:
            self._slots.release()
            raise

    def give(
        self, lent: Connection, *, broken: bool = False, doubtful: bool = False
    ) -> None:
        try:
            if broken:
                lent.close()
                return
            lent.used_at = time.monotonic()
            lent.doubtful = doubtful
            lent.reused = True
            with self._lock:
                self._idle.append(lent)
        finally:
            self._slots.release()

    def close(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, []
        for lent in idle:
            lent.close()


_pools: OrderedDict[str, FtpPool] = OrderedDict()
_pools_lock = threading.Lock()


def identity_of(options: FtpOptions) -> str:
    """One string for a server, a user and where browsing stands.

    Hashed because it holds the password. Two users may read different files,
    so the copies of their files are kept apart by it (D152).
    """
    secret = (
        options.password.get_secret_value() if isinstance(options, FtpPassword) else ""
    )
    dumped = json.dumps(
        {**options.model_dump(mode="json"), "password": secret}, sort_keys=True
    )
    return hashlib.sha256(dumped.encode()).hexdigest()


def pool_for(options: FtpOptions) -> FtpPool:
    key = identity_of(options)
    with _pools_lock:
        found = _pools.get(key)
        if found is not None:
            _pools.move_to_end(key)
            return found
        made = FtpPool(options)
        _pools[key] = made
        evicted = []
        while len(_pools) > _KEPT_POOLS:
            evicted.append(_pools.popitem(last=False)[1])
    for pool in evicted:
        pool.close()
    return made


def connected(options: FtpOptions) -> Connection:
    """A new control connection, signed in, binary, passive. Blocking.

    Every failure is reduced to a kind and a sentence of this repository's:
    the server's own words may name its paths, and a socket error names the
    address.
    """
    ftp: _Lenient | None = None
    try:
        if options.security == "none":
            ftp = _Lenient(timeout=TIMEOUT_SECONDS)
        else:
            context = ssl.create_default_context()
            if not options.verify_tls:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            tls_class = _Implicit if options.security == "implicit" else _Explicit
            ftp = tls_class(context=context, timeout=TIMEOUT_SECONDS)
        ftp.connect(options.host, options.port)
        ftp.lenient()
        if isinstance(ftp, _Explicit) and options.security == "explicit":
            try:
                ftp.auth()
            except ftplib.error_perm:
                raise AdapterError(
                    "config",
                    say(
                        "The server does not offer TLS; choose no encryption to sign in without it"
                    ),
                ) from None
            ftp.lenient()
        user, password = options.login
        # FTP_TLS asks AUTH TLS itself only on a channel not encrypted yet.
        ftp.login(user, password)
        if isinstance(ftp, _Explicit):
            ftp.prot_p()
        ftp.set_pasv(True)
        features = _features(ftp)
        if "UTF8" in features:
            with suppress(ftplib.error_perm, ftplib.error_temp):
                ftp.sendcmd("OPTS UTF8 ON")
        home = ftp.pwd()
    except BaseException as failure:
        _close(ftp)
        if isinstance(failure, AdapterError):
            raise
        if isinstance(failure, ftplib.error_perm) and str(failure).startswith("530"):
            raise AdapterError(
                "auth",
                say("The server did not accept this user and password")
                if isinstance(options, FtpPassword)
                else say("The server does not let anonymous users in"),
            ) from None
        raise reduced(failure) from None
    connection = Connection(ftp=ftp, home=home or "/", features=features)
    connection.binary()
    return connection


def _close(ftp: ftplib.FTP | None) -> None:
    if ftp is not None:
        with suppress(Exception):
            ftp.close()


def _features(ftp: ftplib.FTP) -> frozenset[str]:
    """What FEAT names, by the first word of each line: `MLST`, `MDTM`,
    `SIZE`, `UTF8`, `MFMT`. A server that does not answer FEAT has none."""
    try:
        reply = ftp.sendcmd("FEAT")
    except ftplib.error_perm, ftplib.error_temp:
        return frozenset()
    names = set()
    for line in reply.splitlines()[1:-1]:
        word = line.strip().split(" ", 1)[0].upper()
        if word:
            names.add(word)
    return frozenset(names)


def reduced(failure: BaseException) -> AdapterError:
    """A failure as a kind and a sentence, the server's own words logged and
    never passed on."""
    known = _known(failure)
    if known is not None:
        logger.warning("FTP failed: %r", failure)
        return known
    ref = record_failure(logger, "FTP: an unexpected failure", failure)
    return AdapterError("unknown", with_ref(say("The server could not do that"), ref))


def _known(failure: BaseException) -> AdapterError | None:
    if isinstance(failure, ssl.SSLCertVerificationError):
        return AdapterError("config", say("The server's certificate was not accepted"))
    if isinstance(failure, ssl.SSLError):
        return AdapterError("config", say("The TLS connection to the server failed"))
    if isinstance(failure, TimeoutError):
        return AdapterError("timeout", say("The server did not answer in time"))
    if isinstance(failure, socket.gaierror):
        return AdapterError("network", say("The server's name could not be resolved"))
    if isinstance(
        failure, EOFError | ConnectionError | ftplib.error_proto | ftplib.error_reply
    ):
        return AdapterError("network", say("The server closed the connection"))
    if isinstance(failure, ftplib.error_temp):
        if str(failure).startswith("421"):
            return AdapterError(
                "network", say("The server has too many connections open")
            )
        return AdapterError("network", say("The server is busy; try again"))
    if isinstance(failure, ftplib.error_perm):
        return AdapterError("unknown", say("The server refused that"))
    if isinstance(failure, OSError):
        return AdapterError("network", say("Could not reach the server"))
    return None
