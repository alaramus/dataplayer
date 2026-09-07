"""Dedicated namespaces reserved for Timescale implementation objects (D122)."""

DEDICATED_SCHEMAS = frozenset(
    {
        "_timescaledb_catalog",
        "_timescaledb_config",
        "_timescaledb_cache",
        "_timescaledb_internal",
        "_timescaledb_debug",
        "_timescaledb_functions",
        "timescaledb_experimental",
        "timescaledb_information",
    }
)
