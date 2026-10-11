"""A Redis server as a source: reaching one, walking it, reading it, writing it.

It began as a connection check and nothing else, which was honest while the
phase it arrived in was about starting containers rather than reading key
spaces. This is the rest: the key space as a catalog grouped by the separator
every convention uses, a key read as whatever it holds, and the four things
people do to keys by hand — write one, take one away, give one a deadline,
take the deadline off.

What is deliberately not here is a query language. Redis has commands, not
statements, and a console that accepted them would be a shell on somebody's
server rather than a way of reading data (D65).

Redis keys, folders and databases can be copied or exported as CSV (D171).

`redis` is imported by this package and by nothing else, the rule `psycopg`
already follows: a driver upgrade has one place to change.
"""

from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.redis.actions import REDIS_ACTION_TYPES
from app.adapters.redis.export import RedisExport
from app.adapters.redis.fetch import RedisFetch
from app.adapters.redis.keyspace import RedisKeyspace, is_database, is_key
from app.adapters.redis.metrics import PRESETS as METRIC_PRESETS
from app.adapters.redis.metrics import RedisMetrics
from app.adapters.redis.model import RedisModel
from app.adapters.redis.options import RedisOptions
from app.adapters.redis.samples import RedisSamples
from app.adapters.redis.search import RedisSearch
from app.adapters.redis.session import RedisSession
from app.adapters.redis.update import RedisUpdate
from app.adapters.redis.url import (
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
)
from app.core.config import settings
from app.core.schemas import get_datetime_utc


class RedisAdapter:
    """Everything this application can do with a Redis server.

    Deliberately thin, the way the PostgreSQL facade is: a capability is a
    module composed here rather than another hundred lines in this class.
    """

    def __init__(self, options: Any) -> None:
        self._options = options
        self._session = RedisSession(options)
        self._keyspace = RedisKeyspace(self._session)
        self._search = RedisSearch(self._session, self._keyspace)
        self._fetch = RedisFetch(self._session, self._keyspace)
        self._model = RedisModel(self._keyspace)
        self._export = RedisExport(self._session, self._keyspace)
        self._update = RedisUpdate(self._session, self._keyspace)
        self._samples = RedisSamples(self._session)
        self._metrics = RedisMetrics(self._session)
        self._actions = ActionSet(
            [action_type(self._session, self._keyspace) for action_type in REDIS_ACTION_TYPES]
        )

    # --- how to reach it, in one line ---------------------------------------

    def connection_string(self) -> str:
        """Where this connects, for a person to copy. Never the password."""
        return compose_url(
            host=self._options.host,
            port=self._options.port,
            database=self._options.database,
        )

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """Asked of the class: parsing is what produces the options."""
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        """The address of a form that does not validate yet.

        The values arrive as the form holds them, so each is checked rather
        than assumed: a port half-typed as "63" is a string, and a field
        nobody has touched is absent.
        """
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        return compose_url(
            host=host,
            port=_as_number(options.get("port")),
            database=_as_number(options.get("database")),
        )

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        """The address a person pastes into redis-cli, password included (D89)."""
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        password = options.get("password")
        return compose_url_with_password(
            host=host,
            port=_as_number(options.get("port")),
            database=_as_number(options.get("database")),
            password=password if isinstance(password, str) else "",
        )

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def metric_samples(self) -> list[MetricSample]:
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def source_features(self) -> SourceFeatures:
        """What this server is. It has no optional features to declare (D120).

        Answered anyway rather than left to 501: "which Redis am I working
        on" is the same question a PostgreSQL connection answers, and a source
        with nothing installed still has a version.
        """
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=await self._session.server_version(),
            features=[],
        )

    async def install_sample_data(self) -> str:
        """Fill an empty key space with one worth walking through."""
        return await self._samples.install_sample_data()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._keyspace.list_children(node_id)

    # --- found from the search field and the tree's filter (D91) -----------

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Cheap while the key space is small, which only a first search tells.

        A scan's cost is the keys it looks at, whatever matches, so a server is
        costly until a search has said how many it holds, and above the count
        a scan does not get through while somebody types (D200).
        """
        if field != "names" or last is None:
            return "costly"
        return "cheap" if last.extent <= settings.SEARCH_CHEAP_KEYS else "costly"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    # --- what a node is, where it lies, and all of it -----------------------

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._model.relation_model(node_id)

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

    # --- writing what a key holds, one element at a time -------------------
    #
    # The ordinary editing contract (D25, D26): the six actions write a whole
    # key, and these change one field, one element, one member of the key
    # somebody is already looking at. What each type admits is the writer's to
    # say, and the page said the same thing before the edit was offered.

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        return await self._update.update_cell(request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await self._update.update_cells(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._update.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._update.insert_rows(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._update.delete_rows(request)

    # --- what may be done to a key -----------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return REDIS_ACTION_TYPES

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        """What this node admits, which is decided by what it is.

        A key takes the three that act on a key; a database and a folder take
        the six that write one. The root takes none: what is there is the list
        of databases, and a key is written in a database rather than on a
        server. Asked of the id rather than of the server, so the kinds are
        told apart
        without a round trip; an id naming a key that has since expired is
        refused by the action itself.
        """
        if is_key(node_id):
            return self._actions.for_kind("key")
        if is_database(node_id):
            return self._actions.for_kind("database")
        if node_id is None:
            return []
        return self._actions.for_kind("directory")


@register(
    name="redis",
    title="Redis",
    # Not a SQL database and not a file store: no statements, no relations and
    # no schema — a key space with an expiry clock. It sat under "SQL
    # Databases" for one commit because that was the only group there was.
    category="keyvalue",
    # Expanded in place rather than walked. A key space is bounded — the scan
    # has a ceiling — and its leaves hold structure worth opening where it is,
    # which is what makes it a tree rather than a series of levels (D91).
    catalog_shape="tree",
    description=(
        "An in-memory key-value server. Switch between its databases, walk a "
        "key space by the colons in the names, read what a key holds, write "
        "one of any type, and set or clear an expiry."
    ),
    options_schema=RedisOptions,
    adapter_class=RedisAdapter,
)
def _build(options: Any, _context: AdapterContext) -> RedisAdapter:
    # No home directory and no pooling: everything this source does is a
    # handful of round trips against a server that answers in microseconds.
    return RedisAdapter(options)


def _as_number(value: Any) -> int | None:
    """A number the form may hold as text, or nothing at all.

    A field never touched is absent, and one half-typed is a string; both are
    left out of the address rather than stopping it, because the point of a
    draft address is to show as much of it as there is.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
