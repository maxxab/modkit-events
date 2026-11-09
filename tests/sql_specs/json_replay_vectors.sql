-- BEFORE enclosing JSON parser source. All statements NOT_RUN.
DO $test$
DECLARE bad pg_catalog.text;
BEGIN
    IF modkit_events._json_to_j(pg_catalog.convert_to('[1]','UTF8')) IS DISTINCT FROM
       pg_catalog.decode('6100000001000000000000000a69000000000000000131','hex') THEN
        RAISE EXCEPTION 'array canonical byte vector differs';
    END IF;
    IF modkit_events._json_to_j(pg_catalog.convert_to('0.0','UTF8')) IS DISTINCT FROM
       pg_catalog.decode('6400000000000000083078302e30702b30','hex') THEN
        RAISE EXCEPTION 'float type lost';
    END IF;
    IF modkit_events._json_to_j(pg_catalog.convert_to('{"b":2,"a":1}','UTF8')) IS DISTINCT FROM
       pg_catalog.decode('6f00000002000000000000000161000000000000000a69000000000000000131000000000000000162000000000000000a69000000000000000132','hex') THEN
        RAISE EXCEPTION 'object key order leaks into identity';
    END IF;
    FOREACH bad IN ARRAY ARRAY['[1,]','{"a":1,}','{"a":1,"a":2}','truex','+1','01','1.','{"a" 1}'] LOOP
        IF modkit_events._json_to_j(pg_catalog.convert_to(bad,'UTF8')) IS NOT NULL THEN
            RAISE EXCEPTION 'invalid replay accepted';
        END IF;
    END LOOP;
    IF modkit_events._json_to_j(pg_catalog.decode('efbbbf6e756c6c','hex')) IS NOT NULL THEN
        RAISE EXCEPTION 'UTF8 BOM accepted';
    END IF;
END
$test$;
