"""Waiting until a started service answers, and what it answered to (D83, D153)."""

from pathlib import Path
from urllib.parse import urlsplit

from app.services.readiness import wait_until_ready
from tests.utils import services
from tests.utils.ssh import pinned_key


async def test_a_source_that_answers_is_ready_with_the_options_it_was_given(
    tmp_path: Path,
) -> None:
    answered = await wait_until_ready("file", {"path": "/"}, home_dir=tmp_path, timeout_seconds=0)

    assert answered == {"path": "/"}


async def test_a_started_ssh_server_is_trusted_by_the_key_it_presents(tmp_path: Path) -> None:
    """Against `docker compose up -d sshd`, as a server this application
    would have started: no key is pinned, and the one it presents is."""
    parts = urlsplit(services.SSH.require())
    host, port = str(parts.hostname), parts.port or 22
    options: dict[str, str | int] = {
        "auth_method": "password",
        "host": host,
        "port": port,
        "username": str(parts.username),
        "password": str(parts.password),
    }

    answered = await wait_until_ready("ssh", options, home_dir=tmp_path, timeout_seconds=10)

    assert answered is not None
    assert answered["host_key"] == await pinned_key(host, port)
    assert answered["password"] == options["password"]


async def test_a_server_that_presents_no_key_is_not_ready(tmp_path: Path) -> None:
    """Nothing listens on port 1, so the key is asked for until time runs out."""
    options: dict[str, str | int] = {
        "auth_method": "password",
        "host": "127.0.0.1",
        "port": 1,
        "username": "somebody",
        "password": "secret",
    }

    answered = await wait_until_ready("ssh", options, home_dir=tmp_path, timeout_seconds=0)

    assert answered is None
