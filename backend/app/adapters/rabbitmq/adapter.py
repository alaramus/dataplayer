"""A RabbitMQ broker as a source: its virtual hosts, queues, streams and
exchanges, a stream's messages and the bindings between them.

`aio_pika` and `aiormq` are imported by this package and by nothing else,
the rule `psycopg` already follows (D325).
"""

from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.rabbitmq.actions import (
    RABBITMQ_ACTION_TYPES,
    build_actions,
    offered,
)
from app.adapters.rabbitmq.bindings import RabbitmqBindings
from app.adapters.rabbitmq.catalog import (
    FOLDERS,
    exchange_node,
    folder_node,
    folders_of,
    parse,
    queue_node,
    read_exchange,
    read_exchanges,
    read_queue,
    read_queues,
    read_vhosts,
    vhost_node,
)
from app.adapters.rabbitmq.console import console_program
from app.adapters.rabbitmq.metrics import PRESETS as METRIC_PRESETS
from app.adapters.rabbitmq.metrics import RabbitmqMetrics
from app.adapters.rabbitmq.options import RabbitmqOptions
from app.adapters.rabbitmq.peeks import RabbitmqPeeks
from app.adapters.rabbitmq.reports import (
    REPORTS,
    RabbitmqReports,
    in_section,
    is_section,
    report_for,
    report_node,
    section_node,
)
from app.adapters.rabbitmq.samples import RabbitmqSamples
from app.adapters.rabbitmq.search import RabbitmqSearch
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.rabbitmq.streams import RabbitmqStreams
from app.adapters.rabbitmq.summaries import node_summary
from app.adapters.rabbitmq.writes import RabbitmqWrites
from app.adapters.registry import AdapterContext, register
from app.adapters.resources import Pooling
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.adapters.update import (
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
)
from app.core.translation import N_, say

_SCHEMES = {"amqp": False, "amqps": True}


class RabbitmqAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    def __init__(
        self, options: RabbitmqOptions, pooling: Pooling | None = None
    ) -> None:
        self._session = RabbitmqSession(options)
        self._bindings = RabbitmqBindings(self._session)
        self._streams = RabbitmqStreams(self._session)
        self._writes = RabbitmqWrites(self._session)
        self._peeks = RabbitmqPeeks(self._session, pooling)
        self._actions = ActionSet(build_actions(self._session, self._peeks))
        self._reports = RabbitmqReports(self._session)
        self._metrics = RabbitmqMetrics(self._session)
        self._search = RabbitmqSearch(self._session)
        self._samples = RabbitmqSamples(self._session)

    # --- how to reach it, in one line --------------------------------------------

    def connection_string(self) -> str:
        """The AMQP address, as every client takes it; never a password."""
        options = self._session.options
        return _compose(
            options.host, options.port, options.user, options.vhost, options.tls
        )

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """`amqp://user:password@host:port/vhost`, `amqps://` for TLS.

        The path is the virtual host, `%2F` for `/`; no path is every virtual
        host the user may see.
        """
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError:
            raise ValueError(
                say("The connection string names no usable port")
            ) from None
        scheme = parts.scheme.lower()
        if scheme not in _SCHEMES:
            raise ValueError(say("That is not an AMQP connection string"))
        if not parts.hostname:
            raise ValueError(say("The connection string names no host"))
        tls = _SCHEMES[scheme]
        options: dict[str, Any] = {
            "host": unquote(parts.hostname),
            "port": port or (5671 if tls else 5672),
            "tls": tls,
        }
        if parts.username:
            options["user"] = unquote(parts.username)
        if parts.password:
            options["password"] = unquote(parts.password)
        path = parts.path[1:] if parts.path.startswith("/") else parts.path
        if path:
            options["vhost"] = unquote(path)
        return options

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        port = options.get("port")
        user = options.get("user")
        vhost = options.get("vhost")
        tls = options.get("tls") is True
        return _compose(
            host,
            port if isinstance(port, int) else (5671 if tls else 5672),
            user if isinstance(user, str) else "",
            vhost if isinstance(vhost, str) else "",
            tls,
        )

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    # --- the catalog (D326) ----------------------------------------------------

    async def _vhosts(self) -> list[str]:
        """The virtual hosts the top shows, or one whose contents it shows."""
        if self._session.options.vhost:
            return [self._session.options.vhost]
        return await read_vhosts(self._session)

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            # The broker's own section first, as Kafka's cluster is (D331).
            vhosts = await self._vhosts()
            if len(vhosts) == 1:
                return [section_node(), *folders_of(vhosts[0])]
            return [section_node(), *(vhost_node(vhost) for vhost in vhosts)]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            if report_for(node_id) is None:
                raise NodeNotFound(node_id)
            return []
        named = parse(node_id)
        self._own(named.vhost, node_id)
        if named.prefix == "vhost":
            return folders_of(named.vhost)
        if named.prefix == "queues":
            return await read_queues(self._session, named.vhost, streams=False)
        if named.prefix == "streams":
            return await read_queues(self._session, named.vhost, streams=True)
        if named.prefix == "exchanges":
            return await read_exchanges(self._session, named.vhost)
        # A queue, a stream and an exchange hold nothing.
        return []

    def _own(self, vhost: str, node_id: str) -> None:
        """A node of another virtual host than the connection names is none of
        its own."""
        named = self._session.options.vhost
        if named and vhost != named:
            raise NodeNotFound(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        named = parse(node_id)
        self._own(named.vhost, node_id)
        vhosts = await self._vhosts()
        if named.vhost not in vhosts:
            raise NodeNotFound(node_id)
        top: list[CatalogNode] = [] if len(vhosts) == 1 else [vhost_node(named.vhost)]
        if named.prefix == "vhost":
            if not top:
                raise NodeNotFound(node_id)
            return top
        for folder in FOLDERS:
            if named.prefix == folder:
                return [*top, folder_node(folder, named.vhost)]
        if named.name is None:
            raise NodeNotFound(node_id)
        if named.prefix == "peek":
            # A look hangs under the queue it was taken of, listed nowhere.
            snapshot = await self._peeks.snapshot(node_id)
            queue = await read_queue(
                self._session, named.vhost, named.name, stream=False
            )
            return [
                *top,
                folder_node("queues", named.vhost),
                queue_node(named.vhost, queue),
                self._peeks.node(node_id, snapshot),
            ]
        if named.prefix == "exchange":
            described = await read_exchange(self._session, named.vhost, named.name)
            return [
                *top,
                folder_node("exchanges", named.vhost),
                exchange_node(named.vhost, described),
            ]
        stream = named.prefix == "stream"
        described = await read_queue(
            self._session, named.vhost, named.name, stream=stream
        )
        return [
            *top,
            folder_node("streams" if stream else "queues", named.vhost),
            queue_node(named.vhost, described),
        ]

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if in_section(request.node_id):
            return await self._reports.fetch(request)
        named = parse(request.node_id)
        self._own(named.vhost, request.node_id)
        if named.prefix == "stream":
            return await self._streams.fetch(request)
        if named.prefix == "peek":
            return await self._peeks.fetch(request)
        if named.prefix in {"queue", "exchange"}:
            return await self._bindings.fetch(request)
        raise ValueError(say("A level is opened by its contents, not as rows"))

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        if in_section(request.node_id):
            return self._reports.export_rows(request)
        named = parse(request.node_id)
        self._own(named.vhost, request.node_id)
        if named.prefix == "stream":
            return self._streams.export_rows(request)
        if named.prefix in {"queue", "exchange"}:
            return self._bindings.export_rows(request)
        raise ValueError(say("A level is opened by its contents, not as rows"))

    async def node_summary(self, node_id: str) -> NodeSummary:
        named = parse(node_id)
        self._own(named.vhost, node_id)
        if named.prefix not in {"queue", "stream", "exchange"}:
            raise ValueError(say("Only a queue, a stream or an exchange has details"))
        return await node_summary(self._session, node_id)

    # --- the broker measured, and names found (D331) ---------------------------------

    async def install_sample_data(self) -> str:
        """The lab, for a broker started here (D332)."""
        return await self._samples.install_sample_data()

    async def metric_samples(self) -> list[MetricSample]:
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are a few requests, whatever the broker holds; nothing else is
        searched."""
        del last
        return "cheap" if field == "names" else "costly"

    # --- messages sent and things changed (D329, D330) ------------------------------

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        self._own(parse(request.node_id).vhost, request.node_id)
        return await self._writes.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        self._own(parse(request.node_id).vhost, request.node_id)
        return await self._writes.insert_rows(request)

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return RABBITMQ_ACTION_TYPES

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return [self._actions.get(name) for name in offered(node_id)]

    async def console_program(self) -> ConsoleProgram:
        """rabbitmqadmin, set up for this connection, in a container (D328)."""
        return console_program(self._session.options)


def _compose(host: str, port: int, user: str, vhost: str, tls: bool) -> str:
    scheme = "amqps" if tls else "amqp"
    who = f"{quote(user, safe='')}@" if user else ""
    where = f"/{quote(vhost, safe='')}" if vhost else ""
    return f"{scheme}://{who}{host}:{port}{where}"


@register(
    name="rabbitmq",
    title=N_("RabbitMQ"),
    # A broker of queues and streams; neither a database nor a store of
    # values under keys.
    category="stream",
    description=N_(
        "A RabbitMQ broker. List its virtual hosts, queues, streams and "
        "exchanges, see how many messages wait in a queue and who consumes "
        "them, see what is bound to what, and read a stream's messages as rows, "
        "newest first, with JSON bodies laid out in columns, and work with "
        "rabbitmqadmin in a terminal."
    ),
    options_schema=RabbitmqOptions,
    adapter_class=RabbitmqAdapter,
)
def _build(options: RabbitmqOptions, context: AdapterContext) -> RabbitmqAdapter:
    # The pooling keeps what Peek took (D330); a draft has none.
    return RabbitmqAdapter(options, context.pooling)
