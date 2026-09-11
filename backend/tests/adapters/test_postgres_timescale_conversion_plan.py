from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import conversion_plan
from app.adapters.postgres.timescale.api import ExtensionRoutine, RoutineShape
from app.adapters.postgres.timescale.conversion_plan import ConversionState, TableIndex
from app.adapters.postgres.timescale.plans import (
    ConversionColumn,
    ConversionPlan,
    ConversionStrategy,
    ConversionTarget,
    TimeDuration,
)
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

RELATION: dict[str, object] = {
    "database_oid": "42", "relation_oid": "123", "schema_name": 'odd"schema', "table_name": "events",
    "relkind": "r", "persistence": "p", "owned": True, "readable": True,
    "inherits": False, "has_rules": False, "no_inherit_constraint": False,
}
TARGET = ConversionTarget(database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events")
OBSERVED = ConversionColumn(name="observed_at", type="timestamp with time zone", not_null=False)
DAY = ConversionColumn(name="day", type="date", not_null=True)
STRATEGY = ConversionStrategy(
    extension_version="2.18.0", function_schema="public", create_function_oid="456",
    by_range_function_oid="457", dimension_info_oid="99999",
)
WEEK = TimeDuration(amount=7, unit="day")


@dataclass
class Sources:
    discover: AsyncMock
    server: AsyncMock
    views: AsyncMock
    type_lookup: AsyncMock
    routine: AsyncMock


def routine(_reader: object, _version: str, shape: RoutineShape) -> ExtensionRoutine:
    return ExtensionRoutine(oid="456" if shape.name == "create_hypertable" else "457", schema_name="public")


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> Sources:
    mocks = Sources(
        discover=AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        ))),
        server=AsyncMock(), views=AsyncMock(), type_lookup=AsyncMock(return_value="99999"),
        routine=AsyncMock(side_effect=routine),
    )
    monkeypatch.setattr(conversion_plan, "discover", mocks.discover)
    monkeypatch.setattr(conversion_plan, "require_tested_server", mocks.server)
    monkeypatch.setattr(conversion_plan, "require_public_view", mocks.views)
    monkeypatch.setattr(conversion_plan, "extension_type", mocks.type_lookup)
    monkeypatch.setattr(conversion_plan, "extension_routine", mocks.routine)
    return mocks


def reads(
    *, relation: dict[str, object] | None = None, converted: bool = False, referenced: bool = False,
    columns: tuple[dict[str, object], ...] = (
        {"name": "observed_at", "type": "timestamp with time zone", "not_null": False},
    ),
    empty: bool = True, indexes: tuple[dict[str, object], ...] = (),
) -> list[list[dict[str, object]]]:
    return [
        [relation or RELATION], [{"converted": converted}], [{"references_hypertable": referenced}],
        list(columns), [{"empty": empty}], list(indexes),
    ]


async def test_inspection_reads_bound_identities_and_verifies_both_routines(sources: Sources) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(indexes=({"name": "events_pkey", "constrains": True, "columns": ["id", None]},))
    state = await conversion_plan.inspect_conversion(reader, 'odd"schema', "events")
    assert state == ConversionState(
        target=TARGET, columns=(OBSERVED,),
        indexes=(TableIndex(name="events_pkey", constrains=True, columns=("id", None)),), strategy=STRATEGY,
    )
    calls = reader.query.await_args_list
    assert [call.args[1] for call in calls] == [
        ('odd"schema', "events"), ('odd"schema', "events"), ("123", "123"), ("123",), None, ("123", 1001),
    ]
    assert calls[4].args[0] == 'SELECT NOT EXISTS (SELECT 1 FROM ONLY "odd""schema"."events") AS empty'
    assert all(call.kwargs == {"inspection": True} for call in calls)
    sources.type_lookup.assert_awaited_once_with(reader, "2.18.0", "_timescaledb_internal", "dimension_info")
    created, ranged = (call.args[2] for call in sources.routine.await_args_list)
    assert (created.argument_types, created.returns_set, created.exclusive) == ("2205 99999 16 16 16", True, False)
    assert (ranged.argument_types, ranged.result_type, ranged.exclusive) == ("19 2283 24", 99999, True)


@pytest.mark.parametrize("change,message", [
    ({"owned": False}, "owner"), ({"readable": False}, "may not read"),
    ({"relkind": "p"}, "Partitioned"), ({"relkind": "v"}, "ordinary table"),
    ({"no_inherit_constraint": True}, "NO INHERIT"), ({"inherits": True}, "inheritance"),
    ({"persistence": "u"}, "logged"), ({"persistence": "t"}, "logged"), ({"has_rules": True}, "rules"),
])
@pytest.mark.usefixtures("sources")
async def test_the_sources_refusals_are_named_before_its_api_is_touched(
    change: dict[str, object], message: str,
) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(relation={**RELATION, **change})
    with pytest.raises(ActionRefused, match=message):
        await conversion_plan.inspect_conversion(reader, "lab", "events")
    assert reader.query.await_count == 1


@pytest.mark.parametrize("change,message,reads_made", [
    ({"converted": True}, "already a hypertable", 2),
    ({"referenced": True}, "Foreign keys between this table and a hypertable", 3),
    ({"columns": ()}, "no timestamp or date column", 4),
    ({"empty": False}, "not empty", 5),
    ({"indexes": tuple({"name": f"i{n}", "constrains": False, "columns": ["x"]} for n in range(1001))},
     "too many indexes", 6),
])
async def test_table_facts_refuse_before_routines(
    sources: Sources, change: dict[str, object], message: str, reads_made: int,
) -> None:
    reader = AsyncMock()
    reader.query.side_effect = reads(**change)  # type: ignore[arg-type]  # parametrized overrides
    with pytest.raises(ActionRefused, match=message):
        await conversion_plan.inspect_conversion(reader, "lab", "events")
    assert reader.query.await_count == reads_made
    sources.routine.assert_not_awaited()


def test_only_no_inherit_checks_count_as_no_inherit_constraints() -> None:
    assert "table_constraint.contype = 'c'" in conversion_plan._RELATION


async def test_untested_extension_refuses_before_reads(sources: Sources) -> None:
    sources.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version="2.19.0",
    ))
    reader = AsyncMock()
    with pytest.raises(ActionRefused, match="No supported"):
        await conversion_plan.inspect_conversion(reader, "lab", "events")
    reader.query.assert_not_called()


@pytest.mark.parametrize("error", [
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
@pytest.mark.usefixtures("sources")
async def test_inspection_failure_is_safe(error: Exception) -> None:
    reader = AsyncMock()
    reader.query.side_effect = error
    with pytest.raises(ActionRefused) as caught:
        await conversion_plan.inspect_conversion(reader, "lab", "events")
    assert "secret" not in caught.value.message


def state(*indexes: TableIndex) -> ConversionState:
    return ConversionState(target=TARGET, columns=(OBSERVED, DAY), indexes=indexes, strategy=STRATEGY)


def test_unknown_column_names_the_choices() -> None:
    with pytest.raises(ActionRefused, match="of this table: observed_at, day"):
        conversion_plan.conversion_plan(state(), "value", WEEK)


@pytest.mark.parametrize("column,unit,message", [
    ("observed_at", "month", "Calendar"), ("day", "hour", "whole days"),
])
def test_interval_must_fit_the_column(column: str, unit: str, message: str) -> None:
    with pytest.raises(ActionRefused, match=message):
        conversion_plan.conversion_plan(state(), column, TimeDuration.model_validate({"amount": 1, "unit": unit}))


@pytest.mark.parametrize("columns", [("id",), ("id", None), (None,)])
def test_unique_index_without_the_time_column_is_refused(columns: tuple[str | None, ...]) -> None:
    with pytest.raises(ActionRefused, match='Unique index "events_pkey" must include "observed_at"'):
        conversion_plan.conversion_plan(
            state(TableIndex(name="events_pkey", constrains=True, columns=columns)), "observed_at", WEEK,
        )


@pytest.mark.parametrize("indexes,exists", [
    ((), False),
    ((TableIndex(name="plain", constrains=False, columns=("value",)),), False),
    ((TableIndex(name="pair", constrains=True, columns=("observed_at", "value")),), False),
    ((TableIndex(name="alone", constrains=False, columns=("observed_at",)),), True),
])
def test_only_a_one_column_time_index_counts_as_existing(indexes: tuple[TableIndex, ...], exists: bool) -> None:
    planned = conversion_plan.conversion_plan(state(*indexes), "observed_at", WEEK)
    assert planned.time_index_exists is exists
    assert (planned.column, planned.interval) == (OBSERVED, WEEK)


@pytest.mark.parametrize("section,field,value", [
    ("target", "relation_oid", "124"), ("column", "not_null", True), ("interval", "amount", 8),
    ("strategy", "by_range_function_oid", "458"), (None, "time_index_exists", True),
])
def test_every_planned_fact_is_fingerprinted(section: str | None, field: str, value: object) -> None:
    planned = conversion_plan.conversion_plan(state(), "observed_at", WEEK)
    changed = planned.model_dump()
    if section is None:
        changed[field] = value
    else:
        changed[section][field] = value
    with pytest.raises(ActionRefused, match="review it again"):
        ConversionPlan.model_validate(changed).require_unchanged(planned.fingerprint())
