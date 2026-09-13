"""How dense an answer about a range is: raw samples, or buckets of what width.

Pure, so the rule can be read without the store around it.
"""

from app.metrics.models import MAX_RANGE_SECONDS, MIN_RANGE_SECONDS

# Widths a person reads without arithmetic. The first one wide enough wins.
BUCKET_LADDER: tuple[int, ...] = (
    10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400,
)
DAY = 86400


class RangeRefused(ValueError):
    pass


def check_range(start: int, end: int) -> None:
    span = end - start
    if span < MIN_RANGE_SECONDS:
        raise RangeRefused(f"A range is at least {MIN_RANGE_SECONDS} seconds")
    if span > MAX_RANGE_SECONDS:
        raise RangeRefused("A range is at most a year")


def bucket_seconds(start: int, end: int, max_points: int, densest: int) -> int | None:
    """None when the densest series fits as it is; a bucket width otherwise.

    The width is at least the range divided by the budget, so no series comes
    back with more points than asked for.
    """
    if densest <= max_points:
        return None
    wanted = -(-(end - start) // max_points)
    for width in BUCKET_LADDER:
        if width >= wanted:
            return width
    return -(-wanted // DAY) * DAY
