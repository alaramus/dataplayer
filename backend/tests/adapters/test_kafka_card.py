from app.adapters.kafka.card import topic_view
from app.adapters.summary import KafkaPartition, KafkaSetting, KafkaTopicContents
from app.adapters.views import (
    CodeValue,
    DocumentView,
    EmptyValue,
    PairsBlock,
    SectionBlock,
    TableBlock,
    TextValue,
)


def test_a_topic_card_shows_partition_placement_offsets_and_hidden_settings() -> None:
    view = topic_view(
        "orders",
        KafkaTopicContents(
            partitions=[
                KafkaPartition(
                    partition=0,
                    leader=2,
                    replicas=[2, 3],
                    in_sync=[2],
                    first_offset=10,
                    end_offset=19,
                ),
                KafkaPartition(
                    partition=1,
                    leader=None,
                    replicas=[3],
                    in_sync=[],
                ),
            ],
            settings=[
                KafkaSetting(name="retention.ms", value="86400000"),
                KafkaSetting(name="secret.setting", value=None),
            ],
        ),
    )

    assert isinstance(view, DocumentView)
    sections = {block.title: block for block in view.blocks if isinstance(block, SectionBlock)}
    partitions = sections["Partitions"].blocks[0]
    assert isinstance(partitions, TableBlock)
    assert partitions.columns == [
        "Partition ID",
        "Leader broker",
        "Replica brokers",
        "In-sync replica brokers",
        "First offset",
        "End offset",
    ]
    assert isinstance(partitions.rows[0][0], TextValue)
    assert partitions.rows[0][0].text == "0"
    assert isinstance(partitions.rows[0][1], TextValue)
    assert partitions.rows[0][1].text == "2"
    assert partitions.rows[0][4] == CodeValue(text="10")
    assert partitions.rows[0][5] == CodeValue(text="19")
    assert partitions.rows[1][1] == EmptyValue()
    assert partitions.rows[1][4] == EmptyValue()

    settings = sections["Topic settings"].blocks[0]
    assert isinstance(settings, PairsBlock)
    assert [(one.name, one.value, one.sensitive) for one in settings.pairs] == [
        ("retention.ms", "86400000", False),
        ("secret.setting", "Hidden by Kafka", False),
    ]


def test_a_topic_card_reports_partitions_omitted_by_the_view_limit() -> None:
    contents = KafkaTopicContents(
        partitions=[KafkaPartition(partition=index) for index in range(501)]
    )

    view = topic_view("large", contents)
    partition_table = next(
        block.blocks[0]
        for block in view.blocks
        if isinstance(block, SectionBlock) and block.title == "Partitions"
    )

    assert isinstance(partition_table, TableBlock)
    assert len(partition_table.rows) == 500
    assert partition_table.omitted == 1
