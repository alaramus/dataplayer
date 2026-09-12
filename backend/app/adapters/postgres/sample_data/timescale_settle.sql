-- What the file before this one could not do inside its transaction: filling a
-- continuous aggregate and putting a chunk into the columnstore are procedures
-- that commit, and a script of several statements is one transaction to the
-- driver whatever autocommit says.
--
-- The policies are attached here too, and last. Added beside the tables they
-- act on, a job starts running against the demonstration while it is still
-- being written: a refresh policy took the aggregate's window a moment before
-- this file asked for it, and the refusal - a concurrent refresh - left the
-- whole thing half built.
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
    CALL public.refresh_continuous_aggregate('demo_lab.events_daily', NULL, NULL);

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
          AND NOT is_compressed
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

    -- And now the jobs, on a demonstration that is finished: compression of
    -- anything older than a week, an hourly refresh of the readings, and a
    -- retention window longer than the data is old, so that one is there to be
    -- read rather than to take anything away while somebody is looking at it.
    PERFORM public.add_compression_policy('demo_lab.sensor_readings', INTERVAL '7 days');
    PERFORM public.add_retention_policy('demo_lab.sensor_readings', INTERVAL '90 days');
    PERFORM public.add_continuous_aggregate_policy(
        'demo_lab.readings_hourly',
        start_offset => INTERVAL '3 days',
        end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '1 hour'
    );
END
$sample$;
