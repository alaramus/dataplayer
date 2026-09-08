GRANT USAGE ON SCHEMA lab, other TO fixture_reader, fixture_no_stats, fixture_no_metadata;
GRANT SELECT ON ALL TABLES IN SCHEMA lab, other TO fixture_reader, fixture_no_stats, fixture_no_metadata;
REVOKE USAGE ON SCHEMA timescaledb_information FROM PUBLIC;
GRANT USAGE ON SCHEMA timescaledb_information TO fixture_reader, fixture_no_stats;

REVOKE EXECUTE ON FUNCTION public.hypertable_detailed_size(regclass) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.hypertable_compression_stats(regclass) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.hypertable_detailed_size(regclass) TO fixture_reader;
GRANT EXECUTE ON FUNCTION public.hypertable_compression_stats(regclass) TO fixture_reader;

DO $fixture$
BEGIN
    IF to_regprocedure('public.hypertable_columnstore_stats(regclass)') IS NOT NULL THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.hypertable_columnstore_stats(regclass) FROM PUBLIC';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.hypertable_columnstore_stats(regclass) TO fixture_reader';
    END IF;
END
$fixture$;
