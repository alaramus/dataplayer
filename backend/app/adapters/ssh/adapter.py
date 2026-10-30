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
from urllib.parse import quote, unquote, urlsplit

from app.adapters.actions import Action, ActionOffers
from app.adapters.catalog import CatalogNode
from app.adapters.credentials import ServerKey
from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ConnectFolder,
    ExplorerActionType,
)
from app.adapters.explorer.explorer import Explorer
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, register
from app.adapters.ssh import keys
from app.adapters.ssh.options import SshOptions
from app.adapters.ssh.reports import (
    REPORTS as SYSTEM_REPORTS,
)
from app.adapters.ssh.reports import (
    SshReports,
)
from app.adapters.ssh.reports import (
    in_section as is_system_report,
)
from app.adapters.ssh.reports import (
    is_section as is_system_section,
)
from app.adapters.ssh.reports import (
    report_for as system_report_for,
)
from app.adapters.ssh.reports import (
    report_node as system_report_node,
)
from app.adapters.ssh.reports import (
    section_node as system_section_node,
)
from app.adapters.ssh.session import SshSession, identity_of, server_key
from app.adapters.ssh.storage import SftpStorage
from app.adapters.ssh.terminal import SshTerminal
from app.adapters.ssh.tunnel import TUNNELS
from app.adapters.terminal import Terminal, TerminalSize
from app.core.translation import N_, say

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
        self._reports = SshReports(self._session)
        super().__init__(SftpStorage(self._session, owner=identity_of(options)))

    def connection_string(self) -> str:
        value = self.draft_connection_string(self._session.options.model_dump(mode="python"))
        if value is None:  # pragma: no cover - validated options always have a host
            raise ValueError(say("The SSH connection has no host"))
        return value

    async def forward(self, host: str, port: int) -> tuple[str, int]:
        """A local address reaching `host:port` from this server (D282)."""
        signing = await self._session.signing_key()
        return await TUNNELS.endpoint(self._session.options, signing, host, port)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if is_system_section(node_id):
            return [system_report_node(report) for report in SYSTEM_REPORTS]
        if is_system_report(node_id):
            if system_report_for(node_id) is None:
                raise NodeNotFound(node_id or "")
            return []
        children = await super().list_children(node_id)
        return [system_section_node(), *children] if node_id is None else children

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        if is_system_section(node_id):
            return [system_section_node()]
        if is_system_report(node_id):
            report = system_report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [system_section_node(), system_report_node(report)]
        return await super().path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if is_system_section(request.node_id) or is_system_report(request.node_id):
            return await self._reports.fetch(request)
        return await super().fetch(request)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if is_system_section(node_id) or is_system_report(node_id):
            return []
        return await super().available(node_id)

    async def action_offers(self, node_id: str | None) -> ActionOffers:
        if is_system_section(node_id) or is_system_report(node_id):
            return ActionOffers(actions=[])
        return await super().action_offers(node_id)

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

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """Read the endpoint fields an SSH URL can state; authentication stays separate."""
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise ValueError(say("That is not an SSH URL")) from None
        if (
            parsed.scheme != "ssh"
            or parsed.hostname is None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query != ""
            or parsed.fragment != ""
        ):
            raise ValueError(say("That is not an SSH URL"))
        return {
            "host": parsed.hostname,
            "port": port or DEFAULT_PORT,
            "username": unquote(parsed.username) if parsed.username is not None else "",
        }

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
            raise ValueError(say("Enter the host first"))
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
    title=N_("SSH"),
    category="files",
    description=N_(
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
