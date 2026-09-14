"""Counters a connection reports, as rates per second (D127).

The previous reading lives in memory, so the first poll after a start yields
nothing for a counter. An agent sends rates of its own (D130) and passes
nothing through here.
"""

from collections.abc import Hashable, Sequence

from app.adapters.metrics import MetricSample
from app.metrics.store import Sample


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
            # Out of order, or the counter restarted: the rate is unknowable.
            if ts <= previous_ts or reading.value < previous_value:
                continue
            unit = f"{reading.unit}/s" if reading.unit else "/s"
            rate = (reading.value - previous_value) / (ts - previous_ts)
            result.append(Sample(reading.metric, reading.field, reading.label, unit, ts, rate))
        return result
