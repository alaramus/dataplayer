"""What a Kafka cluster is measured by (D128, D310): lag, growth and health.

One poll is the metadata, every polled partition's end offset and each polled
group's positions. The first hundred topics and groups by name are polled.
"""

from confluent_kafka import ConsumerGroupTopicPartitions

from app.adapters.kafka.catalog import is_internal, watermarks
from app.adapters.kafka.reports import health
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.core.translation import N_

# How many topics and groups one poll measures.
POLLED = 100


def samples(clients: KafkaClients) -> list[MetricSample]:
    seen = health(clients)
    found = [
        MetricSample("cluster", "brokers", float(len(seen.brokers))),
        MetricSample("cluster", "partitions", float(seen.partitions)),
        MetricSample("cluster", "short", float(seen.short)),
        MetricSample("cluster", "offline", float(seen.offline)),
    ]
    admin = clients.admin()
    metadata = admin.list_topics(timeout=TIMEOUT_SECONDS)
    topics = {
        name: sorted(described.partitions)
        for name, described in sorted(metadata.topics.items())
        if described.error is None and not is_internal(name)
    }
    polled = dict(list(topics.items())[:POLLED])
    marks = watermarks(clients, polled)
    for name, partitions in polled.items():
        end = sum(marks.get((name, partition), (0, 0))[1] for partition in partitions)
        found.append(
            MetricSample("messages", "produced", float(end), label=name, counter=True)
        )

    listed = admin.list_consumer_groups(request_timeout=TIMEOUT_SECONDS).result()
    for group in sorted(listing.group_id for listing in listed.valid)[:POLLED]:
        positions = (
            admin.list_consumer_group_offsets(
                [ConsumerGroupTopicPartitions(group)], request_timeout=TIMEOUT_SECONDS
            )[group]
            .result()
            .topic_partitions
            or []
        )
        ends = watermarks(
            clients,
            {
                topic: sorted({tp.partition for tp in positions if tp.topic == topic})
                for topic in {tp.topic for tp in positions}
            },
        )
        lag = sum(
            max(ends[(tp.topic, tp.partition)][1] - tp.offset, 0)
            for tp in positions
            if tp.offset >= 0 and (tp.topic, tp.partition) in ends
        )
        found.append(MetricSample("lag", "messages", float(lag), label=group))
    return found


class KafkaMetrics:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        return await self._session.run(samples)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="kafka-cluster",
        name=N_("Kafka cluster"),
        description=N_(
            "How far each consumer group lags, how fast each topic grows, and the "
            "cluster's partitions; the first hundred topics and groups by name."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("Consumer lag"), (0, 0, 8, 5), "lag"),
            MetricRecipe("stat", N_("Brokers"), (8, 0, 4, 5), "cluster", ("brokers",)),
            MetricRecipe(
                "timeseries", N_("Messages per second"), (0, 5, 8, 5), "messages"
            ),
            MetricRecipe(
                "timeseries",
                N_("Partitions needing attention"),
                (8, 5, 4, 5),
                "cluster",
                ("short", "offline"),
            ),
        ),
    ),
)
