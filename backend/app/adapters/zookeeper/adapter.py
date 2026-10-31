"""A ZooKeeper server as a source: its znode tree, each znode's data, stat and ACL.

`kazoo` is imported by this package and by nothing else, the rule `psycopg`
already follows: a driver upgrade has one place to change (D297).
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.content import (
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    UpdateContentRequest,
)
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, register
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import TunnelAccess
from app.adapters.zookeeper.actions import ZOOKEEPER_ACTION_TYPES, build_actions
from app.adapters.zookeeper.children import ZookeeperChildren
from app.adapters.zookeeper.console import console_program
from app.adapters.zookeeper.data import ZookeeperData
from app.adapters.zookeeper.options import ZookeeperOptions
from app.adapters.zookeeper.session import (
    ZookeeperSession,
    compose_url,
    options_from_url,
)
from app.adapters.zookeeper.summary import ZookeeperSummaries
from app.adapters.zookeeper.znodes import (
    ancestors_of,
    checked_path,
    read_level,
    read_node,
)
from app.core.schemas import get_datetime_utc
from app.core.translation import N_


class ZookeeperAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    def __init__(
        self, options: ZookeeperOptions, tunnels: TunnelAccess | None = None
    ) -> None:
        self._session = ZookeeperSession(options, tunnels)
        self._children = ZookeeperChildren(self._session)
        self._data = ZookeeperData(self._session)
        self._summaries = ZookeeperSummaries(self._session)
        self._actions = ActionSet(build_actions(self._session))

    # --- how to reach it, in one line ---------------------------------------

    def connection_string(self) -> str:
        options = self._session.options
        return compose_url(host=options.host, port=options.port, chroot=options.chroot)

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        port = options.get("port")
        chroot = options.get("chroot")
        return compose_url(
            host=host,
            port=port if isinstance(port, int) and not isinstance(port, bool) else None,
            chroot=chroot if isinstance(chroot, str) and chroot.startswith("/") else "",
        )

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        version = await self._session.server_version()
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=None if version is None else f"ZooKeeper {version}",
            features=[],
        )

    # --- the tree (D298) ------------------------------------------------------

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        path = "/" if node_id is None else checked_path(node_id)
        try:
            return list(
                await self._session.run(lambda client: read_level(client, path), path)
            )
        except NodeNotFound as gone:
            # A level that is not there is a node id the source cannot reach,
            # by the catalog's contract, rather than a 404.
            raise ValueError(str(gone)) from None

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        path = checked_path(node_id)
        if path == "/":
            raise NodeNotFound(node_id)
        return list(
            await self._session.run(
                lambda client: [read_node(client, one) for one in ancestors_of(path)],
                path,
            )
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._children.fetch(request)

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    # --- a znode's data -------------------------------------------------------

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._data.read_content(request)

    async def read_editor_content(self, request: EditorContentRequest) -> EditorContent:
        return await self._data.read_editor_content(request)

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        """The whole data, if the znode is still at the version read (D298)."""
        return await self._data.update_content(request)

    # --- what may be done to znodes (D300) ------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return ZOOKEEPER_ACTION_TYPES

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        """Every one, wherever: the tree's level is its top, and the ones that
        act on a znode are switched on by what is selected (D300)."""
        del node_id
        return list(self._actions)

    async def console_program(self) -> ConsoleProgram:
        """zkCli, connected to this server and root path, in a container (D299)."""
        return console_program(self._session.options)


@register(
    name="zookeeper",
    title=N_("ZooKeeper"),
    # A tree of small values rather than a database: no statements, no
    # relations — a hierarchical key-value store with versions.
    category="keyvalue",
    # Expanded in place, as Redis's key space is: a path is already a tree.
    catalog_shape="tree",
    description=N_(
        "A ZooKeeper server. Walk its znode tree, read a znode's data as text "
        "or as JSON with its stat and ACL, edit the data against the version "
        "read, make and delete znodes and change their ACLs, page through a znode's children as rows, and work in zkCli in a "
        "terminal."
    ),
    options_schema=ZookeeperOptions,
    adapter_class=ZookeeperAdapter,
)
def _build(options: ZookeeperOptions, context: AdapterContext) -> ZookeeperAdapter:
    return ZookeeperAdapter(options, context.tunnels)
