"""When a schedule comes next, in the owner's wall clock (D179)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.pipelines.schedule import ScheduleSettings
from app.pipelines.timing import next_time

RIGA = "Europe/Riga"


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def _settings(**chosen: Any) -> ScheduleSettings:
    return ScheduleSettings.model_validate({"enabled": True, "time_zone": RIGA, **chosen})


def test_an_interval_counts_from_when_it_was_switched_on() -> None:
    every = _settings(kind="interval", every_minutes=5)
    counted_from = _utc(2026, 9, 26, 10, 0)

    assert next_time(every, _utc(2026, 9, 26, 10, 0), counted_from) == _utc(2026, 9, 26, 10, 5)
    assert next_time(every, _utc(2026, 9, 26, 10, 7), counted_from) == _utc(2026, 9, 26, 10, 10)
    # Exactly on a time, the next one: a run is never started twice for one.
    assert next_time(every, _utc(2026, 9, 26, 10, 10), counted_from) == _utc(2026, 9, 26, 10, 15)
    daily = _settings(kind="interval", every_minutes=24 * 60)
    assert next_time(daily, _utc(2026, 9, 29, 9, 0), counted_from) == _utc(2026, 9, 29, 10, 0)


def test_times_of_the_day_are_the_owner_s_wall_clock() -> None:
    nightly = _settings(kind="times", times=["03:00"])

    # 03:00 in Riga in September is midnight in UTC.
    assert next_time(nightly, _utc(2026, 9, 26, 12, 0), _utc(2026, 9, 1)) == _utc(2026, 9, 27, 0, 0)
    tokyo = _settings(kind="times", times=["03:00"], time_zone="Asia/Tokyo")
    assert next_time(tokyo, _utc(2026, 9, 26, 12, 0), _utc(2026, 9, 1)) == _utc(2026, 9, 26, 18, 0)


def test_several_times_on_chosen_days() -> None:
    weekdays = _settings(kind="times", times=["18:00", "09:00"], days=[0, 1, 2, 3, 4])
    friday_evening = _utc(2026, 9, 25, 15, 0)  # 18:00 in Riga, a Friday

    assert weekdays.times == ["09:00", "18:00"]
    assert next_time(weekdays, friday_evening, _utc(2026, 9, 1)) == _utc(2026, 9, 28, 6, 0)
    assert next_time(weekdays, _utc(2026, 9, 28, 6, 0), _utc(2026, 9, 1)) == _utc(2026, 9, 28, 15, 0)


def test_a_time_the_clock_skips_runs_as_it_moves_past() -> None:
    # On 29 March 2026 Riga's clocks go from 03:00 to 04:00.
    skipped = _settings(kind="times", times=["03:30"])

    came = next_time(skipped, _utc(2026, 3, 28, 12, 0), _utc(2026, 3, 1))

    assert came == _utc(2026, 3, 29, 1, 0)
    assert next_time(skipped, came, _utc(2026, 3, 1)) == _utc(2026, 3, 30, 0, 30)


def test_a_time_the_clock_repeats_runs_once() -> None:
    # On 25 October 2026 Riga's clocks go back from 04:00 to 03:00.
    repeated = _settings(kind="times", times=["03:30"])

    came = next_time(repeated, _utc(2026, 10, 24, 12, 0), _utc(2026, 10, 1))

    assert came == _utc(2026, 10, 25, 0, 30)
    assert next_time(repeated, came, _utc(2026, 10, 1)) == _utc(2026, 10, 26, 1, 30)
    assert next_time(repeated, came, _utc(2026, 10, 1)) - came > timedelta(hours=24)


@pytest.mark.parametrize(
    "chosen",
    [
        {"kind": "interval", "every_minutes": 4},
        {"kind": "interval", "every_minutes": 7 * 24 * 60 + 1},
        {"kind": "times", "times": []},
        {"kind": "times", "days": []},
        {"kind": "times", "times": ["24:00"]},
        {"kind": "times", "times": [f"{hour:02}:00" for hour in range(13)]},
        {"time_zone": "Mars/Olympus"},
    ],
)
def test_what_a_schedule_cannot_be(chosen: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _settings(**chosen)
