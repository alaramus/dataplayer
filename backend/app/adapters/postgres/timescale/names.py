"""Names Timescale owns (D122), and the one its actions are drawn under (D207)."""

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

# The submenu every Timescale management action is drawn in.
TIMESCALE_MENU = "Timescale"
