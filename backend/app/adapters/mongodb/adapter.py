from collections.abc import Mapping
from typing import Any

from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.mongodb.catalog import MongodbCatalog
from app.adapters.mongodb.console import console_program
from app.adapters.mongodb.content import MongodbContent
from app.adapters.mongodb.fetch import MongodbFetch
from app.adapters.mongodb.options import MongodbOptions
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.session import (
    MongodbSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.mongodb.summary import MongodbSummaries
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.resources import Pooling
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import TunnelAccess
from app.core.schemas import get_datetime_utc
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


def _address(options: Mapping[str, Any]) -> dict[str, Any] | None:
    host = options.get("host")
    if not isinstance(host, str) or host == "":
        return None
    named = options.get("auth_method") == "user_password"
    return {
        "host": host,
        "port": _as_port(options.get("port")),
        "user": _as_text(options.get("user")) if named else "",
        "database": _as_text(options.get("database")),
        "auth_source": _as_text(options.get("auth_source")) if named else "",
        "tls": options.get("tls") is True,
    }


class MongodbAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(
        self,
        options: MongodbOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
    ) -> None:
        self._session = MongodbSession(options, pooling, tunnels)
        self._catalog = MongodbCatalog(self._session)
        self._relation = MongodbRelation(self._session)
        self._fetch = MongodbFetch(self._session, self._relation)
        self._content = MongodbContent(self._relation)
        self._summaries = MongodbSummaries(self._relation)

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        """The windows PostgreSQL keeps, for the same kinds of answer."""
        if area in {"metadata", "relation"}:
            return 300.0
        return 30.0 if area == "catalog" else 10.0

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        address = _address(options)
        return None if address is None else compose_url(**address)

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        address = _address(options)
        if address is None:
            return None
        password = options.get("password") if address["user"] else ""
        return compose_url_with_password(
            **address, password=password if isinstance(password, str) else ""
        )

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        try:
            version: str | None = f"MongoDB {(await self._session.profile()).text}"
        except AdapterError:
            version = None
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=version, features=[]
        )

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)

    async def relation_models_for_nodes(
        self, request: RelationModelsRequest
    ) -> list[RelationModel]:
        return await self._relation.relation_models_for_nodes(request.node_ids)

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)

    async def console_program(self) -> ConsoleProgram:
        """mongosh, signed in as this connection, in a container (D286)."""
        return console_program(self._session)


@register(
    name="mongodb",
    title=N_("MongoDB"),
    category="document",
    description=N_(
        "A MongoDB server. Browse databases, collections and views, and read "
        "documents a page at a time as rows, their fields found from the "
        "documents themselves, with sorting and filtering done by the server, "
        "and work in mongosh in a terminal."
    ),
    options_schema=MongodbOptions,
    adapter_class=MongodbAdapter,
)
def _build(options: MongodbOptions, context: AdapterContext) -> MongodbAdapter:
    return MongodbAdapter(options, context.pooling, context.tunnels)
