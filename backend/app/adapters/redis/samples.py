"""Something worth looking at, put into an empty Redis.

A Redis this application starts is empty, and an empty key space demonstrates
nothing: the tree has no branches, no key has a type to show and the expiry
column is blank. So a server started automatically is filled — with a key
space that looks like one somebody has been using.

What is in it is chosen to exercise the source rather than to tell a story:
every type Redis has, several depths of naming, keys with an expiry and keys
without, values that are text and values that are JSON, and enough of them
that paging and the scan are doing something. It is written out rather than
generated randomly, so two demonstrations look the same and a screenshot keeps
meaning what it meant.
"""

import json
from collections.abc import Iterator
from typing import Any

from app.adapters.redis.session import RedisSession

# How long the keys that have an expiry keep. Different values on purpose:
# a column where every row says the same number says nothing about the column.
TTLS = (300, 900, 3600, 86_400)

# The people the sample data is about. Enough of them that the tree has
# branches worth expanding, few enough that they can be read.
PEOPLE = (
    ("ada", "Ada Lovelace", "analyst"),
    ("alan", "Alan Turing", "admin"),
    ("grace", "Grace Hopper", "admin"),
    ("edsger", "Edsger Dijkstra", "analyst"),
    ("barbara", "Barbara Liskov", "viewer"),
    ("john", "John von Neumann", "viewer"),
    ("donald", "Donald Knuth", "analyst"),
    ("frances", "Frances Allen", "admin"),
)

PRODUCTS = (
    ("kettle", "Electric kettle", 2499),
    ("lamp", "Desk lamp", 1899),
    ("chair", "Office chair", 12900),
    ("mug", "Enamel mug", 799),
    ("shelf", "Wall shelf", 4500),
    ("rug", "Floor rug", 8900),
)

REGIONS = ("north", "south", "east", "west")

# The days the metrics are for. Fixed dates rather than "today minus n", so a
# demonstration made twice is the same demonstration.
DAYS = ("2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03")


class RedisSamples:
    """Filling a Redis server with a key space worth walking.

    Not an action and not a route: it is offered only where this server has
    just started the Redis itself (D80). Writing into somebody else's server
    is what the four key actions are for, one key at a time.
    """

    def __init__(self, session: RedisSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Write the keys, and say what is now there.

        One pipeline. A hundred and more round trips against a server this
        application has just started is a second of somebody watching a
        progress step for no reason.
        """
        async with self._session.connection() as client:
            pipe = client.pipeline(transaction=False)
            # What was written before is taken away first, so filling a server
            # twice leaves what filling it once does. Only these keys: this
            # writes a demonstration into a server, not over one — and the
            # stream is why it matters at all, since its entries carry ids of
            # their own and a second `xadd` of the same id is refused.
            pipe.delete(*sorted(key_names()))
            for command, arguments in _commands():
                getattr(pipe, command)(*arguments)
            await pipe.execute()
        return f"{len(key_names())} keys in {len(_NAMESPACES)} namespaces"


# Which commands make a key rather than change one that already exists. Named
# rather than guessed: eight `xadd` calls to one stream are one key, and an
# `expire` beside a `set` is none of its own.
_WRITES_A_KEY = frozenset({"set", "hset", "rpush", "sadd", "zadd", "xadd"})


def key_names() -> set[str]:
    """Every key the sample data writes, without writing any of them.

    The first argument of a command is the key it is about, which is true of
    every command used here. Counting this way rather than counting commands
    is the difference between "110 keys" and a number inflated by the eight
    entries of one stream.
    """
    return {
        str(arguments[0])
        for command, arguments in _commands()
        if command in _WRITES_A_KEY
    }

_NAMESPACES = (
    "session",
    "cache",
    "queue",
    "metrics",
    "feature",
    "rate",
    "catalog",
    "events",
)


def _commands() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Every command the sample data is made of, in order.

    A generator of (command, arguments) rather than a list of statements, so
    that what is written can be counted and read without running it.
    """
    yield from _sessions()
    yield from _cached_people()
    yield from _queues()
    yield from _metrics()
    yield from _flags()
    yield from _rate_limits()
    yield from _catalog()
    yield from _events()


def _hash(name: str, fields: dict[str, str]) -> Iterator[tuple[str, tuple[Any, ...]]]:
    """One `hset` per field rather than one carrying a mapping.

    redis-py takes a whole hash as `mapping=`, and a dictionary handed to it
    positionally is read as a field name — which is a runtime failure inside a
    pipeline rather than anything a type could catch. Every command here has
    the same shape, and a pipeline does not care that there are four of them
    instead of one.
    """
    for field, value in fields.items():
        yield "hset", (name, field, value)


def _sessions() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Strings with an expiry, three levels deep: the commonest Redis shape."""
    for index, (handle, name, role) in enumerate(PEOPLE):
        token = f"session:{1000 + index}:token"
        yield "set", (token, f"tok_{handle}_{7000 + index * 13}")
        yield "expire", (token, TTLS[index % len(TTLS)])
        yield "set", (f"session:{1000 + index}:user", handle)
        yield from _hash(
            f"session:{1000 + index}:meta",
            {"role": role, "name": name, "since": DAYS[index % len(DAYS)]},
        )


def _cached_people() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Hashes and JSON strings under one prefix: two ways to cache a record."""
    for index, (handle, name, role) in enumerate(PEOPLE):
        yield from _hash(
            f"cache:user:{handle}",
            {
                "name": name,
                "role": role,
                "logins": str(index * 7 + 3),
                "active": "1" if role != "viewer" else "0",
            },
        )
        document = f"cache:profile:{handle}"
        yield "set", (
            document,
            json.dumps(
                {"handle": handle, "name": name, "role": role, "tags": [role, "demo"]}
            ),
        )
        yield "expire", (document, TTLS[(index + 1) % len(TTLS)])


def _queues() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Lists, which are the one type that pages in the server."""
    yield "rpush", (
        "queue:jobs:pending",
        *[f"job-{2000 + number}" for number in range(40)],
    )
    yield "rpush", ("queue:jobs:failed", "job-1997", "job-1998")
    yield "rpush", (
        "queue:mail:outbox",
        *[f"mail to {handle}@example.com" for handle, _, _ in PEOPLE],
    )


def _metrics() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Counters, sets and sorted sets: what a day of traffic looks like."""
    for day_index, day in enumerate(DAYS):
        yield "set", (f"metrics:visits:{day}", str(1200 + day_index * 317))
        yield "sadd", (
            f"metrics:active:{day}",
            *[handle for handle, _, _ in PEOPLE[: 3 + day_index % 4]],
        )
        yield "zadd", (
            f"metrics:top:{day}",
            {
                name: float(100 - index * 7 - day_index)
                for index, (_, name, _) in enumerate(PRODUCTS)
            },
        )
    yield "zadd", (
        "metrics:leaderboard",
        {name: float(500 - index * 43) for index, (_, name, _) in enumerate(PEOPLE)},
    )


def _flags() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Strings at one level: keys with no colon in them at all."""
    for index, flag in enumerate(
        ("dark-mode", "new-editor", "beta-charts", "slow-log", "read-only")
    ):
        yield "set", (f"feature:{flag}", "on" if index % 2 == 0 else "off")
    yield "set", ("maintenance", "off")
    yield "set", ("greeting", "Hello from a Redis this server started for you")


def _rate_limits() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """Short-lived counters, so the expiry column has something in it."""
    for index, (handle, _, _) in enumerate(PEOPLE):
        for region in REGIONS[: 1 + index % 3]:
            key = f"rate:{region}:{handle}"
            yield "set", (key, str(index * 3 + 1))
            yield "expire", (key, TTLS[index % len(TTLS)])


def _catalog() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """A deeper tree: products by region, each a hash."""
    for region in REGIONS:
        for handle, title, price in PRODUCTS:
            yield from _hash(
                f"catalog:{region}:{handle}",
                {
                    "title": title,
                    "price": str(price),
                    "currency": "EUR",
                    "region": region,
                },
            )
        yield "sadd", (
            f"catalog:{region}:in-stock",
            *[handle for handle, _, _ in PRODUCTS[:4]],
        )


def _events() -> Iterator[tuple[str, tuple[Any, ...]]]:
    """A stream, which is the type nothing else here covers."""
    for index, (handle, _, role) in enumerate(PEOPLE):
        yield "xadd", (
            "events:audit",
            {"who": handle, "what": "signed in", "role": role},
            f"{1788000000000 + index * 1000}-0",
        )
