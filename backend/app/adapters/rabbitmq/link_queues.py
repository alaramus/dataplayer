"""An exchange read on by a pipeline's link through a queue of the link's own
(D337).

The queue is named by the link's reader and made ready at the start of every
step, never when the pipeline is saved: saving never talks to a broker. It
goes by itself once nobody reads it for a week, and keeps at most a million
messages, dropping the oldest, so a pipeline nobody runs does not fill the
broker's disk.
"""

from typing import Any

from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.rabbitmq.catalog import (
    Named,
    exchange_path,
    leaf_id,
    read_exchange,
)
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.reading_on import ReadingTerms
from app.core.translation import say

WEEK_MS = 7 * 24 * 60 * 60 * 1000
MAX_LENGTH = 1_000_000

# What the link's queue is declared with; a queue of that name with anything
# else is somebody's, and is refused rather than declared again.
ARGUMENTS: dict[str, Any] = {
    "x-queue-type": "classic",
    "x-expires": WEEK_MS,
    "x-max-length": MAX_LENGTH,
    "x-overflow": "drop-head",
}

# An exchange type's key when the link names none: everything a topic routes,
# and the empty key of a direct exchange. A fanout and a headers exchange
# take no key.
_DEFAULT_KEYS = {"topic": "#", "direct": ""}
_KEYLESS = {"fanout", "headers"}


def reads_through(named: Named) -> bool:
    """An exchange with a name: the default exchange takes no bindings."""
    return named.prefix == "exchange" and bool(named.name)


def terms_for(named: Named, exchange_type: str | None) -> ReadingTerms:
    """What the link's form asks of a queue, a stream or an exchange."""
    if named.prefix == "queue":
        return ReadingTerms(
            note=say(
                "Other consumers of this queue share its messages with the link; "
                "read its exchange to get all of them"
            )
        )
    if not reads_through(named):
        return ReadingTerms()
    note = say(
        "The link reads through a queue of its own bound to this exchange, "
        "and gets what the exchange routes from its first run on"
    )
    if exchange_type in _KEYLESS:
        return ReadingTerms(note=note)
    return ReadingTerms(
        asks_binding_key=True,
        default_binding_key=_DEFAULT_KEYS.get(exchange_type or "", ""),
        note=note,
    )


def wanted_binding(exchange_type: str, key: str | None) -> tuple[str, dict[str, Any]]:
    """The one binding the link's queue has to the exchange."""
    if exchange_type == "headers":
        # No headers and all of them matching: every message.
        return "", {"x-match": "all"}
    if exchange_type == "fanout":
        return "", {}
    return (key if key is not None else _DEFAULT_KEYS.get(exchange_type, "")), {}


def _same_settings(queue: dict[str, Any]) -> bool:
    arguments = queue.get("arguments") or {}
    return (
        bool(queue.get("durable"))
        and not queue.get("auto_delete")
        and str(queue.get("type") or "classic") == "classic"
        and all(
            arguments.get(name) == value
            for name, value in ARGUMENTS.items()
            if name != "x-queue-type"
        )
    )


async def prepare(
    session: RabbitmqSession, named: Named, queue: str, key: str | None
) -> bool:
    """The link's queue declared and bound by the key it carries now; True
    when it was made just now."""
    assert named.name is not None
    vhost = segment(named.vhost)
    exchange = await read_exchange(session, named.vhost, named.name)
    exchange_type = str(exchange.get("type") or "direct")
    made = False
    try:
        found = await session.api(
            f"/queues/{vhost}/{segment(queue)}",
            node_id=leaf_id("queue", named.vhost, queue),
        )
    except NodeNotFound:
        found = None
    if found is None:
        try:
            await session.change(
                "PUT",
                f"/queues/{vhost}/{segment(queue)}",
                {"durable": True, "auto_delete": False, "arguments": ARGUMENTS},
            )
        except AdapterError as failure:
            raise _refused(failure, queue, named.name, making=True) from None
        made = True
    elif not isinstance(found, dict) or not _same_settings(found):
        raise AdapterError(
            "config",
            say(
                "A queue named {name} is there already, with other settings; "
                "the link does not change it",
                name=queue,
            ),
        )
    await _bind(session, named, queue, wanted_binding(exchange_type, key))
    return made


async def _bind(
    session: RabbitmqSession,
    named: Named,
    queue: str,
    wanted: tuple[str, dict[str, Any]],
) -> None:
    """The wanted binding made, and every other from that exchange to that
    queue removed, so a key changed needs nothing but a run."""
    assert named.name is not None
    path = (
        f"/bindings/{segment(named.vhost)}/e/{exchange_path(named.name)}"
        f"/q/{segment(queue)}"
    )
    key, arguments = wanted
    try:
        bound = await session.api(path)
        present = False
        for one in bound if isinstance(bound, list) else []:
            if (
                str(one.get("routing_key", "")) == key
                and (one.get("arguments") or {}) == arguments
            ):
                present = True
                continue
            await session.change(
                "DELETE", f"{path}/{segment(str(one.get('properties_key', '')))}"
            )
        if not present:
            await session.change(
                "POST", path, {"routing_key": key, "arguments": arguments}
            )
    except AdapterError as failure:
        raise _refused(failure, queue, named.name, making=False) from None


def _refused(
    failure: AdapterError, queue: str, exchange: str, *, making: bool
) -> AdapterError:
    """A permission the account lacks, said by which (D337)."""
    if failure.error_kind != "auth":
        return failure
    if making:
        return AdapterError(
            "auth",
            say(
                "This connection may not make the link's queue {name}: it needs "
                "configure and read on it",
                name=queue,
            ),
        )
    return AdapterError(
        "auth",
        say(
            "This connection may not bind the link's queue {name} to {exchange}: "
            "it needs write on the queue and read on the exchange",
            name=queue,
            exchange=exchange,
        ),
    )
