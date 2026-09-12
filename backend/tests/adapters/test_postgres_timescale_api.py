from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import api
from app.adapters.postgres.timescale.api import RoutineShape

SHAPE = RoutineShape("add_retention_policy", "f", "2205 2276 16", 23)


async def test_routine_shape_is_bound_rather_than_formatted() -> None:
    reader = AsyncMock()
    reader.query.return_value = [{"oid": "456", "schema_name": "public"}]
    routine = await api.extension_routine(reader, "2.18.0", SHAPE)
    assert (routine.oid, routine.schema_name) == ("456", "public")
    statement, params = reader.query.await_args.args
    assert params == ("2.18.0", "add_retention_policy", "f", False, "23", 3, 2, [2205, 2276, 16], 3, True)
    assert "add_retention_policy" not in statement
    assert reader.query.await_args.kwargs == {"inspection": True}


async def test_set_returning_routine_among_overloads_is_asked_for_explicitly() -> None:
    reader = AsyncMock()
    reader.query.return_value = [{"oid": "789", "schema_name": "public"}]
    shape = RoutineShape("create_hypertable", "f", "2205 99999 16 16 16", 2249, returns_set=True, exclusive=False)
    await api.extension_routine(reader, "2.17.2", shape)
    params = reader.query.await_args.args[1]
    assert (params[3], params[4], params[9]) == (True, "2249", False)
    assert params[5:9] == (5, 4, [2205, 99999, 16, 16, 16], 5)


@pytest.mark.parametrize("rows", [[], [{"oid": "456", "schema_name": "public"}] * 2])
async def test_missing_or_ambiguous_routine_refuses(rows: list[dict[str, object]]) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match="add_retention_policy API"):
        await api.extension_routine(reader, "2.18.0", SHAPE)


async def test_malformed_routine_identity_is_not_accepted() -> None:
    reader = AsyncMock()
    reader.query.return_value = [{"oid": "0x1c8", "schema_name": "public"}]
    with pytest.raises(ValueError):
        await api.extension_routine(reader, "2.18.0", SHAPE)


def test_routine_statement_checks_ownership_schema_overloads_and_privileges() -> None:
    for required in (
        "deptype = 'e'", "extension.extnamespace", "overload.proname = routine.proname",
        "has_function_privilege", "has_schema_privilege", "routine.proretset = %s",
        # Arguments the caller does not pass must be optional, and none may be variadic.
        "routine.pronargs - routine.pronargdefaults <= %s", "routine.provariadic = 0",
    ):
        assert required in api._ROUTINE


async def test_extension_type_is_owned_and_usable() -> None:
    reader = AsyncMock()
    reader.query.return_value = [{"oid": "99999"}]
    assert await api.extension_type(reader, "2.18.0", "_timescaledb_internal", "dimension_info") == "99999"
    assert reader.query.await_args.args[1] == ("2.18.0", "_timescaledb_internal", "dimension_info")
    assert "deptype = 'e'" in api._TYPE and "has_type_privilege" in api._TYPE
    reader.query.return_value = []
    with pytest.raises(ActionRefused, match="dimension_info type"):
        await api.extension_type(reader, "2.18.0", "_timescaledb_internal", "dimension_info")


@pytest.mark.parametrize("rows", [[], [{"oid": "789"}] * 2])
async def test_view_without_lock_permission_refuses(rows: list[dict[str, object]]) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match="may not lock"):
        await api.lockable_view(reader, "2.18.0", "jobs")


async def test_lockable_view_is_owned_public_metadata() -> None:
    reader = AsyncMock()
    reader.query.return_value = [{"oid": "789"}]
    assert await api.lockable_view(reader, "2.17.2", "jobs") == "789"
    assert reader.query.await_args.args[1] == ("2.17.2", "jobs")
    assert "timescaledb_information" in api._LOCKABLE_VIEW
    assert "UPDATE,DELETE,TRUNCATE" in api._LOCKABLE_VIEW
