"""When a pipeline's schedule runs next (D179). Plain functions of the
schedule and the moment asked from, in the owner's wall clock.

A time the clock skips when it goes forward runs as the clock moves past it;
a time it repeats when it goes back runs once, the first time round.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.pipelines.schedule import ScheduleSettings

# Far enough for any day of the week to come round, and a skipped hour.
_DAYS_AHEAD = 9


def _hours_minutes(text: str) -> time:
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def _first_after_gap(before: datetime, after: datetime, zone: ZoneInfo) -> datetime:
    """The first minute, between two instants, on the far side of a clock change."""
    offset = after.astimezone(zone).utcoffset()
    low, high = before, after
    while high - low > timedelta(minutes=1):
        middle = low + (high - low) / 2
        if middle.astimezone(zone).utcoffset() == offset:
            high = middle
        else:
            low = middle
    return high.replace(second=0, microsecond=0)


def wall(day: date, at: time, zone: ZoneInfo) -> datetime:
    """A day's time in a zone, as an instant."""
    naive = datetime.combine(day, at)
    first = naive.replace(tzinfo=zone, fold=0)
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive:
        return first.astimezone(UTC)
    # Skipped by the clock going forward: fold 1 reads it by the offset
    # after, which lands before the change, and fold 0 after it.
    earlier = naive.replace(tzinfo=zone, fold=1).astimezone(UTC)
    later = first.astimezone(UTC)
    return _first_after_gap(min(earlier, later), max(earlier, later), zone)


def next_time(settings: ScheduleSettings, after: datetime, counted_from: datetime) -> datetime:
    """The first time the schedule comes, strictly after `after`."""
    if settings.kind == "interval":
        step = timedelta(minutes=settings.every_minutes)
        passed = max(0, int((after - counted_from) / step))
        at = counted_from + passed * step
        while at <= after:
            at += step
        return at
    zone = ZoneInfo(settings.time_zone)
    today = after.astimezone(zone).date()
    times = sorted(_hours_minutes(text) for text in settings.times)
    for ahead in range(_DAYS_AHEAD):
        day = today + timedelta(days=ahead)
        if day.weekday() not in settings.days:
            continue
        for clock in times:
            candidate = wall(day, clock, zone)
            if candidate > after:
                return candidate
    # The settings refuse no day and no time, so a week always holds one.
    raise ValueError("This schedule never comes")
