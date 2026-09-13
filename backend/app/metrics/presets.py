"""Ready-made dashboards a kind of source declares (DB3).

A preset is a layout with recipes, not series ids: ids are minted the first
time a host reports and differ on every install, so a recipe names a metric
and fields and is resolved against what one host actually reported. A recipe
that matches nothing is left out; the gap it leaves is closed when the layout is
placed on a dashboard, by the same grid arithmetic every other move uses.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.metrics.dashboards import (
    AnyWidget,
    ProcessesWidget,
    StatWidget,
    TimeseriesWidget,
    WidgetLayout,
)
from app.metrics.store import StoredSeries


@dataclass(frozen=True)
class Recipe:
    type: Literal["timeseries", "stat", "processes"]
    title: str
    layout: tuple[int, int, int, int]
    metric: str = ""
    # None: every field of the metric.
    fields: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    description: str
    recipes: tuple[Recipe, ...]


# A host `sys_monitor_agent` reports. No recipe spans units, so `cpu` is three
# widgets; `/proc/meminfo` sends twenty lines and five of them answer whether a
# box is short of memory; `iftop` is absent because the agent crashes on it
# (D130).
LINUX_HOST = Preset(
    key="linux-host",
    name="Linux host",
    description="CPU, memory, disk, network and the process table of one machine.",
    recipes=(
        Recipe("timeseries", "CPU per core", (0, 0, 8, 5), "cpu", ("cpu",)),
        Recipe("stat", "Uptime", (8, 0, 4, 5), "cpu", ("uptime",)),
        Recipe(
            "timeseries",
            "Memory",
            (0, 5, 8, 5),
            "memory",
            ("MemTotal", "MemAvailable", "MemFree", "Cached", "Buffers"),
        ),
        Recipe("timeseries", "Load average", (8, 5, 4, 5), "cpu", ("loadavg",)),
        Recipe("timeseries", "Network", (0, 10, 6, 5), "net", ("read_delta", "transfer_delta")),
        Recipe("timeseries", "TCP sockets by state", (6, 10, 6, 5), "tcp", ("count",)),
        Recipe("timeseries", "Disk space", (0, 15, 6, 5), "disk", ("total", "free")),
        Recipe("timeseries", "Filesystems", (6, 15, 6, 5), "df", ("1K-blocks", "Used", "Available")),
        Recipe("processes", "Top processes", (0, 20, 12, 8)),
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
    agent_id: uuid.UUID,
    host: str,
    series: Sequence[StoredSeries],
    reports_processes: bool,
) -> ResolvedPreset:
    """The preset as this host can fill it."""
    mine = [one for one in series if one.source.id == agent_id and one.host == host]
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
                        agent_id=agent_id,
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
