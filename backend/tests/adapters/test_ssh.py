"""An SSH server as a source type, as far as it can be seen without one (D144, D145)."""

import uuid
from pathlib import Path

import pytest

from app.adapters import options as adapter_options
from app.adapters import registry
from app.adapters.protocol import SupportsCatalog, SupportsContent, SupportsNodePath
from app.adapters.registry import AdapterContext
from app.adapters.ssh import keys
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshKeyAuth, SshPassword
from app.adapters.ssh.session import Remote
from app.adapters.terminal import SupportsTerminal

PINNED = keys.generate("ed25519", None).facts.public_key


def _password(**changes: object) -> SshPassword:
    fields: dict[str, object] = {
        "auth_method": "password",
        "host": "127.0.0.1",
        "port": 1,
        "username": "somebody",
        "password": "secret",
        "host_key": PINNED,
    }
    return SshPassword.model_validate(fields | changes)


def _adapter(options: SshPassword | SshKeyAuth) -> SshAdapter:
    return SshAdapter(options, AdapterContext(home_dir=Path(".")))


def test_the_type_is_registered_among_the_file_stores() -> None:
    kind = registry.get("ssh")

    assert kind.title == "SSH"
    assert kind.category == "files"
    assert kind.adapter_class is SshAdapter


def test_what_it_can_do_is_read_off_the_driver() -> None:
    adapter = _adapter(_password())
    assert isinstance(adapter, SupportsCatalog)
    assert isinstance(adapter, SupportsNodePath)
    assert isinstance(adapter, SupportsContent)

    capabilities = registry.capabilities_of(registry.get("ssh"))
    titles = {item.title for item in capabilities}
    files = {item.title for item in registry.capabilities_of(registry.get("file"))}

    # The file explorer over another storage (D150): everything the file
    # source does, but a folder of a server does not become a connection.
    assert files - {"Connect folder"} <= titles
    assert "Connect folder" not in titles
    assert {"Read rows", "Search inside files", "Paste", "Archive"} <= titles
    # The one shell is the terminal, and a screen asks for it by code (D149).
    assert isinstance(adapter, SupportsTerminal)
    assert "terminal" in {item.code for item in capabilities}


def test_a_source_without_a_shell_claims_no_terminal() -> None:
    codes = {item.code for item in registry.capabilities_of(registry.get("file"))}

    assert "terminal" not in codes


def test_a_password_is_a_secret_and_a_key_is_named_rather_than_kept() -> None:
    """The key itself is its owner's, in a store of its own (D146)."""
    schema = registry.get("ssh").options_schema

    assert adapter_options.secret_field_names(schema) == {"password"}
    assert adapter_options.key_reference_names(schema) == {"key_id"}


async def test_nothing_connects_to_a_server_nobody_has_recognised() -> None:
    """A password is not sent to a server whose key nobody confirmed (D145)."""
    result = await _adapter(_password(host_key="")).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"
    assert "confirm" in result.message


async def test_a_server_that_is_not_there_is_a_network_answer() -> None:
    result = await _adapter(_password()).check_connection()

    assert result.ok is False
    assert result.error_kind == "network"
    assert "127.0.0.1" not in result.message


async def test_a_key_connection_with_no_keys_at_hand_refuses_rather_than_guesses() -> None:
    options = SshKeyAuth(
        auth_method="key",
        host="127.0.0.1",
        port=1,
        username="somebody",
        key_id=uuid.uuid4(),
        host_key=PINNED,
    )

    result = await _adapter(options).check_connection()

    assert result.ok is False
    assert result.error_kind == "config"


def test_the_pinned_key_is_described_without_asking_the_server() -> None:
    described = SshAdapter.pinned_server_key({"host_key": PINNED})

    assert described is not None
    assert described.algorithm == "ssh-ed25519"
    assert SshAdapter.pinned_server_key({"host_key": ""}) is None


async def test_asking_for_a_server_key_needs_an_address() -> None:
    with pytest.raises(ValueError, match="host"):
        await SshAdapter.presented_server_key({"host": " "})


@pytest.mark.parametrize("node_id", ["..", "../etc", "a/../..", "/etc", "a//b", "C:"])
def test_a_node_id_never_leaves_the_folder_it_is_below(node_id: str) -> None:
    remote = Remote(sftp=None, root="/home/somebody")  # type: ignore[arg-type]  # only the path rule is asked

    with pytest.raises(ValueError):
        remote.path_of(node_id)


def test_a_node_id_is_the_path_below_the_root() -> None:
    remote = Remote(sftp=None, root="/home/somebody")  # type: ignore[arg-type]  # only the path rule is asked

    assert remote.path_of(None) == "/home/somebody"
    assert remote.path_of("logs/today.log") == "/home/somebody/logs/today.log"


@pytest.mark.parametrize(
    ("options", "line"),
    [
        ({"host": "example.org", "username": "deploy", "port": 22}, "ssh://deploy@example.org"),
        ({"host": "127.0.0.1", "username": "dataplayer", "port": 49222}, "ssh://dataplayer@127.0.0.1:49222"),
        ({"host": "::1", "username": "a@b", "port": 2222}, "ssh://a%40b@[::1]:2222"),
        ({"host": "example.org"}, "ssh://example.org"),
        ({"host": " "}, None),
    ],
)
def test_the_address_is_the_line_openssh_takes(options: dict[str, object], line: str | None) -> None:
    assert SshAdapter.draft_connection_string(options) == line
