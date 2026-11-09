"""What a queue, a stream and an exchange are, as the management API last
measured them (D326)."""

import json
from datetime import UTC, datetime
from typing import Any

from app.adapters.rabbitmq.catalog import (
    BINDINGS,
    MESSAGES,
    exchange_title,
    leaf_id,
    parse,
    read_exchange,
    read_queue,
)
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.summary import (
    AmqpConsumer,
    AmqpExchangeContents,
    AmqpQueueContents,
    AmqpSetting,
    AmqpStreamContents,
    NodeSummary,
)
from app.adapters.words import worded_titles
from app.core.translation import say


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _rate(stats: Any, name: str) -> float | None:
    if not isinstance(stats, dict):
        return None
    details = stats.get(name)
    if not isinstance(details, dict):
        return None
    rate = details.get("rate")
    return float(rate) if isinstance(rate, int | float) else None


def settings_of(arguments: Any) -> list[AmqpSetting]:
    if not isinstance(arguments, dict):
        return []
    return [
        AmqpSetting(
            name=str(name),
            value=value if isinstance(value, str) else json.dumps(value, default=str),
        )
        for name, value in sorted(arguments.items())
    ]


def consumers_of(described: dict[str, Any]) -> list[AmqpConsumer]:
    found: list[AmqpConsumer] = []
    for one in described.get("consumer_details") or []:
        if not isinstance(one, dict):
            continue
        channel = one.get("channel_details")
        found.append(
            AmqpConsumer(
                tag=str(one.get("consumer_tag", "")),
                channel=_text(channel.get("name"))
                if isinstance(channel, dict)
                else None,
                prefetch=_int(one.get("prefetch_count")),
                acknowledges=bool(one.get("ack_required", True)),
                active=one.get("active")
                if isinstance(one.get("active"), bool)
                else None,
            )
        )
    return found


def _moment(value: Any) -> datetime | None:
    """The API's `first_timestamp`: milliseconds, or text, or nothing."""
    if isinstance(value, int) and value > 0:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    if isinstance(value, str) and value:
        try:
            at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return at if at.tzinfo else at.replace(tzinfo=UTC)
    return None


async def node_summary(session: RabbitmqSession, node_id: str) -> NodeSummary:
    named = parse(node_id)
    if named.name is None:
        raise ValueError(say("Not a node of this connection"))
    if named.prefix == "exchange":
        described = await read_exchange(session, named.vhost, named.name)
        stats = described.get("message_stats")
        return NodeSummary(
            node_id=leaf_id("exchange", named.vhost, named.name),
            name=exchange_title(named.name),
            kind="exchange",
            representations=worded_titles([BINDINGS]),
            contents=AmqpExchangeContents(
                exchange_type=str(described.get("type") or "direct"),
                durable=bool(described.get("durable", True)),
                auto_delete=bool(described.get("auto_delete", False)),
                internal=bool(described.get("internal", False)),
                rate_in=_rate(stats, "publish_in_details"),
                rate_out=_rate(stats, "publish_out_details"),
                arguments=settings_of(described.get("arguments")),
            ),
        )
    stream = named.prefix == "stream"
    described = await read_queue(session, named.vhost, named.name, stream=stream)
    stats = described.get("message_stats")
    if stream:
        members = described.get("members")
        return NodeSummary(
            node_id=leaf_id("stream", named.vhost, named.name),
            name=named.name,
            kind="amqp_stream",
            representations=worded_titles([MESSAGES]),
            contents=AmqpStreamContents(
                messages=_int(described.get("messages")),
                segments=_int(described.get("segments")),
                rate_in=_rate(stats, "publish_details"),
                first_at=_moment(described.get("first_timestamp")),
                leader=_text(described.get("leader")),
                members=[str(one) for one in members]
                if isinstance(members, list)
                else [],
                policy=_text(described.get("policy")),
                arguments=settings_of(described.get("arguments")),
                consumers=consumers_of(described),
            ),
        )
    return NodeSummary(
        node_id=leaf_id("queue", named.vhost, named.name),
        name=named.name,
        kind="amqp_queue",
        representations=worded_titles([BINDINGS]),
        contents=AmqpQueueContents(
            queue_type=str(described.get("type") or "classic"),
            state=_text(described.get("state")),
            ready=_int(described.get("messages_ready")),
            unacknowledged=_int(described.get("messages_unacknowledged")),
            rate_in=_rate(stats, "publish_details"),
            rate_out=_rate(stats, "deliver_get_details"),
            node=_text(described.get("node") or described.get("leader")),
            policy=_text(described.get("policy")),
            arguments=settings_of(described.get("arguments")),
            consumers=consumers_of(described),
        ),
    )
