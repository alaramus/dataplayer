GRANT USAGE ON SCHEMA lab, other TO fixture_reader, fixture_no_stats, fixture_no_metadata;
GRANT SELECT ON ALL TABLES IN SCHEMA lab, other TO fixture_reader, fixture_no_stats, fixture_no_metadata;
REVOKE USAGE ON SCHEMA timescaledb_information FROM PUBLIC;
GRANT USAGE ON SCHEMA timescaledb_information TO fixture_reader, fixture_no_stats;

-- Size and compression statistics are renamed between releases, so each name is
-- restricted only where the installed version has it.
DO $fixture$
DECLARE
    routine text;
BEGIN
    FOREACH routine IN ARRAY ARRAY[
        'public.hypertable_detailed_size(regclass)',
        'public.hypertable_compression_stats(regclass)',
        'public.hypertable_columnstore_stats(regclass)'
    ] LOOP
        IF to_regprocedure(routine) IS NOT NULL THEN
            EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', routine);
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO fixture_reader', routine);
        END IF;
    END LOOP;
END
$fixture$;
