-- Authored BEFORE private binary validator source. NOT EXECUTED.
-- Requires a later authorized isolated PostgreSQL owner fixture with the exact
-- complete migration. Private helpers are deliberately not runtime-granted.
DO $test$
DECLARE
    frame pg_catalog.bytea;
    app pg_catalog.bytea;
    b pg_catalog.bytea;
    bad pg_catalog.bytea;
BEGIN
    app := pg_catalog.decode('00', 'hex');
    frame := pg_catalog.decode('4d4b5343010001000000', 'hex');
    IF modkit_events._scope_valid(frame, app, NULL, NULL) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'NUL optional-absent scope rejected';
    END IF;
    IF modkit_events._scope_valid(frame, pg_catalog.decode('01','hex'), NULL, NULL) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'projection mismatch accepted';
    END IF;
    FOREACH bad IN ARRAY ARRAY[
        pg_catalog.decode('c080','hex'), pg_catalog.decode('eda080','hex'),
        pg_catalog.decode('f4908080','hex'), pg_catalog.decode('80','hex'),
        pg_catalog.decode('e282','hex')
    ] LOOP
        IF modkit_events._utf8_valid(bad, 256, FALSE) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'malformed UTF8 accepted';
        END IF;
    END LOOP;
    IF modkit_events._utf8_valid(pg_catalog.decode('f48fbfbf00','hex'),256,TRUE) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'max Unicode scalar and NUL rejected';
    END IF;
    IF modkit_events._utf8_valid(pg_catalog.decode('09c2a0e38080','hex'),256,TRUE) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'whitespace-only scope accepted';
    END IF;
    app := pg_catalog.decode(pg_catalog.repeat('00',256),'hex');
    frame := pg_catalog.decode('4d4b5343010100','hex') || app ||
             pg_catalog.decode('010100','hex') || app ||
             pg_catalog.decode('010100','hex') || app;
    IF pg_catalog.octet_length(frame) <> 781 OR modkit_events._scope_valid(frame,app,app,app) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'maximum781 scope rejected';
    END IF;
    IF modkit_events._scope_valid(frame || pg_catalog.decode('00','hex'),app,app,app) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'trailing data accepted';
    END IF;
    IF modkit_events._scope_valid(pg_catalog.decode('4d4b5343010001610200','hex'),pg_catalog.decode('61','hex'),NULL,NULL) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'invalid optional tag accepted';
    END IF;
    b := pg_catalog.decode('4d4b504601000000000000000174000000020000000000000001610000000000000000','hex');
    IF modkit_events._record_fields(b,pg_catalog.decode('74','hex'),2) IS DISTINCT FROM
        ARRAY[pg_catalog.decode('61','hex'),pg_catalog.decode('','hex')]::pg_catalog.bytea[] THEN
        RAISE EXCEPTION 'MKPF fields changed';
    END IF;
END
$test$;
