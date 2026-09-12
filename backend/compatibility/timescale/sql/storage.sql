ALTER TABLE lab.metrics SET (timescaledb.compress, timescaledb.compress_orderby = 'observed_at');
ALTER TABLE lab.integer_metrics SET (timescaledb.compress, timescaledb.compress_orderby = 'tick');

-- The routine that converts a chunk, and whether it takes the Hypercore access
-- method, are read from the installed version rather than named per release.
DO $fixture$
DECLARE
    target regclass;
    columnstore boolean;
    hypercore boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = 'public' AND routine.proname = 'convert_to_columnstore'
    ), EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = 'public' AND routine.proname = 'convert_to_columnstore'
          AND 'hypercore_use_access_method' = ANY (routine.proargnames)
    ) INTO columnstore, hypercore;
    FOR target IN
        SELECT DISTINCT ON (hypertable_name) format('%I.%I', chunk_schema, chunk_name)::regclass
        FROM timescaledb_information.chunks
        WHERE hypertable_schema = 'lab' AND hypertable_name IN ('metrics', 'integer_metrics')
        ORDER BY hypertable_name, range_start, range_start_integer
    LOOP
        IF hypercore THEN
            CALL public.convert_to_columnstore(target, hypercore_use_access_method => true);
        ELSIF columnstore THEN
            CALL public.convert_to_columnstore(target);
        ELSE
            PERFORM public.compress_chunk(target);
        END IF;
    END LOOP;
END
$fixture$;
