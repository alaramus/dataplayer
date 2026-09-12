-- What the file before this one could not do inside its transaction: filling
-- the continuous aggregate and putting the oldest chunks into the columnstore
-- are procedures that commit, so they are one statement of their own here.
--
-- Which routine converts a chunk, and whether it takes the Hypercore access
-- method, is read from the installed extension rather than named per release:
-- the same rule the adapter itself follows (D120).
DO $sample$
DECLARE
    target regclass;
    columnstore boolean;
    hypercore boolean;
BEGIN
    CALL public.refresh_continuous_aggregate('demo_lab.readings_hourly', NULL, NULL);

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

    -- The two oldest days, so the list of chunks holds both kinds at once.
    FOR target IN
        SELECT format('%I.%I', chunk_schema, chunk_name)::regclass
        FROM timescaledb_information.chunks
        WHERE hypertable_schema = 'demo_lab' AND hypertable_name = 'sensor_readings'
        ORDER BY range_start
        LIMIT 2
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
$sample$;
