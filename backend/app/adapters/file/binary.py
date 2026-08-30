"""The bounded byte sniff shared by file readers."""

from pathlib import Path

SNIFF_BYTES = 4096


def looks_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(SNIFF_BYTES)
