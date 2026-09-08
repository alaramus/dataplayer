ALTER TABLE lab.metrics SET (timescaledb.compress, timescaledb.compress_orderby = 'observed_at');
ALTER TABLE lab.integer_metrics SET (timescaledb.compress, timescaledb.compress_orderby = 'tick');

DO $fixture$
DECLARE
    target regclass;
    modern boolean;
BEGIN
    SELECT extversion = '2.18.0' INTO modern FROM pg_extension WHERE extname = 'timescaledb';
    FOR target IN
        SELECT DISTINCT ON (hypertable_name) format('%I.%I', chunk_schema, chunk_name)::regclass
        FROM timescaledb_information.chunks
        WHERE hypertable_schema = 'lab' AND hypertable_name IN ('metrics', 'integer_metrics')
        ORDER BY hypertable_name, range_start, range_start_integer
    LOOP
        IF modern THEN
            CALL public.convert_to_columnstore(target, hypercore_use_access_method => true);
        ELSE
            PERFORM public.compress_chunk(target);
        END IF;
    END LOOP;
END
$fixture$;
