"""The display unit of a field an agent sends.

Values are stored as reported; the unit travels with the series so a screen can
scale them. What `sys_monitor_agent` sends per (metric, field) comes first, the
field-name suffix convention second.
"""

_UNIT_BY_METRIC: dict[str, str] = {
    # /proc/meminfo reports kilobytes on every line.
    "memory": "kB",
}

_UNIT_BY_METRIC_FIELD: dict[tuple[str, str], str] = {
    ("cpu", "cpu"): "%",
    ("cpu", "uptime"): "s",
    ("disk", "total"): "B",
    ("disk", "free"): "B",
    ("disk", "used"): "B",
    ("disk", "usage"): "%",
    ("df", "1K-blocks"): "kB",
    ("df", "Used"): "kB",
    ("df", "Available"): "kB",
    ("df", "Use%"): "%",
    ("net", "read"): "B",
    ("net", "transfer"): "B",
}

# The first matching suffix wins.
_UNIT_BY_SUFFIX: tuple[tuple[str, str], ...] = (
    ("_percent", "%"),
    ("_bytes", "B"),
    ("_gb", "GB"),
    ("_mb", "MB"),
    ("_sec", "s"),
)


def unit_for(metric: str, field: str) -> str:
    exact = _UNIT_BY_METRIC_FIELD.get((metric, field))
    if exact is not None:
        return exact
    whole = _UNIT_BY_METRIC.get(metric)
    if whole is not None:
        return whole
    lowered = field.lower()
    for suffix, unit in _UNIT_BY_SUFFIX:
        if lowered.endswith(suffix):
            return unit
    return ""
