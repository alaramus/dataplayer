"""A queue, stream or exchange as the Management API describes it (D326, D419)."""

from app.adapters.summary import (
    AmqpConsumer,
    AmqpExchangeContents,
    AmqpQueueContents,
    AmqpSetting,
    AmqpStreamContents,
    NodeSummary,
)
from app.adapters.views import (
    MAX_TEXT,
    BooleanValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    NumberValue,
    SectionBlock,
    StateValue,
    Tone,
    ViewField,
    ViewHeader,
    ViewPair,
    ViewValue,
    chips,
    code,
    moment,
    pairs,
    table,
    text,
)
from app.core.translation import N_, say

_STATE_WORDS = {
    "running": N_("running"),
    "idle": N_("idle"),
    "flow": N_("flow"),
    "blocked": N_("blocked"),
}
_STATE_TONES: dict[str, Tone] = {
    "running": "good",
    "idle": "neutral",
    "flow": "busy",
    "blocked": "warning",
}


def rabbitmq_view(
    summary: NodeSummary,
    *,
    stream_state: str | None = None,
    queue_messages: int | None = None,
    exchange_messages_in: int | None = None,
    exchange_messages_out: int | None = None,
) -> DocumentView:
    contents = summary.contents
    if isinstance(contents, AmqpQueueContents):
        return _queue(summary, contents, queue_messages)
    if isinstance(contents, AmqpStreamContents):
        return _stream(summary, contents, stream_state)
    if isinstance(contents, AmqpExchangeContents):
        return _exchange(summary, contents, exchange_messages_in, exchange_messages_out)
    raise ValueError(say("Only a queue, a stream or an exchange has details"))


def _queue(
    summary: NodeSummary,
    contents: AmqpQueueContents,
    message_count: int | None,
) -> DocumentView:
    fields = [
        ViewField(label=say("Total messages"), value=_number(message_count)),
        ViewField(label=say("Messages ready"), value=_number(contents.ready)),
        ViewField(label=say("Messages unacknowledged"), value=_number(contents.unacknowledged)),
        ViewField(
            label=say("Consumers"),
            value=NumberValue(value=float(len(contents.consumers))),
        ),
        ViewField(label=say("Incoming rate"), value=_rate(contents.rate_in)),
        ViewField(label=say("Outgoing rate"), value=_rate(contents.rate_out)),
        ViewField(label=say("Queue node"), value=_code(contents.node)),
        ViewField(label=say("Queue policy"), value=_text(contents.policy)),
    ]
    return DocumentView(
        header=ViewHeader(
            title=summary.name,
            subtitle=text(contents.queue_type),
            state=_state(contents.state),
        ),
        blocks=[
            _overview(fields),
            _arguments(contents.arguments),
            _consumers(contents.consumers),
        ],
    )


def _stream(
    summary: NodeSummary, contents: AmqpStreamContents, state: str | None
) -> DocumentView:
    fields = [
        ViewField(label=say("Messages"), value=_number(contents.messages)),
        ViewField(label=say("Segments"), value=_number(contents.segments)),
        ViewField(
            label=say("Consumers"),
            value=NumberValue(value=float(len(contents.consumers))),
        ),
        ViewField(label=say("Incoming rate"), value=_rate(contents.rate_in)),
        ViewField(label=say("First message"), value=moment(contents.first_at)),
        ViewField(label=say("Stream leader"), value=_text(contents.leader)),
        ViewField(label=say("Stream members"), value=_list(contents.members)),
        ViewField(label=say("Stream policy"), value=_text(contents.policy)),
    ]
    return DocumentView(
        header=ViewHeader(
            title=summary.name,
            subtitle=text(say("Stream")),
            state=_state(state),
        ),
        blocks=[
            _overview(fields),
            _arguments(contents.arguments),
            _consumers(contents.consumers),
        ],
    )


def _exchange(
    summary: NodeSummary,
    contents: AmqpExchangeContents,
    messages_in: int | None,
    messages_out: int | None,
) -> DocumentView:
    fields = [
        ViewField(
            label=say("Messages published to exchange"),
            value=_number(messages_in),
        ),
        ViewField(
            label=say("Messages routed from exchange"),
            value=_number(messages_out),
        ),
        ViewField(label=say("Durable"), value=BooleanValue(value=contents.durable)),
        ViewField(label=say("Auto delete"), value=BooleanValue(value=contents.auto_delete)),
        ViewField(label=say("Internal"), value=BooleanValue(value=contents.internal)),
        ViewField(label=say("Incoming rate"), value=_rate(contents.rate_in)),
        ViewField(label=say("Outgoing rate"), value=_rate(contents.rate_out)),
    ]
    return DocumentView(
        header=ViewHeader(title=summary.name, subtitle=text(contents.exchange_type)),
        blocks=[_overview(fields), _arguments(contents.arguments)],
    )


def _overview(fields: list[ViewField]) -> SectionBlock:
    return SectionBlock(title=say("Overview"), blocks=[FieldsBlock(fields=fields)])


def _arguments(arguments: list[AmqpSetting]) -> SectionBlock:
    values = [
        ViewPair(name=one.name[:MAX_TEXT], value=one.value[:MAX_TEXT])
        for one in arguments
    ]
    return SectionBlock(title=say("Arguments"), blocks=[pairs(values)])


def _consumers(consumers: list[AmqpConsumer]) -> SectionBlock:
    rows: list[list[ViewValue]] = [
        [
            text(one.tag),
            _code(one.channel),
            _number(one.prefetch),
            BooleanValue(value=one.acknowledges),
            BooleanValue(value=one.active) if one.active is not None else EmptyValue(),
        ]
        for one in consumers
    ]
    return SectionBlock(
        title=say("Consumers"),
        blocks=[
            table(
                [
                    say("Consumer tag"),
                    say("Consumer channel"),
                    say("Consumer prefetch"),
                    say("Consumer acknowledgement"),
                    say("Consumer active"),
                ],
                rows,
            )
        ],
    )


def _state(state: str | None) -> StateValue | None:
    if state is None:
        return None
    word = _STATE_WORDS.get(state.lower())
    if word is None:
        word = state[:200]
    else:
        word = say(word)
    return StateValue(word=word, tone=_STATE_TONES.get(state.lower(), "neutral"))


def _number(value: int | None) -> NumberValue | EmptyValue:
    return EmptyValue() if value is None else NumberValue(value=float(value))


def _rate(value: float | None) -> NumberValue | EmptyValue:
    return EmptyValue() if value is None else NumberValue(value=value, unit=say("messages/s"))


def _text(value: str | None) -> ViewValue:
    return EmptyValue() if value is None else text(value)


def _code(value: str | None) -> ViewValue:
    return EmptyValue() if value is None else code(value)


def _list(values: list[str]) -> ViewValue:
    return chips(values) if values else EmptyValue()
