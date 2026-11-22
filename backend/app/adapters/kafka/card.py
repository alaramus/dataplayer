"""A topic's partitions and its own configuration as a view (D305, D419, D444)."""

from app.adapters.summary import KafkaTopicContents
from app.adapters.views import (
    DocumentView,
    EmptyValue,
    FieldsBlock,
    MAX_TEXT,
    NumberValue,
    SectionBlock,
    ViewField,
    ViewHeader,
    ViewPair,
    ViewValue,
    chips,
    code,
    pairs,
    table,
    text,
)
from app.core.translation import say


def topic_view(name: str, contents: KafkaTopicContents) -> DocumentView:
    """Render the topic facts already read for its summary; no message read."""
    partition_rows: list[list[ViewValue]] = [
        [
            text(str(partition.partition)),
            text(str(partition.leader)) if partition.leader is not None else EmptyValue(),
            chips([str(broker) for broker in partition.replicas]),
            chips([str(broker) for broker in partition.in_sync]),
            code(str(partition.first_offset))
            if partition.first_offset is not None
            else EmptyValue(),
            code(str(partition.end_offset))
            if partition.end_offset is not None
            else EmptyValue(),
        ]
        for partition in contents.partitions
    ]
    settings = pairs(
        [
            ViewPair(
                name=setting.name[:MAX_TEXT],
                value=(
                    setting.value[:MAX_TEXT]
                    if setting.value is not None
                    else say("Hidden by Kafka")
                ),
            )
            for setting in contents.settings
        ]
    )
    return DocumentView(
        header=ViewHeader(title=name),
        blocks=[
            SectionBlock(
                title=say("Overview"),
                blocks=[
                    FieldsBlock(
                        fields=[
                            ViewField(
                                label=say("Partitions"),
                                value=NumberValue(value=float(len(contents.partitions))),
                            ),
                            ViewField(
                                label=say("Configured settings"),
                                value=NumberValue(value=float(len(contents.settings))),
                            ),
                        ]
                    )
                ],
            ),
            SectionBlock(
                title=say("Partitions"),
                blocks=[
                    table(
                        [
                            say("Partition ID"),
                            say("Leader broker"),
                            say("Replica brokers"),
                            say("In-sync replica brokers"),
                            say("First offset"),
                            say("End offset"),
                        ],
                        partition_rows,
                    )
                ],
            ),
            SectionBlock(
                title=say("Topic settings"),
                blocks=[settings],
            ),
        ],
    )
