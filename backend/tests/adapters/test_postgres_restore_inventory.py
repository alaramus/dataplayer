import pytest

from app.adapters.postgres.restore_inventory import (
    MAX_INVENTORY_BYTES,
    validate_inventory,
)


def inventory(*entries: str) -> list[str]:
    return [
        "; Archive created at 2026-09-07",
        f";     TOC Entries: {len(entries)}",
        ";     Format: CUSTOM",
        "; Selected TOC Entries:",
        *entries,
    ]


def test_plain_verbose_inventory_includes_special_entries_and_dependencies() -> None:
    lines = inventory(
        "1; 0 0 ENCODING - ENCODING ",
        "2; 0 0 STDSTRINGS - STDSTRINGS ",
        "3; 3079 100 EXTENSION - plpgsql ",
    )
    lines.append(";\tdepends on: 3")
    validate_inventory(lines)


def test_timescale_extension_is_refused_even_when_far_from_the_tail() -> None:
    entries = ["1; 3079 123 EXTENSION - timescaledb "]
    entries.extend(f"{i}; 1259 {i} TABLE public table_{i} owner" for i in range(2, 101))
    with pytest.raises(ValueError, match="TimescaleDB"):
        validate_inventory(inventory(*entries))


@pytest.mark.parametrize("entry", [
    "1; 1259 42 TABLE _timescaledb_internal _hyper_1_2_chunk owner",
    "1; 0 0 TABLE DATA _timescaledb_catalog hypertable owner",
])
def test_internal_objects_are_refused_even_without_an_extension_entry(entry: str) -> None:
    with pytest.raises(ValueError, match="TimescaleDB"):
        validate_inventory(inventory(entry))


@pytest.mark.parametrize("lines", [
    [],
    ["pg_restore: error: unreadable archive"],
    [";     Format: CUSTOM", ";     TOC Entries: 2", "1; 1259 42 TABLE public x owner"],
    inventory("1; 3079 42 EXTENSION - \"ambiguous name\" "),
    inventory("1; 1259 42 TABLE public x owner", "1; 1259 42 TABLE public x owner"),
    [";" * (MAX_INVENTORY_BYTES + 1)],
])
def test_incomplete_ambiguous_or_oversized_inventory_refuses(lines: list[str]) -> None:
    with pytest.raises(ValueError):
        validate_inventory(lines)
