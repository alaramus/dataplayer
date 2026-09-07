"""Validate a complete verbose custom-archive TOC before restore (D122)."""

import re
from collections.abc import Sequence

from app.adapters.postgres.timescale.names import DEDICATED_SCHEMAS

MAX_INVENTORY_ENTRIES = 10_000
MAX_INVENTORY_BYTES = 1024 * 1024
_ENTRY = re.compile(r"([1-9][0-9]*); [0-9]+ [0-9]+ ([A-Z][A-Z ]* .+)")
_COUNT = re.compile(r";\s+TOC Entries: ([0-9]+)")
_EXTENSION = re.compile(r"EXTENSION - ([a-zA-Z_][a-zA-Z0-9_-]*)(?: [a-zA-Z_][a-zA-Z0-9_-]*)?\s*")
_UNREADABLE = "The backup inventory is incomplete or cannot be interpreted safely"


def validate_inventory(lines: Sequence[str]) -> None:
    if sum(len(line.encode("utf-8")) + 1 for line in lines) > MAX_INVENTORY_BYTES:
        raise ValueError("The backup inventory exceeds the inspection limit")
    count: int | None = None
    custom = False
    entries: set[int] = set()
    for line in lines:
        if not line.strip():
            continue
        header = _COUNT.fullmatch(line.rstrip())
        if header is not None:
            if count is not None:
                raise ValueError(_UNREADABLE)
            count = int(header[1])
            if count > MAX_INVENTORY_ENTRIES:
                raise ValueError("The backup inventory exceeds the inspection limit")
        if line.startswith(";"):
            custom = custom or line.strip() == ";     Format: CUSTOM"
            continue
        entry = _ENTRY.fullmatch(line.rstrip())
        if entry is None or int(entry[1]) in entries:
            raise ValueError(_UNREADABLE)
        entries.add(int(entry[1]))
        if len(entries) > MAX_INVENTORY_ENTRIES:
            raise ValueError("The backup inventory exceeds the inspection limit")
        description = entry[2]
        if description.startswith("EXTENSION "):
            extension = _EXTENSION.fullmatch(description)
            if extension is None:
                raise ValueError(_UNREADABLE)
            if extension[1].lower() == "timescaledb":
                raise ValueError("TimescaleDB archives cannot be restored in this version")
        if DEDICATED_SCHEMAS.intersection(description.split()):
            raise ValueError("TimescaleDB archives cannot be restored in this version")
    # --verbose includes special TOC entries as well as selected restore entries.
    if not custom or count is None or len(entries) != count:
        raise ValueError(_UNREADABLE)
