-- BEFORE JSON string helper source, NOT_RUN under SQL denial.
DO $test$
DECLARE r modkit_events._parse_result;
BEGIN
    r := modkit_events._json_string(pg_catalog.decode('225c753030303022','hex'),0);
    IF r.value IS DISTINCT FROM pg_catalog.decode('00','hex') OR r.after_pos IS DISTINCT FROM 8 OR r.nodes IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'escaped NUL changed';
    END IF;
    r := modkit_events._json_string(pg_catalog.decode('225c75643833645c756465303022','hex'),0);
    IF r.value IS DISTINCT FROM pg_catalog.decode('f09f9880','hex') OR r.after_pos IS DISTINCT FROM 14 OR r.nodes IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'surrogate pair changed';
    END IF;
    r := modkit_events._json_string(pg_catalog.decode('225c756438303022','hex'),0);
    IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'unpaired surrogate accepted'; END IF;
    r := modkit_events._json_string(pg_catalog.decode('220022','hex'),0);
    IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'raw NUL accepted'; END IF;
END
$test$;
