"""What a RabbitMQ connection can be asked to do (D329, D330).

On the Queues, Streams and Exchanges levels: make one. On a queue, a stream or
an exchange: delete it, bind or unbind it; publish to a queue or an exchange;
purge a queue or peek into it. Every change goes through the management API;
a message published goes over AMQP, mandatory, so one routed to no queue is
said.
"""

import json
import re
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    FieldChoice,
    FieldHints,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.layout import layout
from app.adapters.message_cells import bytes_of
from app.adapters.rabbitmq.catalog import (
    Named,
    exchange_path,
    exchange_title,
    folder_id,
    is_system_exchange,
    leaf_id,
    parse,
    read_exchange,
    read_queue,
)
from app.adapters.rabbitmq.peeks import PEEK_CEILING, RabbitmqPeeks
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.rabbitmq.writes import Outgoing, publish
from app.core.translation import N_, say

# A stream's age, as RabbitMQ writes it: a number and Y, M, D, h, m or s.
_AGE = re.compile(r"[1-9][0-9]{0,8}[YMDhms]")
# An argument's name, as RabbitMQ spells its own: `x-max-length`.
_ARGUMENT = re.compile(r"[A-Za-z0-9_.-]{1,255}")

# How many queues and exchanges a form offers to bind to.
CHOICES = 500

EXCHANGE_TYPES = ("direct", "topic", "fanout", "headers")


def parse_arguments(text: str) -> dict[str, Any]:
    """`name=value` per line; a value is JSON when it reads as JSON, text
    otherwise, so `x-max-length=1000` is a number (D330)."""
    found: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        name, equals, value = line.partition("=")
        name = name.strip()
        if equals == "" or _ARGUMENT.fullmatch(name) is None:
            raise ValueError(
                say('Write each argument as name=value, not "{line}"', line=line)
            )
        if name in found:
            raise ValueError(say("{name} is set twice", name=name))
        value = value.strip()
        try:
            found[name] = json.loads(value)
        except ValueError:
            found[name] = value
    return found


def _checked_name(name: str) -> str:
    """RabbitMQ's own rule: up to 255 bytes, and `amq.` is the broker's."""
    if name.strip() != name or name == "":
        raise ValueError(say("A name has no spaces at its ends and is not empty"))
    if len(name.encode("utf-8")) > 255:
        raise ValueError(say("A name is at most 255 bytes"))
    if name.startswith("amq."):
        raise ValueError(say("A name that starts with amq. is the broker's own"))
    return name


def _checked_arguments(text: str) -> str:
    parse_arguments(text)
    return text


# --- the forms -----------------------------------------------------------------


class NewQueueParams(BaseModel):
    name: str = Field(
        title=N_("Name"), examples=["billing"], json_schema_extra=layout()
    )
    queue_type: Literal["classic", "quorum"] = Field(
        default="classic",
        title=N_("Type"),
        description=N_("Quorum is replicated and always durable"),
        json_schema_extra=layout(),
    )
    durable: bool = Field(
        default=True,
        title=N_("Durable"),
        description=N_("Survives the broker's restart"),
        json_schema_extra=layout(),
    )
    arguments: str = Field(
        default="",
        title=N_("Arguments"),
        description=N_("One name=value per line, such as x-max-length=10000"),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    _name = field_validator("name")(_checked_name)
    _arguments = field_validator("arguments")(_checked_arguments)


class NewStreamParams(BaseModel):
    name: str = Field(
        title=N_("Name"), examples=["orders.log"], json_schema_extra=layout()
    )
    max_age: str = Field(
        default="",
        title=N_("Kept for"),
        description=N_("Such as 7D, 12h or 30m; empty to keep by size alone"),
        max_length=16,
        json_schema_extra=layout(),
    )
    max_bytes: int | None = Field(
        default=None,
        ge=1,
        title=N_("Kept up to, in bytes"),
        description=N_("Empty for the broker's limit"),
        json_schema_extra=layout(),
    )
    arguments: str = Field(
        default="",
        title=N_("Arguments"),
        description=N_(
            "One name=value per line, such as x-stream-max-segment-size-bytes=500000000"
        ),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    _name = field_validator("name")(_checked_name)
    _arguments = field_validator("arguments")(_checked_arguments)

    @field_validator("max_age")
    @classmethod
    def _age(cls, text: str) -> str:
        if text and _AGE.fullmatch(text) is None:
            raise ValueError(say("Write an age as a number and Y, M, D, h, m or s"))
        return text


class NewExchangeParams(BaseModel):
    name: str = Field(title=N_("Name"), examples=["orders"], json_schema_extra=layout())
    exchange_type: str = Field(
        default="direct",
        title=N_("Type"),
        description=N_("direct, topic, fanout, headers, or a plugin's"),
        max_length=255,
        json_schema_extra=layout(),
    )
    durable: bool = Field(
        default=True,
        title=N_("Durable"),
        description=N_("Survives the broker's restart"),
        json_schema_extra=layout(),
    )
    internal: bool = Field(
        default=False,
        title=N_("Internal"),
        description=N_("Takes messages only from other exchanges"),
        json_schema_extra=layout(),
    )

    _name = field_validator("name")(_checked_name)


class NoParams(BaseModel):
    """Deleting and purging say nothing but which ones, and those are the selection."""


class BindParams(BaseModel):
    other: str = Field(
        title=N_("Bound to"),
        description=N_(
            "The exchange it comes from, or the queue or exchange it goes to"
        ),
        max_length=600,
        json_schema_extra=layout(),
    )
    routing_key: str = Field(
        default="",
        title=N_("Routing key"),
        description=N_("A topic exchange matches words: orders.* or orders.#"),
        max_length=255,
        json_schema_extra=layout(),
    )
    arguments: str = Field(
        default="",
        title=N_("Arguments"),
        description=N_("One name=value per line; a headers exchange matches on them"),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    _arguments = field_validator("arguments")(_checked_arguments)


class UnbindParams(BaseModel):
    binding: str = Field(
        title=N_("Binding"), max_length=2000, json_schema_extra=layout()
    )


class PublishParams(BaseModel):
    routing_key: str = Field(
        default="",
        title=N_("Routing key"),
        description=N_("For an exchange; a queue is reached by its name"),
        max_length=255,
        json_schema_extra=layout(),
    )
    body: str = Field(
        default="",
        title=N_("Body"),
        description=N_("Text, JSON, or 0x and hex digits for bytes"),
        max_length=1_000_000,
        json_schema_extra=layout(multiline=True),
    )
    content_type: str = Field(
        default="",
        title=N_("Content type"),
        description=N_("Such as application/json; empty for none"),
        max_length=255,
        json_schema_extra=layout(),
    )
    headers: str = Field(
        default="",
        title=N_("Headers"),
        description=N_('A JSON object, such as {"source": "manual"}'),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("headers")
    @classmethod
    def _headers(cls, text: str) -> str:
        if text.strip():
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if not isinstance(parsed, dict):
                raise ValueError(say("Headers are a JSON object"))
        return text


class PeekParams(BaseModel):
    count: int = Field(
        default=10,
        ge=1,
        le=PEEK_CEILING,
        title=N_("Messages"),
        description=N_(
            "Each is taken and put back: it comes back marked redelivered, and "
            "a quorum queue counts it towards its delivery limit"
        ),
        json_schema_extra=layout(),
    )


# --- shared ----------------------------------------------------------------------


class _RabbitmqAction:
    def __init__(self, session: RabbitmqSession, peeks: RabbitmqPeeks) -> None:
        self._session = session
        self._peeks = peeks

    def _named(self, node_id: str | None, prefixes: set[str]) -> Named:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose one first"))
        named = parse(node_id)
        if named.prefix not in prefixes or named.name is None:
            raise ActionRefused("not_applicable", say("Not for this kind of node"))
        own = self._session.options.vhost
        if own and named.vhost != own:
            raise ActionRefused("not_applicable", say("Not a node of this connection"))
        return named

    def _level(self, node_id: str | None, folder: str) -> str:
        """The virtual host of a level of the given kind, or a refusal."""
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a level first"))
        named = parse(node_id)
        if named.prefix != folder:
            raise ActionRefused("not_applicable", say("Not made on this level"))
        return named.vhost


def _bindings_path(named: Named) -> str:
    vhost = segment(named.vhost)
    assert named.name is not None
    if named.prefix == "exchange":
        return f"/exchanges/{vhost}/{exchange_path(named.name)}/bindings/source"
    return f"/queues/{vhost}/{segment(named.name)}/bindings"


async def _bindings(session: RabbitmqSession, named: Named) -> list[dict[str, Any]]:
    """The node's own bindings, the default exchange's implicit one left out."""
    answer = await session.api(_bindings_path(named))
    return [
        one for one in answer or [] if isinstance(one, dict) and one.get("source") != ""
    ]


def _binding_value(one: dict[str, Any]) -> str:
    return json.dumps(
        [
            one.get("source", ""),
            one.get("destination_type", ""),
            one.get("destination", ""),
            one.get("properties_key", ""),
        ]
    )


def _binding_label(one: dict[str, Any], named: Named) -> str:
    key = one.get("routing_key") or "—"
    if named.prefix == "exchange":
        return say(
            "to {destination} by {key}", destination=one.get("destination", ""), key=key
        )
    return say("from {source} by {key}", source=one.get("source", ""), key=key)


# --- making ------------------------------------------------------------------------


class NewQueue(_RabbitmqAction, JsonAction[NewQueueParams]):
    name: ClassVar[str] = "new_queue"
    title: ClassVar[str] = N_("New queue")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    params_model = NewQueueParams

    async def run(self, node_id: str | None, params: NewQueueParams) -> ActionResult:
        vhost = self._level(node_id, "queues")
        arguments = {
            **parse_arguments(params.arguments),
            "x-queue-type": params.queue_type,
        }
        await self._session.change(
            "PUT",
            f"/queues/{segment(vhost)}/{segment(params.name)}",
            {
                "durable": params.durable or params.queue_type == "quorum",
                "auto_delete": False,
                "arguments": arguments,
            },
        )
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=[folder_id("queues", vhost)],
            created_node_id=leaf_id("queue", vhost, params.name),
        )


class NewStream(_RabbitmqAction, JsonAction[NewStreamParams]):
    name: ClassVar[str] = "new_stream"
    title: ClassVar[str] = N_("New stream")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    params_model = NewStreamParams

    async def run(self, node_id: str | None, params: NewStreamParams) -> ActionResult:
        vhost = self._level(node_id, "streams")
        arguments = parse_arguments(params.arguments)
        if params.max_age:
            arguments["x-max-age"] = params.max_age
        if params.max_bytes is not None:
            arguments["x-max-length-bytes"] = params.max_bytes
        arguments["x-queue-type"] = "stream"
        await self._session.change(
            "PUT",
            f"/queues/{segment(vhost)}/{segment(params.name)}",
            {"durable": True, "auto_delete": False, "arguments": arguments},
        )
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=[folder_id("streams", vhost)],
            created_node_id=leaf_id("stream", vhost, params.name),
        )


class NewExchange(_RabbitmqAction, JsonAction[NewExchangeParams]):
    name: ClassVar[str] = "new_exchange"
    title: ClassVar[str] = N_("New exchange")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    params_model = NewExchangeParams

    async def _types(self) -> list[str]:
        """The types this broker knows: the four, and any a plugin adds."""
        overview = await self._session.api("/overview", {"columns": "exchange_types"})
        listed = overview.get("exchange_types") if isinstance(overview, dict) else None
        names = [
            str(one.get("name"))
            for one in listed or []
            if isinstance(one, dict) and one.get("name")
        ]
        return names or list(EXCHANGE_TYPES)

    async def field_hints(self, node_id: str | None) -> FieldHints:
        self._level(node_id, "exchanges")
        return FieldHints(
            choices={
                "exchange_type": [
                    FieldChoice(value=name, label=name) for name in await self._types()
                ]
            }
        )

    async def run(self, node_id: str | None, params: NewExchangeParams) -> ActionResult:
        vhost = self._level(node_id, "exchanges")
        if params.exchange_type not in await self._types():
            raise ActionRefused(
                "not_applicable", say("This broker has no exchanges of that type")
            )
        await self._session.change(
            "PUT",
            f"/exchanges/{segment(vhost)}/{segment(params.name)}",
            {
                "type": params.exchange_type,
                "durable": params.durable,
                "internal": params.internal,
                "auto_delete": False,
                "arguments": {},
            },
        )
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=[folder_id("exchanges", vhost)],
            created_node_id=leaf_id("exchange", vhost, params.name),
        )


# --- deleting and purging -------------------------------------------------------------


class DeleteNode(_RabbitmqAction, JsonAction[NoParams]):
    name: ClassVar[str] = "delete"
    title: ClassVar[str] = N_("Delete")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"amqp_queue", "amqp_stream", "exchange"}
    )
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    params_model = NoParams

    def _target(self, node_id: str | None) -> Named:
        named = self._named(node_id, {"queue", "stream", "exchange"})
        if named.prefix == "exchange" and is_system_exchange(named.name or ""):
            raise ActionRefused(
                "not_applicable", say("The broker's own exchanges are not deleted")
            )
        return named

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        try:
            named = self._target(node_id)
        except ActionRefused as refused:
            return ActionPreview(summary=refused.message, blocked=True)
        assert named.name is not None
        bindings = await _bindings(self._session, named)
        items = [_binding_label(one, named) for one in bindings]
        if named.prefix == "exchange":
            await read_exchange(self._session, named.vhost, named.name)
            return ActionPreview(
                summary=say(
                    "{name} and its {count} bindings will be deleted",
                    name=named.name,
                    count=len(bindings),
                ),
                items=items,
            )
        described = await read_queue(
            self._session, named.vhost, named.name, stream=named.prefix == "stream"
        )
        # A queue counted now over AMQP; a stream's count is the API's.
        count = (
            described.get("messages") or 0
            if named.prefix == "stream"
            else await self._session.waiting(named.vhost, named.name, node_id or "")
        )
        consumers = described.get("consumers")
        if isinstance(consumers, int) and consumers > 0:
            items.insert(0, say("{count} consumers take from it now", count=consumers))
        return ActionPreview(
            summary=say(
                "{name} and its {count} messages will be deleted",
                name=named.name,
                count=count,
            ),
            items=items,
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        named = self._target(node_id)
        assert named.name is not None
        vhost = segment(named.vhost)
        if named.prefix == "exchange":
            path = f"/exchanges/{vhost}/{segment(named.name)}"
            folder = folder_id("exchanges", named.vhost)
        else:
            path = f"/queues/{vhost}/{segment(named.name)}"
            folder = folder_id(
                "streams" if named.prefix == "stream" else "queues", named.vhost
            )
        await self._session.change("DELETE", path, node_id=node_id or "")
        return ActionResult(
            message=say("{name} deleted", name=named.name), reload_node_ids=[folder]
        )


class Purge(_RabbitmqAction, JsonAction[NoParams]):
    name: ClassVar[str] = "purge"
    title: ClassVar[str] = N_("Purge")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"amqp_queue"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "Delete every message waiting in the queue? This cannot be undone."
    )
    bulk: ClassVar[bool] = True
    params_model = NoParams

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        named = self._named(node_id, {"queue"})
        assert named.name is not None
        await read_queue(self._session, named.vhost, named.name, stream=False)
        ready = await self._session.waiting(named.vhost, named.name, node_id or "")
        return ActionPreview(
            summary=say(
                "{count} ready messages of {name} will be deleted",
                count=ready,
                name=named.name,
            ),
            items=[
                say("Messages taken and not yet acknowledged stay with their consumers")
            ],
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        named = self._named(node_id, {"queue"})
        assert named.name is not None
        await read_queue(self._session, named.vhost, named.name, stream=False)
        await self._session.change(
            "DELETE",
            f"/queues/{segment(named.vhost)}/{segment(named.name)}/contents",
            node_id=node_id or "",
        )
        return ActionResult(
            message=say("{name} purged", name=named.name),
            reload_node_ids=[folder_id("queues", named.vhost)],
        )


# --- binding ------------------------------------------------------------------------


class Bind(_RabbitmqAction, JsonAction[BindParams]):
    name: ClassVar[str] = "bind"
    title: ClassVar[str] = N_("Bind")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"amqp_queue", "amqp_stream", "exchange"}
    )
    acts_on: ClassVar[ActsOn] = "node"
    params_model = BindParams

    def _target(self, node_id: str | None) -> Named:
        named = self._named(node_id, {"queue", "stream", "exchange"})
        if named.prefix == "exchange" and named.name == "":
            raise ActionRefused(
                "not_applicable",
                say("The default exchange binds every queue by its name already"),
            )
        return named

    async def _choices(self, named: Named) -> list[FieldChoice]:
        vhost = segment(named.vhost)
        exchanges = await self._session.api(
            f"/exchanges/{vhost}",
            {"page": "1", "page_size": str(CHOICES), "sort": "name", "columns": "name"},
        )
        # The user's own first, then the broker's.
        exchange_names = sorted(
            (
                str(one["name"])
                for one in (exchanges or {}).get("items", [])
                if isinstance(one, dict) and one.get("name")
            ),
            key=lambda name: (is_system_exchange(name), name),
        )
        if named.prefix != "exchange":
            return [
                FieldChoice(value=f"exchange:{name}", label=name)
                for name in exchange_names
            ]
        queues = await self._session.api(
            f"/queues/{vhost}",
            {"page": "1", "page_size": str(CHOICES), "sort": "name", "columns": "name"},
        )
        queue_names = [
            str(one["name"])
            for one in (queues or {}).get("items", [])
            if isinstance(one, dict) and one.get("name")
        ]
        return [
            *[FieldChoice(value=f"queue:{name}", label=name) for name in queue_names],
            *[
                FieldChoice(
                    value=f"exchange:{name}", label=say("exchange {name}", name=name)
                )
                for name in exchange_names
                if name != named.name
            ],
        ]

    async def field_hints(self, node_id: str | None) -> FieldHints:
        named = self._target(node_id)
        return FieldHints(choices={"other": await self._choices(named)})

    def _ends(self, named: Named, other: str) -> tuple[str, str, str]:
        """The source exchange, the destination's kind as the API writes it
        (`q` or `e`) and the destination."""
        kind, colon, name = other.partition(":")
        if colon == "" or kind not in {"queue", "exchange"} or name == "":
            raise ActionRefused("not_applicable", say("Choose what it is bound to"))
        assert named.name is not None
        if named.prefix == "exchange":
            return named.name, "q" if kind == "queue" else "e", name
        if kind != "exchange":
            raise ActionRefused(
                "not_applicable", say("A queue is bound from an exchange")
            )
        return name, "q", named.name

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        named = self._target(node_id)
        try:
            source, _, destination = self._ends(named, params.other)
        except ActionRefused as refused:
            return ActionPreview(summary=refused.message, blocked=True)
        return ActionPreview(
            summary=say(
                "{source} will route to {destination} by {key}",
                source=source,
                destination=destination,
                key=params.routing_key or "—",
            )
        )

    async def run(self, node_id: str | None, params: BindParams) -> ActionResult:
        named = self._target(node_id)
        source, kind, destination = self._ends(named, params.other)
        await self._session.change(
            "POST",
            f"/bindings/{segment(named.vhost)}/e/{segment(source)}/{kind}/{segment(destination)}",
            {
                "routing_key": params.routing_key,
                "arguments": parse_arguments(params.arguments),
            },
        )
        return ActionResult(
            message=say(
                "{source} routes to {destination}",
                source=source,
                destination=destination,
            ),
            reload_node_ids=[],
        )


class Unbind(_RabbitmqAction, JsonAction[UnbindParams]):
    name: ClassVar[str] = "unbind"
    title: ClassVar[str] = N_("Unbind")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"amqp_queue", "amqp_stream", "exchange"}
    )
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_("Remove this binding?")
    params_model = UnbindParams

    async def field_hints(self, node_id: str | None) -> FieldHints:
        named = self._named(node_id, {"queue", "stream", "exchange"})
        bindings = await _bindings(self._session, named)
        return FieldHints(
            choices={
                "binding": [
                    FieldChoice(
                        value=_binding_value(one), label=_binding_label(one, named)
                    )
                    for one in bindings
                ]
            }
        )

    async def _found(self, named: Named, value: str) -> dict[str, Any]:
        for one in await _bindings(self._session, named):
            if _binding_value(one) == value:
                return one
        raise ActionRefused("not_applicable", say("That binding is not there any more"))

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        named = self._named(node_id, {"queue", "stream", "exchange"})
        try:
            one = await self._found(named, params.binding)
        except ActionRefused as refused:
            return ActionPreview(summary=refused.message, blocked=True)
        return ActionPreview(
            summary=say(
                "{source} will no longer route to {destination} by {key}",
                source=one.get("source", ""),
                destination=one.get("destination", ""),
                key=one.get("routing_key") or "—",
            )
        )

    async def run(self, node_id: str | None, params: UnbindParams) -> ActionResult:
        named = self._named(node_id, {"queue", "stream", "exchange"})
        one = await self._found(named, params.binding)
        kind = "q" if one.get("destination_type") == "queue" else "e"
        await self._session.change(
            "DELETE",
            f"/bindings/{segment(named.vhost)}/e/{segment(str(one['source']))}/{kind}/"
            f"{segment(str(one['destination']))}/{segment(str(one['properties_key']))}",
        )
        return ActionResult(message=say("Binding removed"), reload_node_ids=[])


# --- publishing and peeking ----------------------------------------------------------


class Publish(_RabbitmqAction, JsonAction[PublishParams]):
    name: ClassVar[str] = "publish"
    title: ClassVar[str] = N_("Publish")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"amqp_queue", "exchange"})
    acts_on: ClassVar[ActsOn] = "node"
    params_model = PublishParams

    async def run(self, node_id: str | None, params: PublishParams) -> ActionResult:
        named = self._named(node_id, {"queue", "exchange"})
        assert named.name is not None
        if named.prefix == "exchange":
            described = await read_exchange(self._session, named.vhost, named.name)
            if described.get("internal"):
                raise ActionRefused(
                    "not_applicable",
                    say(
                        "An internal exchange takes messages only from other exchanges"
                    ),
                )
            exchange, routing_key = named.name, params.routing_key
        else:
            await read_queue(self._session, named.vhost, named.name, stream=False)
            exchange, routing_key = "", named.name
        message = Outgoing(
            body=bytes_of(params.body),
            timestamp=None,
            content_type=params.content_type or None,
            headers=json.loads(params.headers) if params.headers.strip() else {},
            properties={},
        )
        async with self._session.channel(node_id or "", vhost=named.vhost) as channel:
            lost = await publish(channel, exchange, routing_key, [message])
        if lost:
            raise ActionRefused(
                "not_applicable",
                say(
                    "{exchange} routed the message to no queue, and it is lost",
                    exchange=exchange_title(exchange),
                ),
            )
        return ActionResult(message=say("Published"), reload_node_ids=[])


class Peek(_RabbitmqAction, JsonAction[PeekParams]):
    name: ClassVar[str] = "peek"
    title: ClassVar[str] = N_("Peek")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"amqp_queue"})
    acts_on: ClassVar[ActsOn] = "node"
    # Not a deletion, but a delivery nobody can take back (D330).
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "Take these messages and put them back? Each comes back marked "
        "redelivered; a quorum queue counts it towards its delivery limit, and "
        "a consumer may see them out of order."
    )
    params_model = PeekParams

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        named = self._named(node_id, {"queue"})
        assert named.name is not None
        described = await read_queue(
            self._session, named.vhost, named.name, stream=False
        )
        ready = await self._session.waiting(named.vhost, named.name, node_id or "")
        items = [
            say("Each comes back marked redelivered"),
            say("A consumer may see them out of their order"),
        ]
        if described.get("type") == "quorum":
            items.append(
                say("This quorum queue counts each towards its delivery limit")
            )
        return ActionPreview(
            summary=say(
                "{count} of {ready} ready messages of {name} will be looked at",
                count=min(params.count, ready),
                ready=ready,
                name=named.name,
            ),
            items=items,
            blocked=ready == 0,
        )

    async def run(self, node_id: str | None, params: PeekParams) -> ActionResult:
        named = self._named(node_id, {"queue"})
        assert named.name is not None
        await read_queue(self._session, named.vhost, named.name, stream=False)
        try:
            opened = await self._peeks.take(named.vhost, named.name, params.count)
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        return ActionResult(
            message=say("Looked into {name}", name=named.name),
            reload_node_ids=[],
            open_node_id=opened,
        )


RabbitmqActionType = type[
    NewQueue
    | NewStream
    | NewExchange
    | DeleteNode
    | Purge
    | Bind
    | Unbind
    | Publish
    | Peek
]

# The order the menu shows them in.
RABBITMQ_ACTION_TYPES: tuple[RabbitmqActionType, ...] = (
    NewQueue,
    NewStream,
    NewExchange,
    Publish,
    Peek,
    Bind,
    Unbind,
    Purge,
    DeleteNode,
)

_QUEUE = [Publish.name, Peek.name, Bind.name, Unbind.name, Purge.name, DeleteNode.name]
_STREAM = [Bind.name, Unbind.name, DeleteNode.name]
_EXCHANGE = [Publish.name, Bind.name, Unbind.name, DeleteNode.name]


def build_actions(session: RabbitmqSession, peeks: RabbitmqPeeks) -> list[Action[Any]]:
    return [action(session, peeks) for action in RABBITMQ_ACTION_TYPES]


def offered(node_id: str | None) -> list[str]:
    """The actions offered on a level or for a node of it, by name (D330)."""
    if node_id is None:
        return []
    try:
        named = parse(node_id)
    except ValueError:
        return []
    if named.prefix == "queues":
        return [NewQueue.name, *_QUEUE]
    if named.prefix == "streams":
        return [NewStream.name, *_STREAM]
    if named.prefix == "exchanges":
        return [NewExchange.name, *_EXCHANGE]
    if named.prefix == "queue":
        return _QUEUE
    if named.prefix == "stream":
        return _STREAM
    if named.prefix == "exchange":
        if named.name == "":
            return [Publish.name]
        if is_system_exchange(named.name or ""):
            return [Publish.name, Bind.name, Unbind.name]
        return _EXCHANGE
    return []
