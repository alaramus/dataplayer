"""An SSH server as a source: the file explorer over SFTP, and a terminal.

Everything the file source does, it does here — tables, SQL over files, the
editor, archives, search, the file actions — because it is the same explorer
over another storage (D150). The catalog, the reader and the actions go over
SFTP and run no command on the server, so no string of a form's ever reaches a
shell (D144). The one shell is the terminal, which its owner types into (D149).

`asyncssh` is imported by this package and by nothing else, the rule `psycopg`
follows: a library upgrade has one place to change.
"""

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import quote

from app.adapters.credentials import ServerKey
from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ConnectFolder,
    ExplorerActionType,
)
from app.adapters.explorer.explorer import Explorer
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.ssh import keys
from app.adapters.ssh.options import SshOptions
from app.adapters.ssh.session import SshSession, identity_of, server_key
from app.adapters.ssh.storage import SftpStorage
from app.adapters.ssh.terminal import SshTerminal
from app.adapters.terminal import Terminal, TerminalSize

DEFAULT_PORT = 22


class SshAdapter(Explorer):
    """The explorer over one folder of a server, and a shell on it."""

    # A folder of a server does not become a connection of its own: the draft
    # would carry this connection's credentials to the browser.
    explorer_action_types: ClassVar[tuple[ExplorerActionType, ...]] = tuple(
        action_type
        for action_type in EXPLORER_ACTION_TYPES
        if action_type is not ConnectFolder
    )

    def __init__(self, options: SshOptions, context: AdapterContext) -> None:
        self._session = SshSession(options, context)
        super().__init__(SftpStorage(self._session, owner=identity_of(options)))

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def open_terminal(self, size: TerminalSize) -> Terminal:
        return await SshTerminal.open(self._session, size)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        """Where to point `ssh`, as the one line OpenSSH takes: `ssh://user@host:port`.

        Never with a password, which no SSH client takes in an address — so a
        started service's window shows this line even when it hands the
        password over (D89).
        """
        host = options.get("host")
        if not isinstance(host, str) or host.strip() == "":
            return None
        host = host.strip()
        address = f"[{host}]" if ":" in host else host
        user = options.get("username")
        if isinstance(user, str) and user != "":
            address = f"{quote(user, safe='')}@{address}"
        port = options.get("port")
        if isinstance(port, int) and not isinstance(port, bool) and port != DEFAULT_PORT:
            address = f"{address}:{port}"
        return f"ssh://{address}"

    # --- the server's own key (D145) ----------------------------------------

    @classmethod
    def pinned_server_key(cls, options: Mapping[str, Any]) -> ServerKey | None:
        pinned = options.get("host_key")
        if not isinstance(pinned, str) or pinned.strip() == "":
            return None
        return _described(pinned.strip())

    @classmethod
    async def presented_server_key(cls, options: Mapping[str, Any]) -> ServerKey:
        host = options.get("host")
        if not isinstance(host, str) or host.strip() == "":
            raise ValueError("Enter the host first")
        port = options.get("port")
        number = port if isinstance(port, int) and not isinstance(port, bool) else DEFAULT_PORT
        return _described(await server_key(host.strip(), number))


def _described(public_key: str) -> ServerKey:
    facts = keys.host_key_facts(public_key)
    return ServerKey(
        public_key=facts.public_key, algorithm=facts.algorithm, fingerprint=facts.fingerprint
    )


@register(
    name="ssh",
    title="SSH",
    category="files",
    description=(
        "A server reached over SSH. Browse its folders from where you choose and "
        "work with its files as with your own: tables, SQL over files, the "
        "editor, archives, search, and a terminal. Signs in with a password or "
        "one of your SSH keys, and only to the server whose key you confirmed."
    ),
    options_schema=SshOptions,
    adapter_class=SshAdapter,
)
def _build(options: SshOptions, context: AdapterContext) -> SshAdapter:
    return SshAdapter(options, context)
