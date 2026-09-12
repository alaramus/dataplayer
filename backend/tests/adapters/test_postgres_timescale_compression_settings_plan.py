from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import compression_settings_plan
from app.adapters.postgres.timescale.compression_settings_plan import (
    effective_order_by,
    order_option,
    resolve_settings,
    segment_option,
)
from app.adapters.postgres.timescale.plans import (
    CompressionSettingsPlan,
    OrderColumn,
    TimeHypertable,
)
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

TARGET = TimeHypertable(
    database_oid="42", relation_oid="123", schema_name="lab", table_name="events",
    column_name="observed_at", column_type="timestamp with time zone",
)
COLUMNS = ["observed_at", "device", "value", "my col desc"]
TIME_DESC = OrderColumn(column="observed_at", descending=True, nulls_first=True)


def test_lines_resolve_to_known_columns_with_postgresql_null_defaults() -> None:
    segment_by, order_by = resolve_settings(
        "device\n\n", "value desc\nobserved_at ASC NULLS FIRST\nmy col desc", COLUMNS,
    )
    assert segment_by == ("device",)
    assert order_by == (
        OrderColumn(column="value", descending=True, nulls_first=True),
        OrderColumn(column="observed_at", descending=False, nulls_first=True),
        OrderColumn(column="my col desc", descending=False, nulls_first=False),
    )


@pytest.mark.parametrize("line,expected", [
    ("value", OrderColumn(column="value", descending=False, nulls_first=False)),
    ("value DESC", OrderColumn(column="value", descending=True, nulls_first=True)),
    ("value asc nulls first", OrderColumn(column="value", descending=False, nulls_first=True)),
    ("value desc nulls last", OrderColumn(column="value", descending=True, nulls_first=False)),
    ("my col desc desc", OrderColumn(column="my col desc", descending=True, nulls_first=True)),
])
def test_sort_words_follow_the_column(line: str, expected: OrderColumn) -> None:
    assert resolve_settings("", line, COLUMNS)[1] == (expected,)


@pytest.mark.parametrize("segment,order,message", [
    ("missing", "", 'no column "missing"'),
    ("", "value; DROP TABLE x", "no column"),
    ("", "lower(value)", "no column"),
    ("", 'value" DESC, "device', "no column"),
    ("device", "device", "more than once"),
    ("", "value\nvalue desc", "more than once"),
    ("\n".join(["value"] * 33), "", "at most 32"),
    ("x" * 101, "", "one column"),
])
def test_anything_but_listed_columns_is_refused(segment: str, order: str, message: str) -> None:
    with pytest.raises(ActionRefused, match=message):
        resolve_settings(segment, order, COLUMNS)


def test_time_column_is_appended_unless_either_list_names_it() -> None:
    assert effective_order_by(TARGET, (), ()) == (TIME_DESC,)
    assert effective_order_by(TARGET, ("observed_at",), ()) == ()
    named = (OrderColumn(column="observed_at", descending=False, nulls_first=False),)
    assert effective_order_by(TARGET, (), named) == named
    value = OrderColumn(column="value", descending=True, nulls_first=True)
    assert effective_order_by(TARGET, ("device",), (value,)) == (value, TIME_DESC)


def test_options_are_quoted_identifiers_and_fixed_keywords() -> None:
    assert segment_option(('odd"name', "device")) == '"odd""name", "device"'
    assert segment_option(()) == ""
    assert order_option((
        OrderColumn(column="value", descending=True, nulls_first=False),
        OrderColumn(column='a"b', descending=False, nulls_first=True),
    )) == '"value" DESC NULLS LAST, "a""b" ASC NULLS FIRST'


@dataclass
class Sources:
    discover: AsyncMock
    target: AsyncMock
    views: AsyncMock


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> Sources:
    mocks = Sources(
        discover=AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        ))),
        target=AsyncMock(return_value=TARGET), views=AsyncMock(),
    )
    monkeypatch.setattr(compression_settings_plan, "discover", mocks.discover)
    monkeypatch.setattr(compression_settings_plan, "time_hypertable", mocks.target)
    monkeypatch.setattr(compression_settings_plan, "require_public_view", mocks.views)
    return mocks


def reads(
    *, enabled: object = False, current: dict[str, object] | None = None,
    compressed: object = False, unique: tuple[str, ...] = (),
) -> list[list[dict[str, object]]]:
    return [
        [{"name": name} for name in COLUMNS],
        [{"compression_enabled": enabled}],
        [current or {"segmentby": None, "orderby": None}],
        [{"any_compressed": compressed}],
        [{"name": name} for name in unique],
    ]


async def plan(reader: AsyncMock, segment: str = "", order: str = "") -> CompressionSettingsPlan:
    return await compression_settings_plan.plan_compression_settings(reader, "lab", "events", segment, order)


async def test_first_enable_reads_only_bound_identities(sources: Sources) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(unique=("value", "observed_at"))
    planned = await plan(reader, "device")
    assert (planned.enabled, planned.current_segment_by, planned.current_order_by) == (False, None, None)
    assert (planned.segment_by, planned.order_by) == (("device",), (TIME_DESC,))
    assert planned.unsegmented_unique == ("value",)
    assert planned.strategy.extension_version == "2.18.0"
    calls = reader.query.await_args_list
    assert [call.args[0] for call in calls] == [
        compression_settings_plan._COLUMNS, compression_settings_plan._ENABLED,
        compression_settings_plan._CURRENT, compression_settings_plan._COMPRESSED,
        compression_settings_plan._UNIQUE,
    ]
    assert [call.args[1] for call in calls] == [
        ("123",), ("lab", "events"), ("123",), ("lab", "events"), ("123",),
    ]
    assert all(call.kwargs == {"inspection": True} for call in calls)
    assert {call.args[1] for call in sources.views.await_args_list} == {
        "hypertables", "hypertable_compression_settings", "chunks",
    }


@pytest.mark.usefixtures("sources")
async def test_change_keeps_current_settings_in_the_plan() -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(
        enabled=True, current={"segmentby": "device", "orderby": "observed_at DESC"},
        compressed=True, unique=("value",),
    )
    planned = await plan(reader, "", "value desc")
    assert (planned.current_segment_by, planned.current_order_by) == ("device", "observed_at DESC")
    assert planned.any_compressed
    assert planned.unsegmented_unique == ()
    assert planned.order_by == (OrderColumn(column="value", descending=True, nulls_first=True), TIME_DESC)
    assert "keep theirs" in planned.impact


@pytest.mark.usefixtures("sources")
async def test_unknown_column_refuses_before_further_reads() -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads()
    with pytest.raises(ActionRefused, match='no column "missing"'):
        await plan(reader, "missing")
    assert reader.query.await_count == 1


@pytest.mark.parametrize("change", [
    {"enabled": None}, {"compressed": "yes"}, {"current": {}},
])
@pytest.mark.usefixtures("sources")
async def test_unreadable_state_refuses(change: dict[str, object]) -> None:
    reader = AsyncMock()
    answers = reads(**{key: value for key, value in change.items() if key != "current"})
    if "current" in change:
        answers[2] = []
    reader.query.side_effect = answers
    with pytest.raises(ActionRefused, match="could not be"):
        await plan(reader)


async def test_unavailable_extension_refuses_before_reads(sources: Sources) -> None:
    sources.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="unsupported", installed_version="2.18.0",
        reason="The installed version lacks the supported inspection API",
    ))
    reader = AsyncMock()
    with pytest.raises(ActionRefused, match="lacks the supported inspection API"):
        await plan(reader)
    reader.query.assert_not_called()
    sources.target.assert_not_awaited()


@pytest.mark.parametrize("error", [
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
@pytest.mark.usefixtures("sources")
async def test_inspection_failure_is_safe(error: Exception) -> None:
    reader = AsyncMock()
    reader.query.side_effect = error
    with pytest.raises(ActionRefused) as caught:
        await plan(reader)
    assert "secret" not in caught.value.message


@pytest.mark.parametrize("field,value", [
    ("current_order_by", "observed_at"), ("any_compressed", True), ("segment_by", ("value",)),
    ("enabled", True), ("unsegmented_unique", ()),
])
@pytest.mark.usefixtures("sources")
async def test_every_planned_fact_is_fingerprinted(field: str, value: object) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(unique=("value",))
    planned = await plan(reader, "device")
    changed = CompressionSettingsPlan.model_validate({**planned.model_dump(), field: value})
    with pytest.raises(ActionRefused, match="review it again"):
        changed.require_unchanged(planned.fingerprint())


@pytest.mark.usefixtures("sources")
async def test_plan_rejects_unknown_fields() -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads()
    planned = await plan(reader)
    with pytest.raises(ValidationError):
        CompressionSettingsPlan.model_validate({**planned.model_dump(), "statement": "ALTER TABLE x"})
    assert "Nothing is compressed now" in planned.impact
