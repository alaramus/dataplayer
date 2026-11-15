"""How this application reaches a mailbox, and nothing about what for.

`imaplib` and `smtplib` are synchronous, so one operation — connect, sign in,
do the work, log out — is one call into the thread pool (D368). No session is
kept between requests.

The libraries' own messages name the host and, for a refused login, repeat the
server's words; none of it crosses this boundary.
"""

import imaplib
import logging
import smtplib
import socket
import ssl
import time
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from app.adapters.mail.options import MailOptions
from app.adapters.mailbox import MailboxRefused
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

# What connecting and one exchange may cost.
TIMEOUT_SECONDS = 20.0


class StepFailed(Exception):
    """A failure already reduced, with the step it happened at (D368)."""

    def __init__(self, failure: AdapterError) -> None:
        super().__init__(failure.message)
        self.failure = failure


class MailSession:
    def __init__(self, options: MailOptions) -> None:
        self._options = options

    @property
    def options(self) -> MailOptions:
        return self._options

    async def imap[T](self, work: Callable[[imaplib.IMAP4], T]) -> T:
        """`work` on a signed-in IMAP session of its own, in the thread pool."""
        return await run_in_threadpool(self._imap, work)

    async def smtp[T](self, work: Callable[[smtplib.SMTP], T]) -> T:
        return await run_in_threadpool(self._smtp, work)

    def _imap[T](self, work: Callable[[imaplib.IMAP4], T]) -> T:
        try:
            conn = self.open_imap()
        except StepFailed as failed:
            raise failed.failure from None
        try:
            return work(conn)
        except MailboxRefused, AdapterError, ValueError:
            raise
        except (imaplib.IMAP4.error, OSError) as failure:
            raise reduced(failure, "IMAP") from None
        finally:
            _logout(conn)

    def _smtp[T](self, work: Callable[[smtplib.SMTP], T]) -> T:
        try:
            conn = self.open_smtp()
        except StepFailed as failed:
            raise failed.failure from None
        try:
            return work(conn)
        except MailboxRefused, AdapterError, ValueError:
            raise
        except (smtplib.SMTPException, OSError) as failure:
            raise reduced(failure, "SMTP") from None
        finally:
            _quit(conn)

    # --- connecting, a step at a time ---------------------------------------

    def open_imap(self) -> imaplib.IMAP4:
        options = self._options
        host, port = options.imap_host, options.imap_port
        try:
            if options.imap_security == "tls":
                conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                    host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT_SECONDS
                )
            else:
                conn = imaplib.IMAP4(host, port, timeout=TIMEOUT_SECONDS)
        except (imaplib.IMAP4.error, OSError) as failure:
            raise StepFailed(_unreached(failure, say("Could not reach the IMAP server"))) from None
        try:
            if options.imap_security == "starttls":
                # Upgraded before the password is sent, or not signed in to at
                # all: a server that will not upgrade is refused (D368).
                try:
                    conn.starttls(ssl.create_default_context())
                except (imaplib.IMAP4.error, OSError) as failure:
                    if isinstance(failure, ssl.SSLError):
                        raise StepFailed(_tls_failed()) from None
                    raise StepFailed(
                        AdapterError("config", say("The IMAP server does not offer STARTTLS"))
                    ) from None
            try:
                conn.login(options.imap_login(), options.password.get_secret_value())
            except imaplib.IMAP4.error:
                raise StepFailed(
                    AdapterError("auth", say("The IMAP server refused the login or password"))
                ) from None
            except OSError as failure:
                raise StepFailed(
                    _unreached(failure, say("Could not reach the IMAP server"))
                ) from None
        except StepFailed:
            _logout(conn)
            raise
        return conn

    def open_smtp(self) -> smtplib.SMTP:
        options = self._options
        host, port = options.smtp_host, options.smtp_port
        try:
            if options.smtp_security == "tls":
                conn: smtplib.SMTP = smtplib.SMTP_SSL(
                    host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context()
                )
            else:
                conn = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
        except (smtplib.SMTPException, OSError) as failure:
            raise StepFailed(_unreached(failure, say("Could not reach the SMTP server"))) from None
        try:
            if options.smtp_security == "starttls":
                try:
                    conn.starttls(context=ssl.create_default_context())
                except smtplib.SMTPNotSupportedError:
                    raise StepFailed(
                        AdapterError("config", say("The SMTP server does not offer STARTTLS"))
                    ) from None
                except (smtplib.SMTPException, OSError) as failure:
                    if isinstance(failure, ssl.SSLError):
                        raise StepFailed(_tls_failed()) from None
                    raise StepFailed(
                        _unreached(failure, say("Could not reach the SMTP server"))
                    ) from None
            try:
                conn.ehlo_or_helo_if_needed()
                # A server inside the network may take letters without a login;
                # it says so by offering no AUTH.
                if conn.has_extn("auth"):
                    conn.login(options.smtp_login(), options.smtp_secret())
            except smtplib.SMTPAuthenticationError:
                raise StepFailed(
                    AdapterError("auth", say("The SMTP server refused the login or password"))
                ) from None
            except (smtplib.SMTPException, OSError) as failure:
                raise StepFailed(
                    _unreached(failure, say("Could not reach the SMTP server"))
                ) from None
        except StepFailed:
            _quit(conn)
            raise
        return conn

    async def check(self) -> ConnectionCheckResult:
        """Both servers, each step named when it fails (D368)."""
        started = time.perf_counter()
        try:
            await run_in_threadpool(self._check)
        except StepFailed as failed:
            return ConnectionCheckResult(
                ok=False, message=failed.failure.message, error_kind=failed.failure.error_kind
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )

    def _check(self) -> None:
        _logout(self.open_imap())
        _quit(self.open_smtp())


def _unreached(failure: BaseException, sentence: str) -> AdapterError:
    logger.warning("Mail server not reached: %r", failure)
    if isinstance(failure, ssl.SSLError):
        return _tls_failed()
    if isinstance(failure, TimeoutError | socket.timeout):
        return AdapterError("timeout", sentence)
    return AdapterError("network", sentence)


def _tls_failed() -> AdapterError:
    return AdapterError(
        "network",
        say("Could not make a secure connection; check the port and the security setting"),
    )


def reduced(failure: BaseException, protocol: str) -> AdapterError:
    """A failure after signing in, as a kind and a sentence of this repository's."""
    if isinstance(failure, TimeoutError | socket.timeout):
        logger.warning("Mail server timed out: %r", failure)
        return AdapterError("timeout", say("The mail server did not answer in time"))
    if isinstance(failure, OSError):
        logger.warning("Mail server dropped the connection: %r", failure)
        return AdapterError("network", say("The connection to the mail server was lost"))
    ref = record_failure(logger, f"{protocol}: an unexpected failure", failure)
    return AdapterError("unknown", with_ref(say("The mail server could not do that"), ref))


def _logout(conn: imaplib.IMAP4) -> None:
    try:
        conn.logout()
    except Exception:  # noqa: BLE001 - leaving a session that may already be gone
        logger.debug("IMAP session did not close cleanly", exc_info=True)


def _quit(conn: smtplib.SMTP) -> None:
    try:
        conn.quit()
    except Exception:  # noqa: BLE001 - leaving a session that may already be gone
        logger.debug("SMTP session did not close cleanly", exc_info=True)
