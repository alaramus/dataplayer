from app.adapters.rabbitmq.card import rabbitmq_view
from app.adapters.summary import (
    AmqpConsumer,
    AmqpExchangeContents,
    AmqpQueueContents,
    AmqpSetting,
    AmqpStreamContents,
    NodeSummary,
)
from app.adapters.views import (
    BooleanValue,
    DocumentView,
    FieldsBlock,
    ListValue,
    NumberValue,
    PairsBlock,
    SectionBlock,
    StateValue,
    TableBlock,
    TextValue,
)


def _overview(view: DocumentView) -> dict[str, object]:
    section = next(
        block
        for block in view.blocks
        if isinstance(block, SectionBlock) and block.title == "Overview"
    )
    fields = next(block for block in section.blocks if isinstance(block, FieldsBlock))
    return {field.label: field.value for field in fields.fields}


def test_a_queue_card_shows_state_counts_rates_consumers_policy_and_arguments() -> None:
    view = rabbitmq_view(
        NodeSummary(
            node_id="queue:%2F/orders",
            name="orders",
            kind="amqp_queue",
            contents=AmqpQueueContents(
                queue_type="quorum",
                state="running",
                ready=14,
                unacknowledged=2,
                rate_in=1.5,
                rate_out=0.5,
                node="rabbit@node1",
                policy="ha-policy",
                arguments=[AmqpSetting(name="x-queue-type", value="quorum")],
                consumers=[
                    AmqpConsumer(
                        tag="worker-1",
                        channel="10.0.0.2:52744 (1)",
                        prefetch=20,
                        acknowledges=True,
                        active=True,
                    )
                ],
            ),
        ),
        queue_messages=16,
    )

    assert view.header.title == "orders"
    assert isinstance(view.header.subtitle, TextValue)
    assert view.header.subtitle.text == "quorum"
    assert isinstance(view.header.state, StateValue)
    assert (view.header.state.word, view.header.state.tone) == ("running", "good")
    overview = _overview(view)
    assert overview["Total messages"] == NumberValue(value=16)
    assert overview["Messages ready"] == NumberValue(value=14)
    assert overview["Messages unacknowledged"] == NumberValue(value=2)
    assert overview["Consumers"] == NumberValue(value=1)
    assert overview["Incoming rate"] == NumberValue(
        value=1.5, unit="messages/s"
    )
    assert overview["Outgoing rate"] == NumberValue(
        value=0.5, unit="messages/s"
    )
    assert overview["Queue policy"] == TextValue(text="ha-policy")
    consumers = next(
        block
        for block in view.blocks
        if isinstance(block, SectionBlock) and block.title == "Consumers"
    ).blocks[0]
    assert isinstance(consumers, TableBlock)
    assert consumers.rows[0][0] == TextValue(text="worker-1")
    assert consumers.rows[0][2] == NumberValue(value=20)
    assert consumers.rows[0][3] == BooleanValue(value=True)
    arguments = next(
        block
        for block in view.blocks
        if isinstance(block, SectionBlock) and block.title == "Arguments"
    ).blocks[0]
    assert isinstance(arguments, PairsBlock)
    assert [(one.name, one.value) for one in arguments.pairs] == [("x-queue-type", "quorum")]


def test_a_stream_card_shows_its_api_state_members_and_consumer_rate() -> None:
    view = rabbitmq_view(
        NodeSummary(
            node_id="stream:%2F/prices",
            name="prices",
            kind="amqp_stream",
            contents=AmqpStreamContents(
                messages=100,
                segments=4,
                rate_in=2.0,
                leader="rabbit@node1",
                members=["rabbit@node1", "rabbit@node2"],
                policy="retention",
                arguments=[AmqpSetting(name="x-queue-type", value="stream")],
                consumers=[AmqpConsumer(tag="stream-reader")],
            ),
        ),
        stream_state="running",
    )

    assert isinstance(view.header.state, StateValue)
    assert view.header.state.word == "running"
    overview = _overview(view)
    assert overview["Messages"] == NumberValue(value=100)
    assert overview["Segments"] == NumberValue(value=4)
    assert overview["Consumers"] == NumberValue(value=1)
    assert overview["Incoming rate"] == NumberValue(
        value=2.0, unit="messages/s"
    )
    assert overview["Stream leader"] == TextValue(text="rabbit@node1")
    assert overview["Stream policy"] == TextValue(text="retention")
    members = overview["Stream members"]
    assert isinstance(members, ListValue)
    assert members.items == ["rabbit@node1", "rabbit@node2"]


def test_an_exchange_card_shows_only_exchange_fields_and_arguments() -> None:
    view = rabbitmq_view(
        NodeSummary(
            node_id="exchange:%2F/orders",
            name="orders",
            kind="exchange",
            contents=AmqpExchangeContents(
                exchange_type="topic",
                durable=True,
                auto_delete=False,
                internal=False,
                rate_in=3.0,
                rate_out=2.0,
                arguments=[AmqpSetting(name="alternate-exchange", value="fallback")],
            ),
        ),
        exchange_messages_in=50,
        exchange_messages_out=48,
    )

    overview = _overview(view)
    assert view.header.subtitle == TextValue(text="topic")
    assert overview["Messages published to exchange"] == NumberValue(value=50)
    assert overview["Messages routed from exchange"] == NumberValue(value=48)
    assert overview["Incoming rate"] == NumberValue(
        value=3.0, unit="messages/s"
    )
    assert overview["Outgoing rate"] == NumberValue(
        value=2.0, unit="messages/s"
    )
    assert overview["Durable"] == BooleanValue(value=True)
    assert overview["Auto delete"] == BooleanValue(value=False)
    assert overview["Internal"] == BooleanValue(value=False)
    assert not any(
        isinstance(block, SectionBlock) and block.title == "Consumers"
        for block in view.blocks
    )
