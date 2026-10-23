"""What a MySQL server reports about itself, for dashboards (D128, D241)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.metrics import SupportsMetrics
from app.adapters.mysql.adapter import MysqlAdapter
from tests.adapters.mysql_fixture import DATABASE, TARGETS, Target, build, tear_down


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def test_every_series_a_preset_draws_is_reported(target: Target) -> None:
    source = target.adapter(database=DATABASE)
    assert isinstance(source, SupportsMetrics)

    samples = await source.metric_samples()

    reported = {(sample.metric, sample.field) for sample in samples}
    for preset in MysqlAdapter.metric_presets():
        for recipe in preset.recipes:
            fields = recipe.fields or tuple(field for metric, field in reported if metric == recipe.metric)
            assert fields, recipe.title
            for field in fields:
                assert (recipe.metric, field) in reported, (recipe.metric, field)


async def test_counters_are_counters_and_connections_are_not(target: Target) -> None:
    samples = await target.adapter(database=DATABASE).metric_samples()

    by_key = {(sample.metric, sample.field, sample.label): sample for sample in samples}
    connected = by_key[("sessions", "count", "connected")]
    assert connected.value >= 1 and not connected.counter
    assert by_key[("statements", "select", "")].counter
    assert by_key[("traffic", "sent", "")].unit == "B"


async def test_the_size_is_of_the_connection_s_database(target: Target) -> None:
    named = await target.adapter(database=DATABASE).metric_samples()
    everything = await target.adapter(database="").metric_samples()

    size = next(sample.value for sample in named if sample.metric == "database")
    total = next(sample.value for sample in everything if sample.metric == "database")
    assert 0 < size <= total
