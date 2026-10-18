from collections.abc import Mapping
from typing import Any

from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.content import MysqlContent
from app.adapters.mysql.features import MysqlFeatures
from app.adapters.mysql.fetch import MysqlFetch
from app.adapters.mysql.options import MysqlOptions
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import (
    MysqlSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.mysql.summary import MysqlSummaries
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel
from app.adapters.resources import Pooling
from app.adapters.summary import NodeSummary
from app.core.translation import N_


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_port(value: Any) -> int | None:
    """A form value read as a port, as PostgreSQL's draft reads one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class MysqlAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(self, options: MysqlOptions, pooling: Pooling | None = None) -> None:
        self._session = MysqlSession(options, pooling)
        self._features = MysqlFeatures(self._session)
        self._catalog = MysqlCatalog(self._session)
        self._relation = MysqlRelation(self._session)
        self._fetch = MysqlFetch(self._session, self._relation)
        self._content = MysqlContent(self._session, self._relation)
        self._summaries = MysqlSummaries(self._session, self._relation)

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        """The windows PostgreSQL keeps, for the same kinds of answer."""
        if area == "metadata":
            return 300.0
        return 30.0 if area == "catalog" else 10.0

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        return compose_url(
            host=host,
            port=_as_port(options.get("port")),
            user=_as_text(options.get("user")),
            database=_as_text(options.get("database")),
        )

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        password = options.get("password")
        return compose_url_with_password(
            host=host,
            port=_as_port(options.get("port")),
            user=_as_text(options.get("user")),
            database=_as_text(options.get("database")),
            password=password if isinstance(password, str) else "",
        )

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        return await self._features.source_features()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)


@register(
    name="mysql",
    title=N_("MySQL"),
    category="sql",
    description=N_(
        "MySQL or MariaDB. Browse databases, tables and views, and read rows a "
        "page at a time with sorting and filtering done by the server."
    ),
    options_schema=MysqlOptions,
    adapter_class=MysqlAdapter,
)
def _build(options: MysqlOptions, context: AdapterContext) -> MysqlAdapter:
    return MysqlAdapter(options, context.pooling)
