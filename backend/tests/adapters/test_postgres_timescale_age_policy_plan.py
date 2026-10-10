from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import age_policy_plan
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
    AgePolicyState,
)
from app.adapters.postgres.timescale.api import ExtensionRoutine, RoutineShape
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    AgePolicyPlan,
    AgePolicyStrategy,
    TimeDuration,
    TimeHypertable,
)
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

TARGET = TimeHypertable(
    database_oid="42", relation_oid="123", schema_name="lab", table_name="events",
    column_name="time", column_type="timestamp with time zone",
)
POLICY_ROW: dict[str, object] = {
    "job_id": "1000", "scheduled": True, "schedule_interval": "1 day",
    "older_than": "10 years", "created_before": None,
}
POLICY = AgePolicy.model_validate(POLICY_ROW)
TEN_YEARS = TimeDuration(amount=10, unit="year")
SPECS = [pytest.param(RETENTION, id="retention"), pytest.param(COMPRESSION, id="compression")]


def strategy(spec: AgePolicySpec, version: str = "2.18.0") -> AgePolicyStrategy:
    return AgePolicyStrategy.model_validate({
        "kind": spec.kind, "extension_version": version, "function_schema": "public",
        "add_function_oid": "456", "remove_function_oid": "457",
    })


def state(
    spec: AgePolicySpec = RETENTION, *, existing: AgePolicy | None = POLICY,
    column_type: str = "timestamp with time zone",
) -> AgePolicyState:
    target = TARGET.model_copy(update={"column_type": column_type})
    return AgePolicyState(target=target, existing=existing, strategy=strategy(spec))


def reads(spec: AgePolicySpec, existing: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    enabled: list[list[dict[str, object]]] = [[{"compression_enabled": True}]] if spec.requires_compression else []
    return [*enabled, existing]


@dataclass
class Sources:
    discover: AsyncMock
    target: AsyncMock
    views: AsyncMock
    routine: AsyncMock


def routine(_reader: object, _version: str, shape: RoutineShape) -> ExtensionRoutine:
    return ExtensionRoutine(oid="456" if shape.name.startswith("add_") else "457", schema_name="public")


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> Sources:
    mocks = Sources(
        discover=AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        ))),
        target=AsyncMock(return_value=TARGET), views=AsyncMock(),
        routine=AsyncMock(side_effect=routine),
    )
    monkeypatch.setattr(age_policy_plan, "discover", mocks.discover)
    monkeypatch.setattr(age_policy_plan, "time_hypertable", mocks.target)
    monkeypatch.setattr(age_policy_plan, "require_public_view", mocks.views)
    monkeypatch.setattr(age_policy_plan, "extension_routine", mocks.routine)
    return mocks


@pytest.mark.parametrize("spec", SPECS)
async def test_inspection_reads_the_owned_policy_by_bound_identity(sources: Sources, spec: AgePolicySpec) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(spec, [POLICY_ROW])
    inspected = await age_policy_plan.inspect_age_policy(reader, spec, "lab", "events")
    assert inspected == AgePolicyState(target=TARGET, existing=POLICY, strategy=strategy(spec))
    statement, params = reader.query.await_args.args
    assert statement == age_policy_plan._EXISTING[spec.kind]
    assert params == ("lab", "events")
    assert all(call.kwargs == {"inspection": True} for call in reader.query.await_args_list)
    sources.target.assert_awaited_once_with(reader, "lab", "events")
    assert [call.args[2] for call in sources.routine.await_args_list] == [spec.add, spec.remove]
    assert "jobs" in {call.args[1] for call in sources.views.await_args_list}


def test_each_kind_reads_only_its_own_owned_job_with_validated_thresholds() -> None:
    retention = age_policy_plan._EXISTING["retention"]
    compression = age_policy_plan._EXISTING["compression"]
    assert "'policy_retention'" in retention and "'drop_after'" in retention and "compress" not in retention
    assert "'policy_compression'" in compression and "'compress_after'" in compression
    assert "drop_" not in compression
    for statement in (retention, compression):
        # The interval and integer forms of the age, and the creation-time threshold.
        assert statement.count("OPERATOR(pg_catalog.~)") == 3
        assert "= 'number'" in statement
        assert "deptype = 'e'" in statement
        assert "source.config AS" not in statement and "source.config," not in statement


@pytest.mark.parametrize("version", ["2.14.2", "2.17.2", "2.18.0", "2.30.0"])
async def test_every_version_asks_for_the_arguments_it_passes(sources: Sources, version: str) -> None:
    # add_compression_policy has gained and lost a trailing argument between releases,
    # so only the three the execution passes are asked for, whatever the version.
    sources.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version=version,
    ))
    reader = AsyncMock()
    reader.query.side_effect = reads(COMPRESSION, [])
    inspected = await age_policy_plan.inspect_age_policy(reader, COMPRESSION, "lab", "events")
    added = sources.routine.await_args_list[0].args[2]
    assert (added.name, added.argument_types) == ("add_compression_policy", "2205 2276 16")
    assert inspected.strategy.extension_version == version


@pytest.mark.parametrize("rows", [[], [{"compression_enabled": False}], [{"compression_enabled": None}]])
async def test_compression_policy_requires_compression_enabled(
    sources: Sources, rows: list[dict[str, object]],
) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match="Enable compression"):
        await age_policy_plan.inspect_age_policy(reader, COMPRESSION, "lab", "events")
    assert reader.query.await_count == 1
    sources.routine.assert_not_awaited()


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.usefixtures("sources")
async def test_no_policy_is_an_empty_state(spec: AgePolicySpec) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(spec, [])
    assert (await age_policy_plan.inspect_age_policy(reader, spec, "lab", "events")).existing is None


@pytest.mark.usefixtures("sources")
async def test_several_policies_refuse() -> None:
    reader = AsyncMock()
    reader.query.return_value = [POLICY_ROW, {**POLICY_ROW, "job_id": "1001"}]
    with pytest.raises(ActionRefused, match="several retention policy jobs"):
        await age_policy_plan.inspect_age_policy(reader, RETENTION, "lab", "events")


@pytest.mark.parametrize("row", [
    {**POLICY_ROW, "older_than": None},
    {**POLICY_ROW, "created_before": "30 days"},
    {**POLICY_ROW, "job_id": "abc"},
    {**POLICY_ROW, "scheduled": "yes"},
    {**POLICY_ROW, "config": {"drop_after": "10 years"}},
])
@pytest.mark.usefixtures("sources")
async def test_unreadable_policy_refuses(row: dict[str, object]) -> None:
    reader = AsyncMock()
    reader.query.return_value = [row]
    with pytest.raises(ActionRefused, match="could not be read safely"):
        await age_policy_plan.inspect_age_policy(reader, RETENTION, "lab", "events")


@pytest.mark.parametrize("feature,message", [
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="unsupported", installed_version="2.18.0",
                   reason="Incomplete"), "Incomplete"),
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="unsupported", installed_version="3.0.0",
                   reason="This TimescaleDB major version is not supported"), "major version"),
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="absent"), "is not installed"),
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="unavailable",
                   reason="This connection may not inspect installed extensions"), "may not inspect"),
])
async def test_unavailable_or_missing_extension_refuses_before_reads(
    sources: Sources, feature: SourceFeature, message: str,
) -> None:
    sources.discover.return_value = TimescaleProfile(feature)
    reader = AsyncMock()
    with pytest.raises(ActionRefused, match=message):
        await age_policy_plan.inspect_age_policy(reader, RETENTION, "lab", "events")
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
        await age_policy_plan.inspect_age_policy(reader, RETENTION, "lab", "events")
    assert "secret" not in caught.value.message


async def test_target_refusal_keeps_its_reason(sources: Sources) -> None:
    sources.target.side_effect = ActionRefused(
        "not_applicable", "Only timestamp and date dimensions are supported here",
    )
    with pytest.raises(ActionRefused, match="timestamp and date"):
        await age_policy_plan.inspect_age_policy(AsyncMock(), RETENTION, "lab", "integer_events")


@pytest.mark.parametrize("spec", SPECS)
def test_first_policy_is_set_and_an_existing_one_is_replaced_explicitly(spec: AgePolicySpec) -> None:
    first = age_policy_plan.age_policy_plan(spec, state(spec, existing=None), TEN_YEARS)
    assert (first.operation, first.kind, first.existing, first.older_than) == (
        "set_policy", spec.kind, None, TEN_YEARS,
    )
    replacement = age_policy_plan.age_policy_plan(spec, state(spec), TEN_YEARS)
    assert replacement.existing == POLICY
    assert replacement.fingerprint() != first.fingerprint()


@pytest.mark.parametrize("spec", SPECS)
def test_paused_policy_can_be_removed_but_not_silently_resumed(spec: AgePolicySpec) -> None:
    paused = POLICY.model_copy(update={"scheduled": False})
    with pytest.raises(ActionRefused, match=f"existing {spec.noun} is paused"):
        age_policy_plan.age_policy_plan(spec, state(spec, existing=paused), TEN_YEARS)
    removal = age_policy_plan.age_policy_plan(spec, state(spec, existing=paused), None)
    assert removal.operation == "remove_policy"


@pytest.mark.parametrize("spec", SPECS)
def test_removal_requires_a_policy(spec: AgePolicySpec) -> None:
    with pytest.raises(ActionRefused, match=f"no {spec.noun}"):
        age_policy_plan.age_policy_plan(spec, state(spec, existing=None), None)


@pytest.mark.parametrize("column_type,unit,allowed", [
    ("date", "hour", False), ("date", "day", True), ("date", "month", True),
    ("timestamp with time zone", "hour", True),
])
def test_date_dimensions_take_whole_days(column_type: str, unit: str, allowed: bool) -> None:
    duration = TimeDuration.model_validate({"amount": 3, "unit": unit})
    current = state(column_type=column_type)
    if allowed:
        assert age_policy_plan.age_policy_plan(RETENTION, current, duration).older_than == duration
    else:
        with pytest.raises(ActionRefused, match="whole days"):
            age_policy_plan.age_policy_plan(RETENTION, current, duration)


@pytest.mark.parametrize("section,field,value", [
    ("target", "relation_oid", "124"), ("existing", "job_id", "1001"),
    ("existing", "schedule_interval", "2 days"), ("existing", "older_than", "20 years"),
    ("strategy", "add_function_oid", "458"),
])
def test_every_planned_fact_is_fingerprinted(section: str, field: str, value: str) -> None:
    plan = age_policy_plan.age_policy_plan(RETENTION, state(), TEN_YEARS)
    changed = plan.model_dump()
    changed[section][field] = value
    with pytest.raises(ActionRefused, match="review it again"):
        AgePolicyPlan.model_validate(changed).require_unchanged(plan.fingerprint())
    plan.require_unchanged(age_policy_plan.age_policy_plan(RETENTION, state(), TEN_YEARS).fingerprint())


def test_same_threshold_on_another_kind_is_another_plan() -> None:
    retention = age_policy_plan.age_policy_plan(RETENTION, state(RETENTION), TEN_YEARS)
    compression = age_policy_plan.age_policy_plan(COMPRESSION, state(COMPRESSION), TEN_YEARS)
    assert retention.fingerprint() != compression.fingerprint()


@pytest.mark.parametrize("operation,kind,existing,older_than,strategy_spec", [
    ("remove_policy", "retention", None, None, RETENTION),
    ("remove_policy", "retention", POLICY, TEN_YEARS, RETENTION),
    ("set_policy", "retention", POLICY, None, RETENTION),
    ("set_policy", "retention", POLICY, TEN_YEARS, COMPRESSION),
])
def test_inconsistent_plan_is_not_a_plan(
    operation: str, kind: str, existing: AgePolicy | None, older_than: TimeDuration | None,
    strategy_spec: AgePolicySpec,
) -> None:
    with pytest.raises(ValidationError):
        AgePolicyPlan.model_validate({
            "operation": operation, "kind": kind, "target": TARGET, "existing": existing,
            "older_than": older_than, "strategy": strategy(strategy_spec),
        })


@pytest.mark.parametrize("spec,set_impact,remove_impact", [
    (RETENTION, "after this session ends", "chunks already dropped do not return"),
    (COMPRESSION, "compressed chunks stay readable", "chunks already compressed stay compressed"),
])
def test_plan_states_its_impact_and_rejects_unknown_fields(
    spec: AgePolicySpec, set_impact: str, remove_impact: str,
) -> None:
    plan = age_policy_plan.age_policy_plan(spec, state(spec), TEN_YEARS)
    with pytest.raises(ValidationError):
        AgePolicyPlan.model_validate({**plan.model_dump(), "statement": "DROP TABLE x"})
    assert set_impact in plan.impact
    assert remove_impact in age_policy_plan.age_policy_plan(spec, state(spec), None).impact
    assert "coordination" in plan.model_dump()
