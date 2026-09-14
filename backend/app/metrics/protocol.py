"""DPMA/1, what `dataplayer-monitor-agent` sends, checked before it is read (D130).

The agent's `PROTOCOL.md` is the contract; this module is its receiving half.
A datagram is `DPMA/1 <kid> <signature>\\n<body>`: the key id names the key
without revealing it, the signature is HMAC-SHA256 of the body's bytes under
that key, and the body is JSON whose every value is what it says.

Pure: no database, no socket, no clock of its own.
"""

import base64
import binascii
import hashlib
import hmac
import re
from collections.abc import Hashable
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from app.metrics.keys import KEY_ID_LENGTH

MAGIC = b"DPMA/1"
MAX_DATAGRAM_BYTES = 65507
MAX_FIRST_LINE_BYTES = 128
SIGNATURE_BYTES = 32

# A body measured longer ago than this, or further ahead, is refused.
PAST_SECONDS = 10 * 60
FUTURE_SECONDS = 2 * 60
# Sequence numbers accepted below the highest one of an instance that are
# still remembered. Datagrams are reordered by a few at most; one further back
# than this is refused as if it had been seen.
SEQ_WINDOW = 1024
# An instance not heard from for this long is forgotten. A replay of anything
# it sent is older than PAST_SECONDS by then, and refused by its time.
FORGET_SECONDS = 15 * 60

_KEY_ID = re.compile(rb"^[0-9a-f]{%d}$" % KEY_ID_LENGTH)

Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
Label = Annotated[str, StringConstraints(max_length=128)]
Unit = Literal["%", "B", "B/s", "/s", "s", ""]
Count = Annotated[int, Field(ge=0)]
Share = Annotated[FiniteFloat, Field(ge=0)]


@dataclass(frozen=True, slots=True)
class Frame:
    key_id: str
    signature: bytes
    body: bytes


def frame_of(raw: bytes) -> Frame | None:
    """The parts of a datagram, or None when it is not a DPMA/1 datagram."""
    if len(raw) > MAX_DATAGRAM_BYTES:
        return None
    newline = raw.find(b"\n", 0, MAX_FIRST_LINE_BYTES + 1)
    if newline < 0:
        return None
    parts = raw[:newline].split(b" ")
    if len(parts) != 3 or parts[0] != MAGIC or not _KEY_ID.match(parts[1]):
        return None
    signature = parts[2]
    # base64url without padding: 43 characters for 32 bytes.
    try:
        decoded = base64.urlsafe_b64decode(signature + b"=" * (-len(signature) % 4))
    except (binascii.Error, ValueError):
        return None
    if len(decoded) != SIGNATURE_BYTES:
        return None
    return Frame(key_id=parts[1].decode("ascii"), signature=decoded, body=raw[newline + 1 :])


def signed_with(frame: Frame, key: str) -> bool:
    """Whether the body's bytes, as received, were signed with this key."""
    expected = hmac.new(key.encode("utf-8"), frame.body, hashlib.sha256).digest()
    return hmac.compare_digest(expected, frame.signature)


class _Part(BaseModel):
    # Fields added to version 1 later are ignored; a change that breaks
    # reading it is version 2.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)


class AgentRun(_Part):
    version: Annotated[str, StringConstraints(max_length=64)]
    instance: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    started: Count


class HostName(_Part):
    name: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    boot: Annotated[str, StringConstraints(max_length=64)]


class _Header(_Part):
    v: Literal[1]
    agent: AgentRun
    host: HostName
    seq: Annotated[int, Field(ge=1)]
    time: Count


# [metric, field, label, unit, value]
SampleItem = tuple[Name, Name, Label, Unit, FiniteFloat]

# [pid, ppid, user, state, cpu, memory, rss, started, name, command]
ProcessItem = tuple[
    Count,
    Count,
    Annotated[str, StringConstraints(max_length=256)],
    Annotated[str, StringConstraints(max_length=16)],
    Share,
    Share,
    Count,
    Count,
    Annotated[str, StringConstraints(max_length=256)],
    Annotated[str, StringConstraints(max_length=256)],
]


class MetricsReport(_Header):
    kind: Literal["metrics"]
    samples: list[SampleItem]


class ProcessesReport(_Header):
    kind: Literal["processes"]
    total: Count
    part: tuple[Annotated[int, Field(ge=1)], Annotated[int, Field(ge=1)]]
    rows: list[ProcessItem]

    @model_validator(mode="after")
    def _part_within_count(self) -> ProcessesReport:
        if self.part[0] > self.part[1]:
            raise ValueError("part index past its count")
        return self


class HostDescription(_Part):
    os: Annotated[str, StringConstraints(max_length=256)]
    kernel: Annotated[str, StringConstraints(max_length=256)]
    arch: Annotated[str, StringConstraints(max_length=32)]
    cpus: Count
    cpu_model: Annotated[str, StringConstraints(max_length=256)]
    memory: Count
    boot_time: Count
    collectors: Annotated[dict[Name, Count], Field(max_length=64)]


class HostReport(_Header):
    kind: Literal["host"]
    info: HostDescription


Report = MetricsReport | ProcessesReport | HostReport

_REPORT: TypeAdapter[Report] = TypeAdapter(Annotated[Report, Field(discriminator="kind")])


def report_of(body: bytes) -> Report | None:
    """The body as the protocol reads it, or None when any of it breaks the
    protocol: one bad sample refuses the datagram, it is not salvaged."""
    try:
        return _REPORT.validate_json(body)
    except ValidationError:
        return None


Refusal = Literal["stale", "future", "replayed"]


@dataclass(slots=True)
class _Seen:
    highest: int
    accepted: set[int]
    heard: int


class Freshness:
    """Which bodies are fresh enough to write, by their time and their sequence
    number per agent instance.

    In memory: the metrics process starting again forgets what it accepted, so
    a datagram replayed within ten minutes of being sent before that is taken.
    """

    def __init__(self) -> None:
        self._seen: dict[Hashable, _Seen] = {}

    def check(self, instance: Hashable, seq: int, sent: int, now: int) -> Refusal | None:
        """Refuse, or accept and remember."""
        if sent < now - PAST_SECONDS:
            return "stale"
        if sent > now + FUTURE_SECONDS:
            return "future"
        seen = self._seen.get(instance)
        if seen is None:
            self._seen[instance] = _Seen(highest=seq, accepted={seq}, heard=now)
            return None
        if seq <= seen.highest - SEQ_WINDOW or seq in seen.accepted:
            return "replayed"
        seen.accepted.add(seq)
        seen.heard = now
        seen.highest = max(seen.highest, seq)
        # Pruned now and then rather than on every datagram: below the window
        # a number is refused whether it is remembered or not.
        if len(seen.accepted) > 2 * SEQ_WINDOW:
            floor = seen.highest - SEQ_WINDOW
            seen.accepted = {one for one in seen.accepted if one > floor}
        return None

    def forget_quiet(self, now: int) -> None:
        for instance in [key for key, seen in self._seen.items() if seen.heard < now - FORGET_SECONDS]:
            del self._seen[instance]
