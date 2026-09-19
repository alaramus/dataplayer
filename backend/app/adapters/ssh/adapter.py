"""An SSH server as a source: its folders over SFTP, and the five file actions.

Everything goes over SFTP, and nothing runs a command on the server. The
terminal is a later slice of its own, and until then no string of a form's
ever reaches a shell (D144).

`asyncssh` is imported by this package and by nothing else, the rule `psycopg`
follows: a library upgrade has one place to change.
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.actions import Action, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.content import (
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    UpdateContentRequest,
)
from app.adapters.credentials import ServerKey
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.ssh import keys
from app.adapters.ssh.actions import SSH_ACTION_TYPES, SshActions
from app.adapters.ssh.catalog import SshCatalog
from app.adapters.ssh.content import SshContent
from app.adapters.ssh.options import SshOptions
from app.adapters.ssh.session import SshSession, server_key

DEFAULT_PORT = 22


class SshAdapter:
    """Everything this application can do with an SSH server, composed here."""

    def __init__(self, options: SshOptions, context: AdapterContext) -> None:
        self._session = SshSession(options, context)
        self._catalog = SshCatalog(self._session)
        self._content = SshContent(self._session)
        self._actions = SshActions(self._session)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)

    async def read_editor_content(self, request: EditorContentRequest) -> EditorContent:
        return await self._content.read_editor_content(request)

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        return await self._content.update_content(request)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return SSH_ACTION_TYPES

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
        "A server reached over SSH. Browse its folders from where you choose, "
        "read and edit its text files, upload, download, rename and delete. Signs in "
        "with a password or one of your SSH keys, and only to the server whose "
        "key you confirmed."
    ),
    options_schema=SshOptions,
    adapter_class=SshAdapter,
)
def _build(options: SshOptions, context: AdapterContext) -> SshAdapter:
    return SshAdapter(options, context)
