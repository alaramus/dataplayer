"""How a routine is recognised across releases, against the real extension."""

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.api import RoutineShape, extension_routine
from app.adapters.postgres.timescale.interval_plan import SET_INTERVAL
from compatibility.timescale.source import TimescaleSource

ADD_COMPRESSION = RoutineShape("add_compression_policy", "f", "2205 2276 16", 23)

_ARGUMENTS = """
SELECT routine.proargtypes::text AS arguments
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
WHERE namespace.nspname = 'public' AND routine.proname = %s
"""


async def whole_list(source: TimescaleSource, name: str) -> str:
    rows = await source.session().query(_ARGUMENTS, (name,))
    assert len(rows) == 1
    return str(rows[0]["arguments"])


async def test_the_leading_arguments_are_enough_on_every_release(source: TimescaleSource) -> None:
    routine = await extension_routine(source.session(), source.version, ADD_COMPRESSION)
    assert routine.schema_name == "public"
    found = await source.session().query(
        "SELECT proname FROM pg_catalog.pg_proc WHERE oid = %s::pg_catalog.oid", (routine.oid,),
    )
    assert found == [{"proname": "add_compression_policy"}]


async def test_a_whole_argument_list_belongs_to_one_release(source: TimescaleSource) -> None:
    """Why a shape names a prefix: releases add and remove trailing arguments.

    `add_compression_policy` has eight arguments in 2.18 and 2.19 and seven in
    every other release here, so pinning either whole list refuses the other.
    Asking for one argument fewer is what survives the difference.
    """
    session = source.session()
    whole = await whole_list(source, "add_compression_policy")
    assert await extension_routine(session, source.version, RoutineShape(
        "add_compression_policy", "f", whole, 23,
    ))
    assert await extension_routine(session, source.version, RoutineShape(
        "add_compression_policy", "f", " ".join(whole.split()[:-1]), 23,
    ))
    with pytest.raises(ActionRefused, match="add_compression_policy API"):
        await extension_routine(session, source.version, RoutineShape(
            "add_compression_policy", "f", f"{whole} 16", 23,
        ))


async def test_an_argument_without_a_default_must_be_named(source: TimescaleSource) -> None:
    # set_chunk_time_interval requires its second argument, so a shape naming
    # only the relation would leave the call short and is refused.
    assert await extension_routine(source.session(), source.version, SET_INTERVAL)
    short = RoutineShape("set_chunk_time_interval", "f", "2205", 2278)
    with pytest.raises(ActionRefused, match="set_chunk_time_interval API"):
        await extension_routine(source.session(), source.version, short)


@pytest.mark.parametrize("arguments", [
    pytest.param("2205 25 16", id="a wrong argument type"),
    pytest.param("16 2276 16", id="a wrong leading type"),
    pytest.param("2205 2276 16 16 16 16 16 16 16 16 16 16", id="more arguments than it has"),
])
async def test_a_shape_the_routine_does_not_have_refuses(
    source: TimescaleSource, arguments: str,
) -> None:
    shape = RoutineShape("add_compression_policy", "f", arguments, 23)
    with pytest.raises(ActionRefused, match="add_compression_policy API"):
        await extension_routine(source.session(), source.version, shape)


async def test_a_routine_of_another_version_is_not_accepted(source: TimescaleSource) -> None:
    # The version is part of the lookup, so an extension upgraded between review
    # and execution finds nothing rather than a routine of the wrong release.
    with pytest.raises(ActionRefused, match="add_compression_policy API"):
        await extension_routine(source.session(), "2.0.0", ADD_COMPRESSION)


async def test_a_routine_outside_the_extension_is_not_found(source: TimescaleSource) -> None:
    # Beside the extension, in its own schema, with the shape a caller asks for.
    session = source.session()
    await session.schema_change(
        "CREATE FUNCTION public.add_policy_probe(regclass, interval, boolean) "
        "RETURNS integer LANGUAGE sql AS 'SELECT 1'",
    )
    try:
        shape = RoutineShape("add_policy_probe", "f", "2205 1186 16", 23)
        with pytest.raises(ActionRefused, match="add_policy_probe API"):
            await extension_routine(session, source.version, shape)
    finally:
        await session.schema_change(
            "DROP FUNCTION public.add_policy_probe(regclass, interval, boolean)",
        )
