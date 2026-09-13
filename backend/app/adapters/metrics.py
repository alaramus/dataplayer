"""What a source reports about itself as metrics, and the layouts it declares (D128).

A capability like any other (D2): a driver that can say something about its own
health implements `SupportsMetrics`, and the metrics process polls the
connections whose owners switched reporting on. A sample is one reading; a
growing counter is marked as one, and the collector turns it into a rate, so no
driver has to remember its previous reading between polls.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

RecipeType = Literal["timeseries", "stat", "processes"]


@dataclass(frozen=True, slots=True)
class MetricSample:
    metric: str
    field: str
    value: float
    label: str = ""
    # Of the reading itself; a counter's rate is this per second.
    unit: str = ""
    # A count since some start, reported as its rate per second.
    counter: bool = False


@dataclass(frozen=True)
class MetricRecipe:
    """One widget of a ready-made layout: what to draw, never series ids."""

    type: RecipeType
    title: str
    # x, y, w, h on the twelve-column grid.
    layout: tuple[int, int, int, int]
    metric: str = ""
    # None: every field of the metric.
    fields: tuple[str, ...] | None = None


@dataclass(frozen=True)
class MetricPreset:
    key: str
    name: str
    description: str
    recipes: tuple[MetricRecipe, ...]


@runtime_checkable
class SupportsMetrics(Protocol):
    async def metric_samples(self) -> Sequence[MetricSample]: ...

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]: ...
