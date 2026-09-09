import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.plans import (
    ChunkIntervalPlan,
    IntervalStrategy,
    IntervalTarget,
    TimeDuration,
)


def plan() -> ChunkIntervalPlan:
    return ChunkIntervalPlan(
        target=IntervalTarget(
            database_oid="42", relation_oid="123", schema_name="lab", table_name="events",
            dimension_number=1, column_name="time", column_type="timestamp with time zone",
            current_interval="7 days",
        ),
        interval=TimeDuration(amount=2, unit="day"),
        strategy=IntervalStrategy(
            extension_version="2.18.0", function_oid="456", function_schema="public",
            dimensions_view_oid="789",
        ),
    )


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "2", 2_147_483_648])
def test_duration_refuses_non_positive_or_non_integer_amounts(amount: object) -> None:
    with pytest.raises(ValidationError):
        TimeDuration.model_validate({"amount": amount, "unit": "day"})


def test_duration_keeps_calendar_units_and_refuses_sql() -> None:
    assert TimeDuration(amount=2, unit="month").interval_value() == "2 month"
    with pytest.raises(ValidationError):
        TimeDuration.model_validate({"amount": 1, "unit": "day'; DROP TABLE events; --"})
    with pytest.raises(ValidationError):
        TimeDuration.model_validate({"amount": 1, "unit": "day", "sql": "SELECT 1"})


@pytest.mark.parametrize("field,value", [
    ("relation_oid", "124"), ("database_oid", "43"), ("current_interval", "1 day"),
    ("column_name", "other_time"), ("dimension_number", 2),
])
def test_a_changed_target_invalidates_review(field: str, value: object) -> None:
    reviewed = plan()
    raw = reviewed.model_dump()
    raw["target"][field] = value
    with pytest.raises(ActionRefused, match="review it again"):
        ChunkIntervalPlan.model_validate(raw).require_unchanged(reviewed.fingerprint())


def test_changed_parameters_or_api_invalidate_review() -> None:
    reviewed = plan()
    for section, field, value in [
        ("interval", "amount", 3), ("strategy", "extension_version", "2.17.2"),
        ("strategy", "function_oid", "457"), ("strategy", "function_schema", "extensions"),
        ("strategy", "dimensions_view_oid", "790"),
    ]:
        raw = reviewed.model_dump()
        raw[section][field] = value
        with pytest.raises(ActionRefused):
            ChunkIntervalPlan.model_validate(raw).require_unchanged(reviewed.fingerprint())


def test_round_trip_preserves_fingerprint_and_impact() -> None:
    reviewed = plan()
    reread = ChunkIntervalPlan.model_validate_json(reviewed.model_dump_json())
    reread.require_unchanged(reviewed.fingerprint())
    assert "existing chunks are not repartitioned" in reread.impact


@pytest.mark.parametrize("fingerprint", ["", "f" * 63, "f" * 65, "я" * 64])
def test_malformed_fingerprints_are_safe_conflicts(fingerprint: str) -> None:
    with pytest.raises(ActionRefused):
        plan().require_unchanged(fingerprint)
