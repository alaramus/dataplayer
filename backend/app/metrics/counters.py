"""Growing counters stored as their increments.

A byte count since boot only climbs; on a shared axis it presses every other
line onto the floor. The counter is replaced by its increment, computed once
here. The previous sample lives in memory, so the first packet after a restart
yields nothing for a counter.
"""

from collections.abc import Hashable, Sequence
from dataclasses import replace

from app.adapters.metrics import MetricSample
from app.metrics.packets import Sample

INCREMENT_SUFFIX = "_delta"

COUNTER_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {("net", "read"), ("net", "transfer")}
)


class CounterState:
    """The previous sample of every counter, per reporting source."""

    def __init__(self) -> None:
        self._previous: dict[tuple[Hashable, str, str, str], tuple[int, float]] = {}

    def expand(self, source: Hashable, samples: list[Sample]) -> list[Sample]:
        result: list[Sample] = []
        for sample in samples:
            if (sample.metric, sample.field) not in COUNTER_FIELDS:
                result.append(sample)
                continue
            key = (source, sample.metric, sample.field, sample.label)
            previous = self._previous.get(key)
            self._previous[key] = (sample.ts, sample.value)
            if previous is None:
                continue
            previous_ts, previous_value = previous
            # Out of order, or the counter restarted: the increment is unknowable.
            if sample.ts <= previous_ts or sample.value < previous_value:
                continue
            result.append(
                replace(
                    sample,
                    field=sample.field + INCREMENT_SUFFIX,
                    value=sample.value - previous_value,
                )
            )
        return result


class RateState:
    """Counters a connection reports, turned into rates per second.

    A connection is polled on an interval its owner chose, so an increment per
    poll would change its meaning with the interval; a rate does not.
    """

    def __init__(self) -> None:
        self._previous: dict[tuple[Hashable, str, str, str], tuple[int, float]] = {}

    def expand(self, source: Hashable, ts: int, readings: Sequence[MetricSample]) -> list[Sample]:
        result: list[Sample] = []
        for reading in readings:
            if not reading.counter:
                result.append(
                    Sample(reading.metric, reading.field, reading.label, reading.unit, ts, reading.value)
                )
                continue
            key = (source, reading.metric, reading.field, reading.label)
            previous = self._previous.get(key)
            self._previous[key] = (ts, reading.value)
            if previous is None:
                continue
            previous_ts, previous_value = previous
            if ts <= previous_ts or reading.value < previous_value:
                continue
            unit = f"{reading.unit}/s" if reading.unit else "/s"
            rate = (reading.value - previous_value) / (ts - previous_ts)
            result.append(Sample(reading.metric, reading.field, reading.label, unit, ts, rate))
        return result
