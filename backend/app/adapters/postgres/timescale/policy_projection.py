"""Allowlisted policy parameters, evaluated at the source (D121)."""

from psycopg import sql

# A routine name alone cannot certify a user job as an extension policy. Reads the
# jobs view under the alias `source`.
OWNED_POLICY_ROUTINE = sql.SQL("""EXISTS (
    SELECT 1 FROM pg_catalog.pg_proc AS p
    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
    JOIN pg_catalog.pg_depend AS d
      ON d.classid = 'pg_catalog.pg_proc'::regclass AND d.objid = p.oid
     AND d.refclassid = 'pg_catalog.pg_extension'::regclass AND d.deptype = 'e'
    JOIN pg_catalog.pg_extension AS e ON e.oid = d.refobjid
    WHERE e.extname = 'timescaledb' AND n.nspname = source.proc_schema
      AND p.proname = source.proc_name AND p.prokind = 'p'
      AND p.pronargs = 2 AND p.proargtypes = '23 3802'::pg_catalog.oidvector
)""")

def validated_interval(key: str) -> sql.Composed:
    """One interval setting of `source.config`, or NULL when absent, null or malformed."""
    value = sql.SQL("source.config ->> {}").format(sql.Literal(key))
    # The cast applies to NULL or validated text only; malformed config is never echoed.
    return sql.SQL(
        "(CASE WHEN pg_catalog.jsonb_typeof(source.config -> {key}) = 'string' "
        "AND pg_catalog.length({value}) <= 128 "
        "AND pg_catalog.pg_input_is_valid({value}, 'pg_catalog.interval') "
        "THEN {value} END)::pg_catalog.interval::text"
    ).format(key=sql.Literal(key), value=value)


_POLICIES = (
    ("policy_retention", "retention", ("drop_after", "drop_created_before")),
    ("policy_compression", "compression", ("compress_after", "compress_created_before")),
    ("policy_refresh_continuous_aggregate", "refresh", ("start_offset", "end_offset")),
)


def policy_columns() -> tuple[sql.Composed, ...]:
    kind = sql.SQL("CASE WHEN {} THEN CASE source.proc_name {} END END AS policy_kind").format(
        OWNED_POLICY_ROUTINE,
        sql.SQL(" ").join(
            sql.SQL("WHEN {} THEN {}").format(sql.Literal(routine), sql.Literal(label))
            for routine, label, _ in _POLICIES
        ),
    )
    columns = [kind]
    for routine, _, keys in _POLICIES:
        for key in keys:
            value = sql.SQL("source.config ->> {}").format(sql.Literal(key))
            json_type = sql.SQL("pg_catalog.jsonb_typeof(source.config -> {})").format(sql.Literal(key))
            guard = sql.SQL("{} AND source.proc_name = {}").format(OWNED_POLICY_ROUTINE, sql.Literal(routine))
            # Canonical interval output never echoes malformed source strings.
            columns.append(sql.SQL("""CASE WHEN {} THEN
                CASE WHEN {} = 'string' AND length({}) <= 128 THEN
                    (CASE WHEN pg_catalog.pg_input_is_valid({}, 'pg_catalog.interval')
                         THEN {} END)::pg_catalog.interval::text
                END END AS {}""").format(
                    guard, json_type, value, value, value, sql.Identifier(f"{key}_interval"),
                ))
            if not key.endswith("created_before"):
                columns.append(sql.SQL("""CASE WHEN {} THEN
                    CASE WHEN {} = 'number' AND length({}) <= 20 THEN
                        (CASE WHEN pg_catalog.pg_input_is_valid({}, 'pg_catalog.int8')
                             THEN {} END)::pg_catalog.int8
                    END END AS {}""").format(
                        guard, json_type, value, value, value, sql.Identifier(f"{key}_integer"),
                    ))
    return tuple(columns)
