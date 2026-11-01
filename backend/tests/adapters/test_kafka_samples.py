"""The lab put into a Kafka this server started (D311)."""

from app.adapters.catalog import ConsumerGroupNode, TopicNode
from app.adapters.fetch import FetchRequest
from app.adapters.kafka.samples import GROUP, TOPICS
from tests.adapters.kafka_fixture import adapter, admin, on_server


def _drop_lab() -> None:
    client = admin()
    listed = client.list_consumer_groups().result()
    if GROUP in {listing.group_id for listing in listed.valid}:
        for future in client.delete_consumer_groups([GROUP]).values():
            future.result()
    there = [topic for topic in TOPICS if topic in client.list_topics(timeout=5).topics]
    if there:
        for future in client.delete_topics(there).values():
            future.result()


async def test_the_lab_is_made_and_made_again_the_same() -> None:
    source = adapter()
    try:
        first = await source.install_sample_data()
        again = await source.install_sample_data()
        assert first == again and GROUP in first

        topics = {node.name: node for node in await source.list_children("topics")}
        assert set(TOPICS) <= set(topics)
        orders = topics["lab.orders"]
        assert isinstance(orders, TopicNode) and orders.partitions == 3
        assert orders.messages == 300

        page = await source.fetch(FetchRequest(node_id="topic:lab.orders", limit=1))
        assert "value.customer" in [column.name for column in page.columns]
        sensor = await source.fetch(FetchRequest(node_id="topic:lab.sensor", limit=1))
        assert (sensor.rows[0][4] or "").startswith("0x")

        groups = {node.name: node for node in await source.list_children("groups")}
        billing = groups[GROUP]
        assert isinstance(billing, ConsumerGroupNode) and billing.state == "empty"
        positions = await source.fetch(FetchRequest(node_id=f"group:{GROUP}"))
        assert {row[4] for row in positions.rows} == {"40"}
    finally:
        await on_server(_drop_lab)
