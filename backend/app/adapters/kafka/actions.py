"""What a Kafka connection can be asked to do to its topics and groups (D309).

On the Topics level: make a topic; delete, change the settings of, add
partitions to, or delete the records of the selected ones. On the Consumer
groups level: move a group's positions or delete the group. Kafka's own topics
take none. A message is sent as a new row of the topic (D308), not here.
"""

import re
import time
from collections.abc import Mapping
from typing import Any, ClassVar

from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import (
    AlterConfigOpType,
    ConfigEntry,
    ConfigResource,
    ConfigSource,
    NewPartitions,
    NewTopic,
    ResourceType,
)
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
from app.adapters.kafka.catalog import (
    GROUP_PREFIX,
    GROUPS,
    TOPIC_PREFIX,
    TOPICS,
    group_of,
    is_internal,
    partitions_of,
    topic_of,
    watermarks,
)
from app.adapters.kafka.groups import commit_positions, read_standing
from app.adapters.kafka.messages import milliseconds_of
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.layout import layout
from app.core.translation import N_, say

# Kafka's rule for a topic's name; the catalog reads the same one.
_TOPIC_NAME = re.compile(r"[A-Za-z0-9._-]{1,249}")
# A setting's name, as Kafka spells every one of them.
_SETTING_NAME = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")

# How many groups a topic's deletion preview asks whether they read it.
GROUPS_ASKED = 100


def parse_settings(text: str) -> dict[str, str]:
    """`name=value` per line, as kafka-configs.sh takes them; `#` starts a comment."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        name, equals, value = line.partition("=")
        name = name.strip()
        if equals == "" or _SETTING_NAME.fullmatch(name) is None:
            raise ValueError(
                say('Write each setting as name=value, not "{line}"', line=line)
            )
        if name in found:
            raise ValueError(say("{name} is set twice", name=name))
        found[name] = value.strip()
    return found


def settings_text(settings: Mapping[str, str]) -> str:
    return "\n".join(f"{name}={value}" for name, value in settings.items())


# A moment, picked from a calendar or typed; empty is allowed, so the type
# stays text and only the form is told what the text is.
INSTANT = {**layout(), "format": "date-time"}


def _instant(text: str) -> str:
    if text.strip() != "":
        milliseconds_of(text)
    return text


# --- the forms -----------------------------------------------------------------


class NewTopicParams(BaseModel):
    name: str = Field(
        title=N_("Name"),
        description=N_("Letters, digits, dots, underscores and hyphens"),
        examples=["orders"],
        max_length=249,
        json_schema_extra=layout(),
    )
    partitions: int = Field(
        default=1,
        ge=1,
        le=10_000,
        title=N_("Partitions"),
        json_schema_extra=layout(),
    )
    replication_factor: int | None = Field(
        default=None,
        ge=1,
        le=32,
        title=N_("Replication factor"),
        description=N_("Empty for the broker's default"),
        json_schema_extra=layout(),
    )
    settings: str = Field(
        default="",
        title=N_("Settings"),
        description=N_("One name=value per line, such as retention.ms=86400000"),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("name")
    @classmethod
    def _name(cls, name: str) -> str:
        if _TOPIC_NAME.fullmatch(name) is None or name in {".", ".."}:
            raise ValueError(
                say("A topic name is letters, digits, dots, underscores and hyphens")
            )
        if name.startswith("_"):
            raise ValueError(
                say("A name that starts with an underscore is Kafka's own")
            )
        return name

    @field_validator("settings")
    @classmethod
    def _settings(cls, text: str) -> str:
        parse_settings(text)
        return text


class NoParams(BaseModel):
    """Deleting says nothing but which topics, and those are the selection."""


class SettingsParams(BaseModel):
    settings: str = Field(
        title=N_("Settings"),
        description=N_(
            "The settings made on the topic, one name=value per line; "
            "a line taken away returns that setting to the broker's default"
        ),
        max_length=20_000,
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("settings")
    @classmethod
    def _settings(cls, text: str) -> str:
        parse_settings(text)
        return text


class PartitionsParams(BaseModel):
    total: int = Field(
        ge=1,
        le=10_000,
        title=N_("Partitions in all"),
        description=N_("More than the topic has now; partitions are never taken away"),
        json_schema_extra=layout(),
    )


class DeleteRecordsParams(BaseModel):
    before: str = Field(
        default="",
        title=N_("Before"),
        description=N_(
            "A date and time, such as 2026-11-01T00:00:00Z; empty for every message"
        ),
        max_length=64,
        json_schema_extra=INSTANT,
    )

    _check = field_validator("before")(_instant)


class MoveParams(BaseModel):
    to: str = Field(
        default="start",
        title=N_("Move to"),
        json_schema_extra=layout(),
    )
    at: str = Field(
        default="",
        title=N_("Time"),
        description=N_("For a time: a date and time, such as 2026-11-01T00:00:00Z"),
        max_length=64,
        json_schema_extra=INSTANT,
    )
    topic: str = Field(
        default="",
        title=N_("Topic"),
        description=N_("Empty for every topic the group has positions in"),
        max_length=249,
        json_schema_extra=layout(),
    )

    _check = field_validator("at")(_instant)

    @field_validator("to")
    @classmethod
    def _to(cls, to: str) -> str:
        if to not in {"start", "end", "time"}:
            raise ValueError(say("Move to the start, the end or a time"))
        return to


# --- shared ----------------------------------------------------------------------


class _KafkaAction:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    def _topic(self, node_id: str | None) -> str:
        if node_id is None or not node_id.startswith(TOPIC_PREFIX):
            raise ActionRefused("not_applicable", say("Choose a topic first"))
        topic = topic_of(node_id)
        if is_internal(topic):
            raise ActionRefused(
                "not_applicable", say("Kafka's own topics are not changed from here")
            )
        return topic


def _settings_of(clients: KafkaClients, topic: str) -> dict[str, str]:
    """The settings made on the topic itself, the secret ones left out."""
    resource = ConfigResource(ResourceType.TOPIC, topic)
    entries = clients.admin().describe_configs(
        [resource], request_timeout=TIMEOUT_SECONDS
    )
    config = next(iter(entries.values())).result()
    return {
        name: entry.value
        for name, entry in sorted(config.items())
        if entry.source == ConfigSource.DYNAMIC_TOPIC_CONFIG.value
        and not entry.is_sensitive
        and entry.value is not None
    }


def _offsets_at(
    clients: KafkaClients, topic: str, partitions: list[int], milliseconds: int
) -> dict[int, int]:
    """Each partition's first offset at or after a moment, its end when none is."""
    ends = watermarks(clients, {topic: partitions})
    found = clients.consumer().offsets_for_times(
        [TopicPartition(topic, partition, milliseconds) for partition in partitions],
        timeout=TIMEOUT_SECONDS,
    )
    offsets: dict[int, int] = {}
    for tp in found:
        end = ends.get((topic, tp.partition), (0, 0))[1]
        offsets[tp.partition] = end if tp.offset < 0 else int(tp.offset)
    return offsets


# --- topics ------------------------------------------------------------------------


class NewTopicAction(_KafkaAction, JsonAction[NewTopicParams]):
    name: ClassVar[str] = "new_topic"
    title: ClassVar[str] = N_("New topic")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    params_model = NewTopicParams

    async def run(self, node_id: str | None, params: NewTopicParams) -> ActionResult:
        if node_id != TOPICS:
            raise ActionRefused(
                "not_applicable", say("A topic is made on the Topics level")
            )

        def create(clients: KafkaClients) -> None:
            topic = NewTopic(
                params.name,
                num_partitions=params.partitions,
                replication_factor=params.replication_factor or -1,
                config=parse_settings(params.settings),
            )
            for future in (
                clients.admin()
                .create_topics([topic], request_timeout=TIMEOUT_SECONDS)
                .values()
            ):
                future.result()
            # Made is not yet listed: the metadata catches up a moment later,
            # and the topic is opened as soon as this answers.
            deadline = time.monotonic() + TIMEOUT_SECONDS
            while params.name not in partitions_of(clients) and time.monotonic() < deadline:
                time.sleep(0.2)

        await self._session.run(create, TOPICS)
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=[TOPICS],
            created_node_id=TOPIC_PREFIX + params.name,
        )


class DeleteTopic(_KafkaAction, JsonAction[NoParams]):
    name: ClassVar[str] = "delete_topic"
    title: ClassVar[str] = N_("Delete topic")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"topic"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    params_model = NoParams

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        topic = self._topic(node_id)

        def look(clients: KafkaClients) -> tuple[int, list[str]]:
            known = partitions_of(clients, topic)
            marks = watermarks(clients, known)
            messages = sum(high - low for low, high in marks.values())
            admin = clients.admin()
            listed = admin.list_consumer_groups(
                request_timeout=TIMEOUT_SECONDS
            ).result()
            readers: list[str] = []
            for listing in sorted(listed.valid, key=lambda one: one.group_id)[
                :GROUPS_ASKED
            ]:
                positions = admin.list_consumer_group_offsets(
                    [ConsumerGroupTopicPartitions(listing.group_id)],
                    request_timeout=TIMEOUT_SECONDS,
                )[listing.group_id].result()
                if any(tp.topic == topic for tp in positions.topic_partitions or []):
                    readers.append(listing.group_id)
            return messages, readers

        messages, readers = await self._session.run(look, node_id or "")
        return ActionPreview(
            summary=say(
                "{name} and its {count} messages will be deleted",
                name=topic,
                count=messages,
            ),
            items=[say("Read by the group {group}", group=group) for group in readers],
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        topic = self._topic(node_id)

        def delete(clients: KafkaClients) -> None:
            for future in (
                clients.admin()
                .delete_topics([topic], request_timeout=TIMEOUT_SECONDS)
                .values()
            ):
                future.result()

        await self._session.run(delete, node_id or "")
        return ActionResult(
            message=say("{name} deleted", name=topic), reload_node_ids=[TOPICS]
        )


class ChangeTopicSettings(_KafkaAction, JsonAction[SettingsParams]):
    name: ClassVar[str] = "change_topic_settings"
    title: ClassVar[str] = N_("Change settings")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"topic"})
    acts_on: ClassVar[ActsOn] = "node"
    params_model = SettingsParams

    async def field_hints(self, node_id: str | None) -> FieldHints:
        topic = self._topic(node_id)
        current = await self._session.run(
            lambda clients: _settings_of(clients, topic), node_id or ""
        )
        return FieldHints(values={"settings": settings_text(current)})

    async def _changes(
        self, node_id: str | None, params: SettingsParams
    ) -> tuple[str, dict[str, str], list[str]]:
        topic = self._topic(node_id)
        wanted = parse_settings(params.settings)
        current = await self._session.run(
            lambda clients: _settings_of(clients, topic), node_id or ""
        )
        changed = {
            name: value for name, value in wanted.items() if current.get(name) != value
        }
        dropped = [name for name in current if name not in wanted]
        return topic, changed, dropped

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        topic, changed, dropped = await self._changes(node_id, self._validated(raw))
        items = [f"{name}={value}" for name, value in changed.items()]
        items += [
            say("{name} returns to the broker's default", name=name) for name in dropped
        ]
        if not items:
            return ActionPreview(summary=say("Nothing changes"), blocked=True)
        return ActionPreview(
            summary=say("The settings of {name} will change", name=topic), items=items
        )

    async def run(self, node_id: str | None, params: SettingsParams) -> ActionResult:
        topic, changed, dropped = await self._changes(node_id, params)
        entries = [
            ConfigEntry(name, value, incremental_operation=AlterConfigOpType.SET)
            for name, value in changed.items()
        ] + [
            ConfigEntry(name, None, incremental_operation=AlterConfigOpType.DELETE)
            for name in dropped
        ]
        if not entries:
            raise ActionRefused("not_applicable", say("Nothing changes"))

        def alter(clients: KafkaClients) -> None:
            resource = ConfigResource(
                ResourceType.TOPIC, topic, incremental_configs=entries
            )
            for future in (
                clients.admin()
                .incremental_alter_configs([resource], request_timeout=TIMEOUT_SECONDS)
                .values()
            ):
                future.result()

        await self._session.run(alter, node_id or "")
        return ActionResult(
            message=say("The settings of {name} changed", name=topic),
            reload_node_ids=[TOPICS],
        )


class AddPartitions(_KafkaAction, JsonAction[PartitionsParams]):
    name: ClassVar[str] = "add_partitions"
    title: ClassVar[str] = N_("Add partitions")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"topic"})
    acts_on: ClassVar[ActsOn] = "node"
    params_model = PartitionsParams

    async def _count(self, node_id: str | None) -> tuple[str, int]:
        topic = self._topic(node_id)
        known = await self._session.run(
            lambda clients: partitions_of(clients, topic), node_id or ""
        )
        return topic, len(known[topic])

    async def field_hints(self, node_id: str | None) -> FieldHints:
        _, count = await self._count(node_id)
        return FieldHints(values={"total": str(count + 1)})

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        topic, count = await self._count(node_id)
        if params.total <= count:
            return ActionPreview(
                summary=say(
                    "{name} has {count} partitions already", name=topic, count=count
                ),
                blocked=True,
            )
        return ActionPreview(
            summary=say(
                "{name} will have {total} partitions instead of {count}",
                name=topic,
                total=params.total,
                count=count,
            ),
            items=[
                say(
                    "From then on a key may go to another partition than before, "
                    "so the order of one key's messages holds only within each"
                )
            ],
        )

    async def run(self, node_id: str | None, params: PartitionsParams) -> ActionResult:
        topic, count = await self._count(node_id)
        if params.total <= count:
            raise ActionRefused(
                "not_applicable",
                say("{name} has {count} partitions already", name=topic, count=count),
            )

        def grow(clients: KafkaClients) -> None:
            for future in (
                clients.admin()
                .create_partitions(
                    [NewPartitions(topic, params.total)],
                    request_timeout=TIMEOUT_SECONDS,
                )
                .values()
            ):
                future.result()

        await self._session.run(grow, node_id or "")
        return ActionResult(
            message=say(
                "{name} has {total} partitions", name=topic, total=params.total
            ),
            reload_node_ids=[TOPICS],
        )


class DeleteRecords(_KafkaAction, JsonAction[DeleteRecordsParams]):
    name: ClassVar[str] = "delete_records"
    title: ClassVar[str] = N_("Delete messages")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"topic"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "These messages will be deleted from the topic for good. Delete them?"
    )
    params_model = DeleteRecordsParams

    def _plan(
        self, clients: KafkaClients, topic: str, before: str
    ) -> dict[int, tuple[int, int]]:
        """Each partition's first offset now and the one it will start at."""
        partitions = partitions_of(clients, topic)[topic]
        marks = watermarks(clients, {topic: partitions})
        if before.strip() == "":
            cut = {
                partition: marks.get((topic, partition), (0, 0))[1]
                for partition in partitions
            }
        else:
            cut = _offsets_at(clients, topic, partitions, milliseconds_of(before))
        plan: dict[int, tuple[int, int]] = {}
        for partition in partitions:
            low = marks.get((topic, partition), (0, 0))[0]
            plan[partition] = (low, max(cut[partition], low))
        return plan

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        topic = self._topic(node_id)
        plan = await self._session.run(
            lambda clients: self._plan(clients, topic, params.before), node_id or ""
        )
        gone = sum(new - low for low, new in plan.values())
        return ActionPreview(
            summary=say(
                "{count} messages will be deleted from {name}", count=gone, name=topic
            ),
            items=[
                say("Partition {n}: {count} messages", n=partition, count=new - low)
                for partition, (low, new) in sorted(plan.items())
                if new > low
            ],
            blocked=gone == 0,
        )

    async def run(
        self, node_id: str | None, params: DeleteRecordsParams
    ) -> ActionResult:
        topic = self._topic(node_id)

        def delete(clients: KafkaClients) -> int:
            plan = self._plan(clients, topic, params.before)
            cuts = [
                TopicPartition(topic, partition, new)
                for partition, (low, new) in plan.items()
                if new > low
            ]
            if cuts:
                for future in (
                    clients.admin()
                    .delete_records(cuts, request_timeout=TIMEOUT_SECONDS)
                    .values()
                ):
                    future.result()
            return sum(new - low for low, new in plan.values())

        count = await self._session.run(delete, node_id or "")
        return ActionResult(
            message=say(
                "{count} messages deleted from {name}", count=count, name=topic
            ),
            reload_node_ids=[TOPICS],
        )


# --- groups -------------------------------------------------------------------------


class MovePositions(_KafkaAction, JsonAction[MoveParams]):
    name: ClassVar[str] = "move_group_positions"
    title: ClassVar[str] = N_("Move positions")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"consumer_group"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "The group's consumers will read from these positions when they next start. Move them?"
    )
    params_model = MoveParams

    def _group(self, node_id: str | None) -> str:
        if node_id is None or not node_id.startswith(GROUP_PREFIX):
            raise ActionRefused("not_applicable", say("Choose a consumer group first"))
        return group_of(node_id)

    async def field_hints(self, node_id: str | None) -> FieldHints:
        self._group(node_id)

        def topics(clients: KafkaClients) -> list[str]:
            return sorted(
                name for name in partitions_of(clients) if not is_internal(name)
            )

        names = await self._session.run(topics, node_id or "")
        return FieldHints(
            choices={
                "to": [
                    FieldChoice(value="start", label=say("The start")),
                    FieldChoice(value="end", label=say("The end")),
                    FieldChoice(value="time", label=say("A time")),
                ],
                "topic": [FieldChoice(value="", label=say("Every topic it reads"))]
                + [FieldChoice(value=name, label=name) for name in names],
            },
            values={"to": "start", "topic": ""},
        )

    def _plan(
        self, clients: KafkaClients, group: str, params: MoveParams
    ) -> dict[tuple[str, int], tuple[int | None, int, int]]:
        """Each partition's position now, the new one, and the end."""
        standing = read_standing(clients, group)
        if standing.description.members:
            raise ActionRefused(
                "conflict",
                say(
                    "{group} has consumers; positions are moved while nobody reads",
                    group=group,
                ),
            )
        if params.topic != "":
            known = partitions_of(clients, params.topic)
            keys = [(params.topic, partition) for partition in known[params.topic]]
        else:
            keys = [(one.topic, one.partition) for one in standing.positions]
        committed = {
            (one.topic, one.partition): one.committed for one in standing.positions
        }
        plan: dict[tuple[str, int], tuple[int | None, int, int]] = {}
        for topic in sorted({topic for topic, _ in keys}):
            partitions = [partition for name, partition in keys if name == topic]
            marks = watermarks(clients, {topic: partitions})
            if params.to == "time":
                if params.at.strip() == "":
                    raise ValueError(say("Give the time to move to"))
                targets = _offsets_at(
                    clients, topic, partitions, milliseconds_of(params.at)
                )
            else:
                index = 0 if params.to == "start" else 1
                targets = {
                    partition: marks[(topic, partition)][index]
                    for partition in partitions
                }
            for partition in partitions:
                end = marks[(topic, partition)][1]
                plan[(topic, partition)] = (
                    committed.get((topic, partition)),
                    targets[partition],
                    end,
                )
        return plan

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        group = self._group(node_id)
        try:
            plan = await self._session.run(
                lambda clients: self._plan(clients, group, params), node_id or ""
            )
        except ActionRefused as refused:
            return ActionPreview(summary=refused.message, blocked=True)
        if not plan:
            return ActionPreview(
                summary=say("{group} has no positions to move", group=group),
                blocked=True,
            )
        return ActionPreview(
            summary=say("The positions of {group} will move", group=group),
            items=[
                say(
                    "{topic} {n}: {now} → {new}, {lag} behind",
                    topic=topic,
                    n=partition,
                    now="—" if now is None else now,
                    new=new,
                    lag=end - new,
                )
                for (topic, partition), (now, new, end) in sorted(plan.items())
            ],
        )

    async def run(self, node_id: str | None, params: MoveParams) -> ActionResult:
        group = self._group(node_id)

        def move(clients: KafkaClients) -> int:
            plan = self._plan(clients, group, params)
            if not plan:
                raise ActionRefused(
                    "not_applicable",
                    say("{group} has no positions to move", group=group),
                )
            positions = [
                TopicPartition(topic, partition, new)
                for (topic, partition), (_, new, _) in sorted(plan.items())
            ]
            commit_positions(clients, group, positions)
            return len(positions)

        count = await self._session.run(move, node_id or "")
        return ActionResult(
            message=say("{count} positions of {group} moved", count=count, group=group),
            reload_node_ids=[GROUPS],
        )


class DeleteGroup(_KafkaAction, JsonAction[NoParams]):
    """A group and the positions it keeps; refused while it has consumers."""

    name: ClassVar[str] = "delete_group"
    title: ClassVar[str] = N_("Delete group")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"consumer_group"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "The group and every position it keeps will be deleted; its consumers "
        "will start again by their own setting. Delete it?"
    )
    params_model = NoParams

    def _group(self, node_id: str | None) -> str:
        if node_id is None or not node_id.startswith(GROUP_PREFIX):
            raise ActionRefused("not_applicable", say("Choose a consumer group first"))
        return group_of(node_id)

    def _checked(self, clients: KafkaClients, group: str) -> list[str]:
        standing = read_standing(clients, group)
        if standing.description.members:
            raise ActionRefused(
                "conflict",
                say(
                    "{group} has consumers; a group is deleted while nobody reads",
                    group=group,
                ),
            )
        return [
            say(
                "{topic} {n}: position {now}, {lag} behind",
                topic=one.topic,
                n=one.partition,
                now="—" if one.committed is None else one.committed,
                lag="—" if one.lag is None else one.lag,
            )
            for one in standing.positions
        ]

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        group = self._group(node_id)
        try:
            items = await self._session.run(
                lambda clients: self._checked(clients, group), node_id or ""
            )
        except ActionRefused as refused:
            return ActionPreview(summary=refused.message, blocked=True)
        return ActionPreview(
            summary=say("{group} and its positions will be deleted", group=group),
            items=items,
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        group = self._group(node_id)

        def delete(clients: KafkaClients) -> None:
            self._checked(clients, group)
            for future in (
                clients.admin()
                .delete_consumer_groups([group], request_timeout=TIMEOUT_SECONDS)
                .values()
            ):
                future.result()

        await self._session.run(delete, node_id or "")
        return ActionResult(
            message=say("{name} deleted", name=group), reload_node_ids=[GROUPS]
        )


TOPIC_ACTIONS = (DeleteTopic, ChangeTopicSettings, AddPartitions, DeleteRecords)
GROUP_ACTIONS = (MovePositions, DeleteGroup)

KafkaActionType = type[
    NewTopicAction
    | DeleteTopic
    | ChangeTopicSettings
    | AddPartitions
    | DeleteRecords
    | MovePositions
    | DeleteGroup
]

# The order the menu shows them in.
KAFKA_ACTION_TYPES: tuple[KafkaActionType, ...] = (
    NewTopicAction,
    *TOPIC_ACTIONS,
    *GROUP_ACTIONS,
)


def build_actions(session: KafkaSession) -> list[Action[Any]]:
    return [action(session) for action in KAFKA_ACTION_TYPES]


def offered(node_id: str | None) -> list[str]:
    """The actions offered on a level or for a node of it, by name (D309)."""
    if node_id == TOPICS:
        return [NewTopicAction.name, *(action.name for action in TOPIC_ACTIONS)]
    if node_id is not None and node_id.startswith(TOPIC_PREFIX):
        if is_internal(node_id[len(TOPIC_PREFIX) :]):
            return []
        return [action.name for action in TOPIC_ACTIONS]
    if node_id == GROUPS or (node_id is not None and node_id.startswith(GROUP_PREFIX)):
        return [action.name for action in GROUP_ACTIONS]
    return []
