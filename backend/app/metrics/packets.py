"""What an agent packet says, as samples and process snapshots (D130).

`sys_monitor_agent` shells out to `df`, `ss` and `ps` and forwards what they
printed. Every habit of that output is absorbed here and nowhere else: numbers
sent as text, the command's header echoed as the first row, labels under
whatever name the command gave the column, positional arrays.

Pure: no database, no socket. The collector hands in bytes and gets values.
"""

import json
import math
from dataclasses import dataclass

from app.metrics.units import unit_for

METRIC_PREFIX = "monitor-"
# A UDP datagram cannot carry more.
MAX_PACKET_BYTES = 65507
# Part of a series identity and of every legend.
MAX_LABEL_LENGTH = 64
MAX_NAME_LENGTH = 128
# At or above this a timestamp is in milliseconds.
_MS_EPOCH_THRESHOLD = 100_000_000_000

PROCESS_METRIC = "ps"
# `ps` is a table with a home of its own. `python` is `ps | grep python`, which
# matches itself and the agent's own command line, so its honest count on a
# host without python is a constant zero.
_NOT_SERIES = frozenset({PROCESS_METRIC, "python"})

# Checked in order for the label of a row. Lower case: the capitalisation
# follows whichever command printed the row.
_LABEL_FIELDS: tuple[str, ...] = (
    "name",
    "mounted",
    "mounted_on",
    "mountpoint",
    "mount",
    "filesystem",
    "device",
    "interface",
    "id",
    "path",
)
_LABEL_FIELD_SET = frozenset(_LABEL_FIELDS)

TCP_METRIC = "tcp"
TCP_COUNT_FIELD = "count"
TCP_TOTAL_LABEL = "total"
TCP_UNKNOWN_STATE = "unknown"

IFTOP_METRIC = "iftop"
IFTOP_PEERS_FIELD = "peers"
# The agent labels these lines' columns after time windows while each holds
# sent, received and total; which number is which cannot be known, so they
# are dropped rather than charted under a wrong label.
_IFTOP_MISLABELLED = frozenset(
    {"Peak rate (sent/received/total)", "Cumulative (sent/received/total)"}
)
# iftop scales by 1024 and tells bits ("Kb") from bytes ("KB") by case.
_RATE_MULTIPLIERS: dict[str, int] = {
    "": 1,
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3,
    "t": 1024**4,
}

MAX_PROCESS_ROWS = 500
MAX_COMMAND_LENGTH = 500
MAX_USER_LENGTH = 64
MAX_ELAPSED_LENGTH = 32


@dataclass(frozen=True, slots=True)
class Envelope:
    """Who sent a packet, about what, when, and the payload as decoded JSON."""

    key: str
    host: str
    metric: str
    ts: int
    data: object


@dataclass(frozen=True, slots=True)
class Sample:
    metric: str
    field: str
    label: str
    unit: str
    ts: int
    value: float


@dataclass(frozen=True, slots=True)
class ProcessRow:
    pid: int
    ppid: int
    user: str
    command: str
    pcpu: float
    pmem: float
    elapsed: str


@dataclass(frozen=True, slots=True)
class ProcessSnapshot:
    host: str
    ts: int
    rows: list[ProcessRow]
    # Carried out rather than logged here: the caller knows which agent sent it.
    skipped: int
    truncated: int


def read_envelope(raw: bytes) -> Envelope | None:
    """The addressed parts of a packet, or None when it cannot be addressed."""
    if len(raw) > MAX_PACKET_BYTES:
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    key = _name(decoded.get("appkey"))
    host = _name(decoded.get("host"))
    action = _name(decoded.get("action"))
    ts = _timestamp(decoded.get("time"))
    if key is None or host is None or action is None or ts is None:
        return None
    metric = action.removeprefix(METRIC_PREFIX)
    if not metric:
        return None
    return Envelope(key=key, host=host, metric=metric, ts=ts, data=decoded.get("data"))


def samples_of(envelope: Envelope) -> list[Sample]:
    """The measurements a packet carries. Empty for a table that is not one."""
    if envelope.metric in _NOT_SERIES:
        return []
    collected = _Samples(envelope.metric, envelope.ts)
    if envelope.metric == TCP_METRIC:
        _connection_counts(collected, envelope.data)
    elif envelope.metric == IFTOP_METRIC:
        _iftop(collected, envelope.data)
    elif isinstance(envelope.data, dict):
        _mapping(collected, envelope.data)
    elif isinstance(envelope.data, list):
        _rows(collected, envelope.data)
    return collected.samples


def process_snapshot_of(envelope: Envelope) -> ProcessSnapshot | None:
    """The process table a `ps` packet carries, or None for any other packet."""
    if envelope.metric != PROCESS_METRIC:
        return None
    raw_rows = _process_rows(envelope.data)
    rows: list[ProcessRow] = []
    skipped = 0
    for item in raw_rows[:MAX_PROCESS_ROWS]:
        if isinstance(item, dict) and is_header_row(item):
            continue
        row = _process_row(item)
        if row is None:
            skipped += 1
            continue
        rows.append(row)
    return ProcessSnapshot(
        host=envelope.host,
        ts=envelope.ts,
        rows=rows,
        skipped=skipped,
        truncated=max(0, len(raw_rows) - MAX_PROCESS_ROWS),
    )


def is_header_row(item: dict[object, object]) -> bool:
    """Whether a row is the command's header line, echoed as values.

    Recognised rather than skipped by position, because not every metric sends
    one. Two echoes, not all: the agent glues a word onto the last `ss` header
    ("Peer:Address:PortProcess").
    """
    echoes = 0
    for key, value in item.items():
        if not isinstance(value, str):
            return False
        if value.strip() == str(key).strip():
            echoes += 1
    return echoes >= 2


class _Samples:
    def __init__(self, metric: str, ts: int) -> None:
        self.metric = metric
        self.ts = ts
        self.samples: list[Sample] = []

    def emit(self, field: str, label: str, raw: object, unit: str | None = None) -> None:
        value = numeric(raw)
        if value is None:
            return
        field = field[:MAX_NAME_LENGTH]
        self.samples.append(
            Sample(
                metric=self.metric,
                field=field,
                label=label[:MAX_LABEL_LENGTH],
                unit=unit_for(self.metric, field) if unit is None else unit,
                ts=self.ts,
                value=value,
            )
        )


def numeric(value: object) -> float | None:
    """A measurement, including one that travelled as text ("2%").

    Non-finite results are refused: Python's JSON parser accepts NaN, and one
    poisons every average built over it.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > MAX_NAME_LENGTH:
        return None
    return text


def _timestamp(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        ts = int(value) if isinstance(value, int | str) else None
    except ValueError:
        return None
    if ts is None or ts <= 0:
        return None
    return ts // 1000 if ts >= _MS_EPOCH_THRESHOLD else ts


def _clean_label(value: str) -> str:
    # "eth0:" is how /proc/net/dev prints a name, not part of it.
    return value.strip().rstrip(":").strip()[:MAX_LABEL_LENGTH]


def _label_of(item: dict[object, object], position: int) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for key in _LABEL_FIELDS:
        value = lowered.get(key)
        if isinstance(value, str):
            cleaned = _clean_label(value)
            if cleaned:
                return cleaned
    # /proc/meminfo sends one single-key object per line. A positional label
    # would tie every identity to the order of that file.
    if len(item) == 1:
        return ""
    return str(position)


def _array_labels(metric: str, field: str, size: int) -> list[str]:
    if field == "loadavg" and size == 3:
        return ["1m", "5m", "15m"]
    if metric == "cpu" and field == "cpu" and size > 1:
        # The machine total first, then one entry per core.
        return ["total"] + [f"cpu{index}" for index in range(size - 1)]
    return [str(index) for index in range(size)]


def _mapping(collected: _Samples, payload: dict[object, object]) -> None:
    for field, raw in payload.items():
        if isinstance(raw, list):
            labels = _array_labels(collected.metric, str(field), len(raw))
            for label, element in zip(labels, raw, strict=True):
                collected.emit(str(field), label, element)
            continue
        collected.emit(str(field), "", raw)


def _rows(collected: _Samples, payload: list[object]) -> None:
    for position, item in enumerate(payload):
        if not isinstance(item, dict) or is_header_row(item):
            continue
        label = _label_of(item, position)
        for field, raw in item.items():
            if str(field).lower() in _LABEL_FIELD_SET:
                continue
            collected.emit(str(field), label, raw)


def _connection_counts(collected: _Samples, payload: object) -> None:
    """A socket table as a count per state, plus the total.

    A row is a socket whose position changes every packet; a series per row
    would mint an identity per socket the host ever opens.
    """
    if not isinstance(payload, list):
        return
    counts: dict[str, int] = {}
    total = 0
    for item in payload:
        if not isinstance(item, dict) or is_header_row(item):
            continue
        lowered = {str(key).lower(): value for key, value in item.items()}
        raw_state = lowered.get("state")
        state = _clean_label(raw_state) if isinstance(raw_state, str) else ""
        state = state or TCP_UNKNOWN_STATE
        counts[state] = counts.get(state, 0) + 1
        total += 1
    for state, count in counts.items():
        collected.emit(TCP_COUNT_FIELD, state, count)
    # Written for an empty table too: a gap reads as "the agent stopped".
    collected.emit(TCP_COUNT_FIELD, TCP_TOTAL_LABEL, total)


def _iftop(collected: _Samples, payload: object) -> None:
    """The summary lines of an iftop report as series, and its flows counted.

    A flow is addressed by an ephemeral port, so it is only counted.
    """
    if not isinstance(payload, list):
        return
    flows = 0
    for element in payload:
        if isinstance(element, list):
            # Two rows per peer, one per direction.
            if _flow_direction(element) == "TX":
                flows += 1
            continue
        if not isinstance(element, dict):
            continue
        for name, columns in element.items():
            if not isinstance(columns, list) or name in _IFTOP_MISLABELLED:
                continue
            for column in columns:
                if not isinstance(column, dict):
                    continue
                for label, raw in column.items():
                    value, unit = _rate(raw)
                    if value is not None:
                        collected.emit(str(name), str(label), value, unit)
    collected.emit(IFTOP_PEERS_FIELD, "", flows)


def _flow_direction(row: list[object]) -> str:
    for column in row:
        if not isinstance(column, dict):
            continue
        for key, value in column.items():
            if str(key).lower() == "txrx" and isinstance(value, str):
                return value.strip()
    return ""


def _rate(raw: object) -> tuple[float | None, str]:
    if not isinstance(raw, str):
        return numeric(raw), ""
    text = raw.strip()
    suffix = ""
    while text and text[-1].isalpha():
        suffix = text[-1] + suffix
        text = text[:-1]
    number = numeric(text)
    if number is None or not suffix:
        return number, ""
    scale = _RATE_MULTIPLIERS.get(suffix[:-1].lower())
    if scale is None:
        return None, ""
    return number * scale, ("b/s" if suffix[-1] == "b" else "B")


def _process_rows(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, list):
            return inner
    return []


def _process_row(item: object) -> ProcessRow | None:
    if not isinstance(item, dict):
        return None
    lowered = {str(key).lower(): value for key, value in item.items()}
    pid = _integer(lowered.get("pid"))
    pcpu = numeric(lowered.get("pcpu"))
    pmem = numeric(lowered.get("pmem"))
    if pid is None or pcpu is None or pmem is None:
        return None
    ppid = _integer(lowered.get("ppid"))
    return ProcessRow(
        pid=pid,
        # A kernel thread without a parent is still a process.
        ppid=ppid if ppid is not None else 0,
        user=_text(lowered.get("user"), MAX_USER_LENGTH),
        command=_text(lowered.get("command"), MAX_COMMAND_LENGTH),
        pcpu=pcpu,
        pmem=pmem,
        elapsed=_text(lowered.get("elapsed"), MAX_ELAPSED_LENGTH),
    )


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _text(value: object, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]
