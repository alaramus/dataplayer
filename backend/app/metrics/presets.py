"""Ready-made dashboards a kind of source declares (DB3).

A preset is a layout with recipes, not series ids: ids are minted the first
time a host reports and differ on every install, so a recipe names a metric
and fields and is resolved against what one host actually reported. A recipe
that matches nothing is left out; the gap it leaves is closed when the layout is
placed on a dashboard, by the same grid arithmetic every other move uses.
"""

import uuid
from collections.abc import Sequence

from pydantic import BaseModel

from app.adapters.metrics import MetricPreset, MetricRecipe
from app.metrics.dashboards import (
    AnyWidget,
    ProcessesWidget,
    StatWidget,
    TimeseriesWidget,
    WidgetLayout,
)
from app.metrics.store import StoredSeries

Recipe = MetricRecipe
Preset = MetricPreset


# A host `dataplayer-monitor-agent` reports, in the names of its PROTOCOL.md
# (D130). No recipe spans units: an axis has one scale.
LINUX_HOST = Preset(
    key="linux-host",
    name="Linux host",
    description="CPU, memory, network, disks, file systems, connections, containers and the busiest processes of one machine.",
    recipes=(
        Recipe("timeseries", "CPU by mode", (0, 0, 5, 5), "cpu", ("user", "system", "iowait", "steal")),
        Recipe("timeseries", "CPU per core", (5, 0, 5, 5), "cpu", ("utilization",)),
        Recipe("stat", "Uptime", (10, 0, 2, 5), "host", ("uptime",)),
        Recipe("timeseries", "Memory", (0, 5, 5, 5), "memory", ("used", "available", "cached", "buffers")),
        Recipe("timeseries", "Load average", (5, 5, 5, 5), "cpu", ("load1", "load5", "load15")),
        Recipe("stat", "Memory in use", (10, 5, 2, 5), "memory", ("utilization",)),
        Recipe("timeseries", "Network", (0, 10, 6, 5), "net", ("receive", "transmit")),
        Recipe("timeseries", "Disk I/O", (6, 10, 6, 5), "disk", ("read", "write")),
        Recipe("timeseries", "File systems in use", (0, 15, 6, 5), "fs", ("utilization",)),
        Recipe("timeseries", "TCP connections by state", (6, 15, 6, 5), "tcp", ("connections",)),
        Recipe("timeseries", "Containers: CPU", (0, 20, 6, 5), "container", ("cpu",)),
        Recipe("timeseries", "Containers: memory", (6, 20, 6, 5), "container", ("memory",)),
        Recipe("processes", "Top processes", (0, 25, 12, 8)),
    ),
)

AGENT_PRESETS: tuple[Preset, ...] = (LINUX_HOST,)


class ResolvedPreset(BaseModel):
    key: str
    name: str
    description: str
    # How many recipes the preset has, beside how many this host matched.
    total: int
    # Placeholder ids; a dashboard gives each widget its own when it is added.
    widgets: list[AnyWidget]


def resolve(
    preset: Preset,
    *,
    source_id: uuid.UUID,
    host: str,
    series: Sequence[StoredSeries],
    reports_processes: bool,
) -> ResolvedPreset:
    """The preset as one host of an agent, or one connection, can fill it.

    A connection's series carry an empty host; a process table is only ever an
    agent's.
    """
    mine = [one for one in series if one.source.id == source_id and one.host == host]
    widgets: list[AnyWidget] = []
    for recipe in preset.recipes:
        x, y, w, h = recipe.layout
        layout = WidgetLayout(x=x, y=y, w=w, h=h)
        if recipe.type == "processes":
            if reports_processes:
                widgets.append(
                    ProcessesWidget(
                        type="processes",
                        id=uuid.uuid4(),
                        title=recipe.title,
                        layout=layout,
                        agent_id=source_id,
                        host=host,
                    )
                )
            continue
        matched = [
            one
            for one in mine
            if one.metric == recipe.metric
            and (recipe.fields is None or one.field in recipe.fields)
        ]
        if not matched:
            continue
        if recipe.type == "stat":
            widgets.append(
                StatWidget(type="stat", id=uuid.uuid4(), title=recipe.title, layout=layout, series_id=matched[0].id)
            )
            continue
        widgets.append(
            TimeseriesWidget(
                type="timeseries",
                id=uuid.uuid4(),
                title=recipe.title,
                layout=layout,
                series_ids=[one.id for one in matched][:50],
            )
        )
    return ResolvedPreset(
        key=preset.key,
        name=preset.name,
        description=preset.description,
        total=len(preset.recipes),
        widgets=widgets,
    )
