"""What a test does when a server it needs is not there (`tests/utils/services.py`)."""

import re
import socket
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.utils import services

TESTS = Path(__file__).parent
REGISTRY = TESTS / "utils" / "services.py"


@pytest.fixture(autouse=True)
def _registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # A refused port on Windows is only noticed when the probe gives up.
    monkeypatch.setattr(services, "PROBE_SECONDS", 0.2)
    # This run may itself have been started with --require-services.
    monkeypatch.setattr(services, "_required", False)


@contextmanager
def _listener(reply: bytes | None) -> Iterator[int]:
    """A port that accepts, and answers a hello with `reply` or hangs up."""
    stop = threading.Event()
    with socket.create_server(("127.0.0.1", 0)) as listener:
        listener.settimeout(0.05)

        def serve() -> None:
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    if reply is not None:
                        connection.recv(64)
                        connection.sendall(reply)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield listener.getsockname()[1]
        finally:
            stop.set()
            thread.join()


@pytest.fixture
def answering() -> Iterator[int]:
    with _listener(b"+PONG\r\n") as port:
        yield port


@pytest.fixture
def silent() -> Iterator[int]:
    """What Docker Desktop publishes for a container whose server is not up yet."""
    with _listener(None) as port:
        yield port


@pytest.fixture
def closed() -> int:
    with socket.create_server(("127.0.0.1", 0)) as server:
        return int(server.getsockname()[1])


def _server(port: int, *, base: bool = False, scheme: str = "redis") -> services.Server:
    # An address of its own: answers are remembered by address, and a port
    # closed in one test may be listening in the next.
    database = uuid.uuid4().hex
    return services.Server(
        name="Example",
        variable="TEST_EXAMPLE_URL",
        start="docker compose up -d example",
        read=lambda: f"{scheme}://user:hunter2@127.0.0.1:{port}/{database}",
        base=base,
    )


def test_a_server_that_answers_gives_its_address(answering: int) -> None:
    server = _server(answering)

    assert server.require() == server.url()


def test_a_test_without_its_server_is_skipped_with_how_to_start_it(closed: int) -> None:
    with pytest.raises(pytest.skip.Exception) as skipped:
        _server(closed).require()

    reason = str(skipped.value)
    assert f"127.0.0.1:{closed}" in reason
    assert "docker compose up -d example" in reason
    assert "TEST_EXAMPLE_URL" in reason
    assert "hunter2" not in reason


def test_a_port_that_accepts_but_never_answers_is_not_a_server(silent: int) -> None:
    with pytest.raises(pytest.skip.Exception):
        _server(silent).require()


def test_a_server_nobody_taught_the_probe_to_greet_is_refused(answering: int) -> None:
    with pytest.raises(ValueError, match="_PROTOCOLS"):
        _server(answering, scheme="mysql").require()


def test_without_the_base_server_the_run_stops(closed: int) -> None:
    with pytest.raises(pytest.exit.Exception):
        _server(closed, base=True).require()


def test_when_servers_are_required_a_missing_one_fails_instead(
    closed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(services, "_required", True)

    with pytest.raises(pytest.fail.Exception):
        _server(closed).require()


def test_requiring_all_stops_the_run_naming_every_missing_server(
    closed: int, answering: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = _server(closed)
    present = _server(answering)
    monkeypatch.setattr(services, "SERVERS", (present, missing))

    with pytest.raises(pytest.exit.Exception) as stopped:
        services.require_all()

    assert f"127.0.0.1:{closed}" in str(stopped.value)
    assert f"127.0.0.1:{answering}" not in str(stopped.value)
    assert services._required is False


def test_only_the_registry_reads_an_address_from_the_environment() -> None:
    """A test that finds its server by itself errors rather than skips without it."""
    reading = re.compile(r"\bos\.(environ\b|getenv\()")
    readers = [
        path.relative_to(TESTS).as_posix()
        for path in TESTS.rglob("*.py")
        if path != REGISTRY and reading.search(path.read_text(encoding="utf-8"))
    ]

    assert readers == []
