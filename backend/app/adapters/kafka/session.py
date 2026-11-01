"""How this application talks to a Kafka cluster, and nothing about what for.

confluent-kafka is synchronous and runs librdkafka's threads of its own, so a
whole operation — make the clients, ask, close them — is one call into the
thread pool (D304). A client per operation, as ZooKeeper has a session per
operation: a client kept open holds connections to every broker for nobody.

librdkafka's messages name the brokers they failed on, so none of them cross
this boundary.
"""

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient
from starlette.concurrency import run_in_threadpool

from app.adapters.kafka.options import MECHANISMS, KafkaNoAuth, KafkaOptions
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    ErrorKind,
    NodeNotFound,
)
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)


class _DriverLog:
    """librdkafka's own lines, at debug: it writes one per broker per retry, at
    error, for a failure `reduced` already logs once."""

    _log = logging.getLogger(__name__ + ".librdkafka")

    def log(self, level: int, message: str, *args: Any) -> None:
        del level
        self._log.debug(message, *args)


_driver_log = _DriverLog()

# What one request to the cluster may cost.
TIMEOUT_SECONDS = 5.0

# Never joined and never committed: a page assigns partitions to itself
# (D306). The id is still required by the client.
BROWSING_GROUP = "dataplayer-browse"


class KafkaClients:
    """The clients of one operation, made when first asked for."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._admin: AdminClient | None = None
        self._consumer: Consumer | None = None
        # What librdkafka reported while the operation ran: a refused password
        # arrives here, and the request itself only times out.
        self.errors: list[KafkaError] = []

    def _on_error(self, error: KafkaError) -> None:
        self.errors.append(error)

    def admin(self) -> AdminClient:
        if self._admin is None:
            self._admin = AdminClient(self._config, error_cb=self._on_error)
        return self._admin

    def consumer(self) -> Consumer:
        if self._consumer is None:
            self._consumer = Consumer(
                {
                    **self._config,
                    "error_cb": self._on_error,
                    "group.id": BROWSING_GROUP,
                    "enable.auto.commit": False,
                    "enable.auto.offset.store": False,
                    # Said when a partition is read to its end, so a page does
                    # not wait for a message that is not coming.
                    "enable.partition.eof": True,
                    # Read committed: an aborted transaction's messages are
                    # not part of the topic anybody else reads.
                    "isolation.level": "read_committed",
                }
            )
        return self._consumer

    def serve_callbacks(self) -> None:
        """Have librdkafka hand over what it reported; an admin client says
        nothing until it is polled."""
        if self._admin is not None:
            self._admin.poll(0)

    def close(self) -> None:
        if self._consumer is not None:
            try:
                self._consumer.close()
            except Exception:  # noqa: BLE001 - closing a consumer that failed
                logger.debug("Kafka consumer did not close cleanly", exc_info=True)
        # An admin client has no close; dropping it ends its threads.
        self._admin = None
        self._consumer = None


class KafkaSession:
    """A way to reach one Kafka cluster, opened per operation."""

    def __init__(self, options: KafkaOptions) -> None:
        self._options = options

    @property
    def options(self) -> KafkaOptions:
        return self._options

    def config(self) -> dict[str, Any]:
        options = self._options
        sasl = not isinstance(options, KafkaNoAuth)
        protocol = {
            (False, False): "PLAINTEXT",
            (True, False): "SSL",
            (False, True): "SASL_PLAINTEXT",
            (True, True): "SASL_SSL",
        }[(options.tls, sasl)]
        config: dict[str, Any] = {
            "bootstrap.servers": options.bootstrap_servers,
            "security.protocol": protocol,
            "client.id": "dataplayer",
            "socket.connection.setup.timeout.ms": int(TIMEOUT_SECONDS * 1000),
            "logger": _driver_log,
        }
        if options.tls:
            if options.ca_certificate.strip() != "":
                config["ssl.ca.pem"] = options.ca_certificate
            elif os.name != "nt":
                # Windows builds read the system store by default; elsewhere
                # librdkafka is told to find the system's bundle itself.
                config["ssl.ca.location"] = "probe"
        if not isinstance(options, KafkaNoAuth):
            config["sasl.mechanism"] = MECHANISMS[options.auth_method]
            config["sasl.username"] = options.user
            config["sasl.password"] = options.password.get_secret_value()
        return config

    async def run[T](self, work: Callable[[KafkaClients], T], node_id: str = "") -> T:
        """`work` with clients of its own, in the thread pool, failures reduced."""
        return await run_in_threadpool(self._run, work, node_id)

    def _run[T](self, work: Callable[[KafkaClients], T], node_id: str) -> T:
        clients = KafkaClients(self.config())
        try:
            return work(clients)
        except NodeNotFound, AdapterError, ValueError:
            raise
        except KafkaException as failure:
            error = failure.args[0] if failure.args else None
            if isinstance(error, KafkaError) and error.code() in _MISSING:
                raise NodeNotFound(node_id) from None
            clients.serve_callbacks()
            raise reduced(failure, clients.errors) from None
        finally:
            clients.close()

    async def check(self) -> ConnectionCheckResult:
        """Ask the cluster for its brokers, in words that name no address."""
        started = time.perf_counter()
        try:
            await self.run(lambda clients: describe_cluster(clients))
        except AdapterError as failure:
            return _refused(failure.error_kind, failure.message)
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )


def describe_cluster(clients: KafkaClients) -> Any:
    return clients.admin().describe_cluster(request_timeout=TIMEOUT_SECONDS).result()


_MISSING = {
    KafkaError.UNKNOWN_TOPIC_OR_PART,
    KafkaError.GROUP_ID_NOT_FOUND,
}

_AUTH = {
    KafkaError._AUTHENTICATION,
    KafkaError.SASL_AUTHENTICATION_FAILED,
    KafkaError.ILLEGAL_SASL_STATE,
    KafkaError.UNSUPPORTED_SASL_MECHANISM,
}

_DENIED = {
    KafkaError.TOPIC_AUTHORIZATION_FAILED,
    KafkaError.GROUP_AUTHORIZATION_FAILED,
    KafkaError.CLUSTER_AUTHORIZATION_FAILED,
}

_UNREACHABLE = {
    KafkaError._TRANSPORT,
    KafkaError._ALL_BROKERS_DOWN,
    KafkaError._RESOLVE,
    KafkaError._TIMED_OUT,
    KafkaError.REQUEST_TIMED_OUT,
}


def _refused(kind: ErrorKind, message: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(ok=False, message=message, error_kind=kind)


def reduced(failure: BaseException, reported: list[KafkaError]) -> AdapterError:
    """The driver's failure as a kind and a sentence of this repository's.

    What librdkafka reported along the way is read first: a refused password
    or certificate is said there, while the request that failed only says it
    timed out. Logged on the server, never passed on (D184).
    """
    errors = [*reported]
    if failure.args and isinstance(failure.args[0], KafkaError):
        errors.append(failure.args[0])
    known = _known({error.code() for error in errors})
    if known is not None:
        logger.warning("Kafka failed: %r; reported %r", failure, reported)
        return known
    ref = record_failure(logger, "Kafka: an unexpected failure", failure)
    return AdapterError(
        "unknown", with_ref(say("The Kafka cluster could not do that"), ref)
    )


def _known(codes: set[int]) -> AdapterError | None:
    if codes & _AUTH:
        return AdapterError("auth", say("This connection was refused by the cluster"))
    if KafkaError._SSL in codes:
        return AdapterError(
            "network", say("The brokers' certificates could not be verified")
        )
    if codes & _DENIED:
        return AdapterError("auth", say("This connection may not do that"))
    if codes & _UNREACHABLE:
        return AdapterError("network", say("Could not reach the Kafka cluster"))
    if (
        KafkaError.INVALID_PARTITIONS in codes
        or KafkaError.OFFSET_OUT_OF_RANGE in codes
    ):
        return AdapterError("config", say("The Kafka cluster refused that"))
    return None
