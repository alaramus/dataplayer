"""Ready-made dashboards resolved against what one host reported."""

import uuid
from datetime import UTC, datetime

from app.metrics.dashboards import ProcessesWidget, StatWidget, TimeseriesWidget
from app.metrics.presets import LINUX_HOST, resolve
from app.metrics.store import Source, StoredSeries

AGENT = uuid.uuid4()
SEEN = datetime(2026, 9, 14, tzinfo=UTC)

# The unit of every field the agent sends, from its PROTOCOL.md.
PROTOCOL_UNITS: dict[str, dict[str, str]] = {
    "cpu": {
        "utilization": "%", "user": "%", "system": "%", "iowait": "%", "steal": "%",
        "load1": "", "load5": "", "load15": "", "count": "",
    },
    "host": {"uptime": "s", "processes": "", "running": "", "blocked": ""},
    "memory": {
        "total": "B", "available": "B", "used": "B", "free": "B", "cached": "B", "buffers": "B",
        "swap_total": "B", "swap_used": "B", "utilization": "%", "swap_utilization": "%",
    },
    "fs": {"total": "B", "used": "B", "available": "B", "utilization": "%", "inodes_utilization": "%"},
    "disk": {"read": "B/s", "write": "B/s", "read_ops": "/s", "write_ops": "/s", "utilization": "%"},
    "net": {
        "receive": "B/s", "transmit": "B/s", "receive_packets": "/s", "transmit_packets": "/s",
        "errors": "/s", "drops": "/s",
    },
    "tcp": {"connections": ""},
    "container": {"cpu": "%", "memory": "B", "memory_limit": "B", "receive": "B/s", "transmit": "B/s", "running": ""},
}


def _series(series_id: int, metric: str, field: str, label: str = "", host: str = "web-01", agent: uuid.UUID = AGENT) -> StoredSeries:
    return StoredSeries(
        id=series_id,
        source=Source("agent", agent),
        host=host,
        metric=metric,
        field=field,
        label=label,
        unit=PROTOCOL_UNITS[metric][field],
        first_seen=SEEN,
        last_seen=SEEN,
    )


def test_a_host_that_reports_everything_fills_every_recipe() -> None:
    series = [
        _series(index, metric, field, label)
        for index, (metric, field, label) in enumerate(
            [
                (metric, field, label)
                for metric, fields in PROTOCOL_UNITS.items()
                for field in fields
                for label in (("total", "cpu0") if metric == "cpu" and field == "utilization" else ("",))
            ],
            start=1,
        )
    ]

    preset = resolve(LINUX_HOST, source_id=AGENT, host="web-01", series=series, reports_processes=True)

    assert preset.total == len(preset.widgets) == len(LINUX_HOST.recipes)
    by_title = {widget.title: widget for widget in preset.widgets}
    by_name = {(s.metric, s.field, s.label): s.id for s in series}
    cpu = by_title["CPU per core"]
    assert isinstance(cpu, TimeseriesWidget)
    assert cpu.series_ids == [by_name[("cpu", "utilization", "total")], by_name[("cpu", "utilization", "cpu0")]]
    uptime = by_title["Uptime"]
    assert isinstance(uptime, StatWidget) and uptime.series_id == by_name[("host", "uptime", "")]
    network = by_title["Network"]
    assert isinstance(network, TimeseriesWidget)
    assert network.series_ids == [by_name[("net", "receive", "")], by_name[("net", "transmit", "")]]
    table = by_title["Top processes"]
    assert isinstance(table, ProcessesWidget) and table.host == "web-01"


def test_a_recipe_that_matches_nothing_is_left_out() -> None:
    series = [_series(1, "host", "uptime"), _series(2, "cpu", "utilization", "total", host="db-01")]

    preset = resolve(LINUX_HOST, source_id=AGENT, host="web-01", series=series, reports_processes=False)

    assert [widget.title for widget in preset.widgets] == ["Uptime"]
    assert preset.total == len(LINUX_HOST.recipes)


def test_another_agent_s_series_of_the_same_host_name_are_not_taken() -> None:
    series = [_series(1, "host", "uptime", agent=uuid.uuid4())]

    preset = resolve(LINUX_HOST, source_id=AGENT, host="web-01", series=series, reports_processes=False)

    assert preset.widgets == []


def test_every_recipe_names_fields_the_agent_sends_and_no_recipe_spans_units() -> None:
    for recipe in LINUX_HOST.recipes:
        if recipe.type == "processes":
            continue
        assert recipe.fields is not None, recipe.title
        assert set(recipe.fields) <= set(PROTOCOL_UNITS[recipe.metric]), recipe.title
        assert len({PROTOCOL_UNITS[recipe.metric][field] for field in recipe.fields}) == 1, recipe.title


def test_the_layout_fits_the_grid_without_overlapping() -> None:
    taken: set[tuple[int, int]] = set()
    for recipe in LINUX_HOST.recipes:
        x, y, w, h = recipe.layout
        assert 0 <= x and x + w <= 12, recipe.title
        cells = {(column, row) for column in range(x, x + w) for row in range(y, y + h)}
        assert not cells & taken, recipe.title
        taken |= cells
