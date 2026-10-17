"""How dense an answer about a range is, and which table holds it.

Pure, so the rule can be read without the store around it.
"""

from dataclasses import dataclass
from typing import Literal

from app.core.translation import say
from app.metrics.models import MAX_RANGE_SECONDS, MIN_RANGE_SECONDS

# Widths a person reads without arithmetic. The first one wide enough wins.
BUCKET_LADDER: tuple[int, ...] = (
    10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400,
)
DAY = 86400

TierName = Literal["raw", "5m", "1h"]


@dataclass(frozen=True, slots=True)
class Tier:
    name: TierName
    # The width of what it holds; 0 for samples as they came.
    width: int
    # How long the store keeps it.
    kept: int


# What migrations 2 and 3 made, finest first. A test reads the store's
# policies back against these.
RAW = Tier("raw", 0, 7 * DAY)
ROLLUPS: tuple[Tier, ...] = (Tier("5m", 300, 35 * DAY), Tier("1h", 3600, 400 * DAY))
TIERS: tuple[Tier, ...] = (RAW, *ROLLUPS)


@dataclass(frozen=True, slots=True)
class Density:
    # None for raw samples; the width of a bucket otherwise.
    bucket_seconds: int | None
    tier: TierName


class RangeRefused(ValueError):
    pass


def check_range(start: int, end: int) -> None:
    span = end - start
    if span < MIN_RANGE_SECONDS:
        raise RangeRefused(say("A range is at least {count} seconds", count=MIN_RANGE_SECONDS))
    if span > MAX_RANGE_SECONDS:
        raise RangeRefused(say("A range is at most a year"))


def raw_reaches(start: int, now: int) -> bool:
    """Whether raw samples still go back as far as the range starts."""
    return start >= now - RAW.kept


def density(start: int, end: int, max_points: int, densest: int | None, now: int) -> Density:
    """Raw when the densest series fits and raw samples reach the start; buckets
    otherwise, read from the coarsest table that still holds the start and
    divides the width.

    `densest` is None when it was not counted, because raw samples do not reach
    that far. The width is at least the range divided by the budget, so no
    series comes back with more points than asked for.
    """
    if densest is not None and densest <= max_points and raw_reaches(start, now):
        return Density(None, "raw")
    width = _ladder_width(-(-(end - start) // max_points))
    holding = [tier for tier in TIERS if start >= now - tier.kept] or [TIERS[-1]]
    for tier in reversed(holding):
        if tier.width <= width and (tier.width == 0 or width % tier.width == 0):
            return Density(width, tier.name)
    # A range older than the finer tables keep, asked at a width finer than
    # what still holds it: as fine as that table goes.
    finest = holding[0]
    return Density(-(-width // finest.width) * finest.width, finest.name)


def _ladder_width(wanted: int) -> int:
    for width in BUCKET_LADDER:
        if width >= wanted:
            return width
    return -(-wanted // DAY) * DAY
