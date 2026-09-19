"""A shell on an SSH server, as the terminal gets it (D149).

Against `docker compose up -d sshd`, except where the refusal comes before
anything is sent: a locked key and a server key nobody confirmed are refused
without a server at all.
"""

import asyncio
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.adapters.credentials import SigningKey
from app.adapters.protocol import AdapterError
from app.adapters.registry import AdapterContext
from app.adapters.ssh import keys
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshKeyAuth, SshPassword
from app.adapters.terminal import Terminal, TerminalSize
from tests.utils import services
from tests.utils.ssh import pinned_key


class _LockedKeys:
    async def signing_key(self, key_id: uuid.UUID) -> SigningKey:
        raise AdapterError("locked", "The SSH key is locked")


@pytest.fixture
def server() -> dict[str, object]:
    parts = urlsplit(services.SSH.require())
    return {
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }


@pytest.fixture
async def adapter(server: dict[str, object]) -> SshAdapter:
    pinned = await pinned_key(str(server["host"]), int(str(server["port"])))
    options = SshPassword.model_validate(
        {"auth_method": "password", **server, "host_key": pinned}
    )
    return SshAdapter(options, AdapterContext(home_dir=Path(".")))


async def _until(terminal: Terminal, needle: bytes) -> bytes:
    """Output until `needle` appears; what the shell echoes back included."""
    seen = b""
    async with asyncio.timeout(10):
        while needle not in seen:
            chunk = await terminal.read()
            if chunk == b"":
                break
            seen += chunk
    return seen


async def test_a_terminal_is_a_shell_at_the_size_it_was_opened_with(
    adapter: SshAdapter,
) -> None:
    terminal = await adapter.open_terminal(TerminalSize(cols=91, rows=23))
    try:
        # The arithmetic is done by the shell, so the answer cannot be the
        # echo of what was typed.
        await terminal.write(b'stty size; echo "dp-$((6*7))"\n')
        seen = await _until(terminal, b"dp-42")
    finally:
        await terminal.close()

    assert b"dp-42" in seen
    assert b"23 91" in seen


async def test_a_terminal_follows_the_window_it_is_drawn_in(adapter: SshAdapter) -> None:
    terminal = await adapter.open_terminal(TerminalSize(cols=80, rows=24))
    try:
        terminal.resize(TerminalSize(cols=120, rows=40))
        await terminal.write(b'stty size; echo "dp-$((6*7))"\n')
        seen = await _until(terminal, b"dp-42")
    finally:
        await terminal.close()

    assert b"40 120" in seen


async def test_a_shell_that_exits_ends_the_terminal_with_its_status(
    adapter: SshAdapter,
) -> None:
    terminal = await adapter.open_terminal(TerminalSize(cols=80, rows=24))
    try:
        await terminal.write(b"exit 3\n")
        async with asyncio.timeout(10):
            while await terminal.read() != b"":
                pass
        status = await terminal.exit_status()
    finally:
        await terminal.close()

    assert status == 3


async def test_a_locked_key_opens_no_terminal_and_reaches_no_server() -> None:
    options = SshKeyAuth.model_validate(
        {
            "auth_method": "key",
            # Nothing answers here, so reaching it would be a network failure
            # rather than the refusal this expects.
            "host": "server.invalid",
            "username": "deploy",
            "key_id": str(uuid.uuid4()),
            "host_key": keys.generate("ed25519", None).facts.public_key,
        }
    )
    adapter = SshAdapter(options, AdapterContext(home_dir=Path("."), keys=_LockedKeys()))

    with pytest.raises(AdapterError) as refused:
        await adapter.open_terminal(TerminalSize(cols=80, rows=24))

    assert refused.value.error_kind == "locked"


async def test_a_server_key_nobody_confirmed_opens_no_terminal() -> None:
    options = SshPassword.model_validate(
        {
            "auth_method": "password",
            "host": "server.invalid",
            "username": "deploy",
            "password": "secret",
        }
    )
    adapter = SshAdapter(options, AdapterContext(home_dir=Path(".")))

    with pytest.raises(AdapterError) as refused:
        await adapter.open_terminal(TerminalSize(cols=80, rows=24))

    assert refused.value.error_kind == "config"
