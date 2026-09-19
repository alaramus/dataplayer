"""The bounded byte sniff shared by file readers."""

from pathlib import Path

SNIFF_BYTES = 4096


def looks_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return bytes_look_binary(handle.read(SNIFF_BYTES))


def bytes_look_binary(data: bytes) -> bool:
    return b"\x00" in data[:SNIFF_BYTES]
