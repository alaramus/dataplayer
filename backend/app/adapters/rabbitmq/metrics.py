"""What a RabbitMQ broker is measured by (D128, D331).

One poll is the overview, the nodes and the first hundred queues by name. No
message content is ever a metric.
"""

from typing import Any

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.core.translation import N_

# How many queues one poll measures.
POLLED = 100

_QUEUE_COLUMNS = "name,vhost,type,messages,messages_ready,messages_unacknowledged"


def _value(source: Any, name: str) -> float | None:
    found = source.get(name) if isinstance(source, dict) else None
    if isinstance(found, bool) or not isinstance(found, int | float):
        return None
    return float(found)


def _add(
    found: list[MetricSample],
    metric: str,
    field: str,
    value: float | None,
    **extra: Any,
) -> None:
    if value is not None:
        found.append(MetricSample(metric, field, value, **extra))


async def samples(session: RabbitmqSession) -> list[MetricSample]:
    found: list[MetricSample] = []
    overview = await session.api("/overview")
    totals = overview.get("object_totals") if isinstance(overview, dict) else None
    for name in ("connections", "channels", "consumers", "queues"):
        _add(found, "broker", name, _value(totals, name))
    nodes = await session.api("/nodes") or []
    alarms = sum(
        1
        for node in nodes
        if isinstance(node, dict)
        and (node.get("mem_alarm") or node.get("disk_free_alarm"))
    )
    found.append(MetricSample("broker", "alarms", float(alarms)))

    stats = overview.get("message_stats") if isinstance(overview, dict) else None
    for name in ("publish", "deliver_get", "redeliver"):
        _add(found, "messages", name, _value(stats, name), counter=True)
    queued = overview.get("queue_totals") if isinstance(overview, dict) else None
    _add(found, "messages", "ready", _value(queued, "messages_ready"))
    _add(found, "messages", "unacknowledged", _value(queued, "messages_unacknowledged"))

    own = session.options.vhost
    path = f"/queues/{segment(own)}" if own else "/queues"
    answer = await session.api(
        path,
        {
            "page": "1",
            "page_size": str(POLLED),
            "sort": "name",
            "columns": _QUEUE_COLUMNS,
        },
    )
    items = answer.get("items", []) if isinstance(answer, dict) else []
    for queue in items:
        if not isinstance(queue, dict):
            continue
        # The root virtual host is left out of a label, as nobody names it.
        vhost, name = str(queue.get("vhost", "")), str(queue.get("name", ""))
        label = name if vhost == "/" else f"{vhost}/{name}"
        if queue.get("type") == "stream":
            _add(found, "queue", "stream", _value(queue, "messages"), label=label)
            continue
        _add(found, "queue", "ready", _value(queue, "messages_ready"), label=label)
        _add(
            found,
            "queue",
            "unacknowledged",
            _value(queue, "messages_unacknowledged"),
            label=label,
        )
    return found


class RabbitmqMetrics:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        return await samples(self._session)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="rabbitmq-broker",
        name=N_("RabbitMQ broker"),
        description=N_(
            "Messages a second, what waits in each queue and what is taken and not "
            "acknowledged, connections and alarms; the first hundred queues by name."
        ),
        recipes=(
            MetricRecipe(
                "timeseries",
                N_("Messages per second"),
                (0, 0, 8, 5),
                "messages",
                ("publish", "deliver_get", "redeliver"),
            ),
            MetricRecipe(
                "stat", N_("Connections"), (8, 0, 4, 5), "broker", ("connections",)
            ),
            MetricRecipe(
                "timeseries", N_("Ready by queue"), (0, 5, 6, 5), "queue", ("ready",)
            ),
            MetricRecipe(
                "timeseries",
                N_("Unacknowledged by queue"),
                (6, 5, 6, 5),
                "queue",
                ("unacknowledged",),
            ),
            MetricRecipe("stat", N_("Alarms"), (0, 10, 4, 4), "broker", ("alarms",)),
        ),
    ),
)
