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

`redis` is imported by this package and by nothing else, the rule `psycopg`
already follows: a driver upgrade has one place to change.
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.redis.actions import REDIS_ACTION_TYPES
from app.adapters.redis.fetch import RedisFetch
from app.adapters.redis.keyspace import RedisKeyspace, is_key
from app.adapters.redis.options import RedisOptions
from app.adapters.redis.samples import RedisSamples
from app.adapters.redis.session import RedisSession
from app.adapters.redis.url import (
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.registry import AdapterContext, register


class RedisAdapter:
    """Everything this application can do with a Redis server.

    Deliberately thin, the way the PostgreSQL facade is: a capability is a
    module composed here rather than another hundred lines in this class.
    """

    def __init__(self, options: Any) -> None:
        self._options = options
        self._session = RedisSession(options)
        self._keyspace = RedisKeyspace(self._session)
        self._fetch = RedisFetch(self._session, self._keyspace)
        self._samples = RedisSamples(self._session)
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

    async def install_sample_data(self) -> str:
        """Fill an empty key space with one worth walking through."""
        return await self._samples.install_sample_data()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._keyspace.list_children(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    # --- what may be done to a key -----------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return REDIS_ACTION_TYPES

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        """What this node admits, which is decided by what it is.

        A key takes the three that act on a key; a folder and the root take
        the one that makes one. Asked of the id rather than of the server: the
        two kinds of id are told apart without a round trip, and an id naming
        a key that has since expired is refused by the action itself.
        """
        if is_key(node_id):
            return self._actions.for_kind("key")
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
        "An in-memory key-value server. Walk its key space by the colons in "
        "the names, read what a key holds, write one, and set or clear an "
        "expiry."
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
