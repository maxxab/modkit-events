-- Authored before corresponding helpers. NOT_RUN; SQL execution denied.
DO $test$
BEGIN
    IF modkit_events._optional_bytes(NULL) IS DISTINCT FROM pg_catalog.decode('30','hex')
       OR modkit_events._optional_bytes(''::pg_catalog.bytea) IS DISTINCT FROM pg_catalog.decode('310000000000000000','hex') THEN
        RAISE EXCEPTION 'optional null and empty are not distinct';
    END IF;
    IF modkit_events._instant_bytes('2026-11-06 07:08:09.123456+02'::pg_catalog.timestamptz)
       IS DISTINCT FROM pg_catalog.convert_to('2026-11-06T05:08:09.123456Z','UTF8') THEN
        RAISE EXCEPTION 'UTC instant encoding differs';
    END IF;
    IF modkit_events._instant_bytes('infinity'::pg_catalog.timestamptz) IS NOT NULL
       OR modkit_events._instant_bytes('0001-01-01 BC'::pg_catalog.timestamptz) IS NOT NULL
       OR modkit_events._instant_bytes('10000-01-01 AD'::pg_catalog.timestamptz) IS NOT NULL THEN
        RAISE EXCEPTION 'out of managed timestamp domain accepted';
    END IF;
END
$test$;
