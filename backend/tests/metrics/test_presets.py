"""Ready-made dashboards resolved against what one host reported."""

import uuid
from datetime import UTC, datetime

from app.metrics.dashboards import ProcessesWidget, StatWidget, TimeseriesWidget
from app.metrics.presets import LINUX_HOST, resolve
from app.metrics.store import Source, StoredSeries
from app.metrics.units import unit_for

AGENT = uuid.uuid4()
SEEN = datetime(2026, 9, 13, tzinfo=UTC)


def _series(series_id: int, metric: str, field: str, label: str = "", host: str = "web-01", agent: uuid.UUID = AGENT) -> StoredSeries:
    return StoredSeries(
        id=series_id,
        source=Source("agent", agent),
        host=host,
        metric=metric,
        field=field,
        label=label,
        unit=unit_for(metric, field),
        first_seen=SEEN,
        last_seen=SEEN,
    )


def test_a_host_that_reports_everything_fills_every_recipe() -> None:
    series = [
        _series(1, "cpu", "cpu", "total"),
        _series(2, "cpu", "cpu", "cpu0"),
        _series(3, "cpu", "uptime"),
        _series(4, "memory", "MemFree"),
        _series(5, "memory", "Dirty"),
        _series(6, "cpu", "loadavg", "1m"),
        _series(7, "net", "read_delta", "eth0"),
        _series(8, "tcp", "count", "total"),
        _series(9, "disk", "free", "/"),
        _series(10, "df", "Used", "/"),
    ]

    preset = resolve(LINUX_HOST, agent_id=AGENT, host="web-01", series=series, reports_processes=True)

    assert preset.total == len(preset.widgets) == 9
    by_title = {widget.title: widget for widget in preset.widgets}
    cpu = by_title["CPU per core"]
    assert isinstance(cpu, TimeseriesWidget) and cpu.series_ids == [1, 2]
    uptime = by_title["Uptime"]
    assert isinstance(uptime, StatWidget) and uptime.series_id == 3
    memory = by_title["Memory"]
    # A dump of twenty lines is narrowed to the ones that answer the question.
    assert isinstance(memory, TimeseriesWidget) and memory.series_ids == [4]
    table = by_title["Top processes"]
    assert isinstance(table, ProcessesWidget) and table.host == "web-01"


def test_a_recipe_that_matches_nothing_is_left_out() -> None:
    series = [_series(1, "cpu", "uptime"), _series(2, "cpu", "cpu", "total", host="db-01")]

    preset = resolve(LINUX_HOST, agent_id=AGENT, host="web-01", series=series, reports_processes=False)

    assert [widget.title for widget in preset.widgets] == ["Uptime"]
    assert preset.total == 9


def test_another_agent_s_series_of_the_same_host_name_are_not_taken() -> None:
    series = [_series(1, "cpu", "uptime", agent=uuid.uuid4())]

    preset = resolve(LINUX_HOST, agent_id=AGENT, host="web-01", series=series, reports_processes=False)

    assert preset.widgets == []


def test_no_recipe_spans_units() -> None:
    fields = {
        "cpu": ["cpu", "uptime", "loadavg"],
        "memory": ["MemTotal", "MemAvailable", "MemFree", "Cached", "Buffers"],
        "net": ["read_delta", "transfer_delta"],
        "tcp": ["count"],
        "disk": ["total", "free"],
        "df": ["1K-blocks", "Used", "Available"],
    }
    for recipe in LINUX_HOST.recipes:
        if recipe.type == "processes":
            continue
        chosen = recipe.fields or tuple(fields[recipe.metric])
        # Increments keep the unit of the counter they replace.
        units = {unit_for(recipe.metric, field.removesuffix("_delta")) for field in chosen}
        assert len(units) == 1, recipe.title
