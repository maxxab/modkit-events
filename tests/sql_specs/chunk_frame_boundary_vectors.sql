-- SQAT1/SQAT3 prospective assertions. NOT_RUN, never a substitute SQL parser.
DO $test$
DECLARE r modkit_events._parse_result; raw pg_catalog.bytea; scalar pg_catalog.bytea;
    expected pg_catalog.bytea; i pg_catalog.int4; prefix_size pg_catalog.int4;
    frame pg_catalog.bytea; app pg_catalog.bytea; fields pg_catalog.bytea[];
BEGIN
    -- Assertion negative-controls: NULL cannot masquerade as either exact boolean.
    IF (NULL::pg_catalog.bool IS DISTINCT FROM TRUE) IS DISTINCT FROM TRUE
       OR (NULL::pg_catalog.bool IS DISTINCT FROM FALSE) IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'boolean assertion guard'; END IF;
    r := (pg_catalog.decode('61','hex'),NULL,NULL)::modkit_events._parse_result;
    IF (r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL) IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'partial rejection guard'; END IF;
    r := (pg_catalog.decode('61','hex'),NULL,0)::modkit_events._parse_result;
    IF (r.value IS DISTINCT FROM pg_catalog.decode('61','hex') OR r.after_pos IS DISTINCT FROM 3 OR r.nodes IS DISTINCT FROM 0) IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'partial positive guard'; END IF;
    FOREACH scalar IN ARRAY ARRAY[pg_catalog.decode('c2a2','hex'),pg_catalog.decode('e282ac','hex'),pg_catalog.decode('f09f9880','hex')] LOOP
      FOR prefix_size IN 4095..4097 LOOP
        expected := pg_catalog.convert_to(pg_catalog.repeat('a',prefix_size),'UTF8')||scalar;
        raw := pg_catalog.decode('22','hex')||expected||pg_catalog.decode('22','hex');
        r := modkit_events._json_string(raw,0);
        IF r.value IS DISTINCT FROM expected OR r.after_pos IS DISTINCT FROM (prefix_size+pg_catalog.octet_length(scalar)+2) OR r.nodes IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'UTF8 run split'; END IF;
        raw := pg_catalog.decode('22','hex')||pg_catalog.convert_to(pg_catalog.repeat('a',prefix_size),'UTF8')||pg_catalog.decode('5c7530303030','hex')||scalar||pg_catalog.decode('22','hex');
        r := modkit_events._json_string(raw,0);
        expected := pg_catalog.convert_to(pg_catalog.repeat('a',prefix_size),'UTF8')||pg_catalog.decode('00','hex')||scalar;
        IF r.value IS DISTINCT FROM expected OR r.after_pos IS DISTINCT FROM (prefix_size+pg_catalog.octet_length(scalar)+8) OR r.nodes IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'escape run split'; END IF;
      END LOOP;
    END LOOP;
    FOREACH raw IN ARRAY ARRAY[
      pg_catalog.decode('22','hex')||pg_catalog.convert_to(pg_catalog.repeat('a',4095),'UTF8')||pg_catalog.decode('e228a122','hex'),
      pg_catalog.decode('22','hex')||pg_catalog.convert_to(pg_catalog.repeat('a',8192),'UTF8')
    ] LOOP
      r := modkit_events._json_string(raw,0);
      IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'bad UTF8 or missing quote returned prefix'; END IF;
    END LOOP;
    FOREACH raw IN ARRAY ARRAY[
      pg_catalog.convert_to('['||pg_catalog.repeat('null,',1024)||'null','UTF8'),
      pg_catalog.convert_to('{"a":null,"b":null','UTF8')
    ] LOOP
      r := modkit_events._json_value(raw,0,0,262144);
      IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'missing collection marker returned prefix'; END IF;
    END LOOP;
    SELECT pg_catalog.convert_to('{'||pg_catalog.string_agg('"'||g.i::pg_catalog.text||'":null',',' ORDER BY g.i),'UTF8')
      INTO raw FROM pg_catalog.generate_series(1,1000) AS g(i);
    r := modkit_events._json_value(raw,0,0,262144);
    IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'many object children missing marker'; END IF;
    SELECT pg_catalog.convert_to('{'||pg_catalog.string_agg('"'||g.i::pg_catalog.text||'":null',',' ORDER BY g.i)||',"1":true}','UTF8')
      INTO raw FROM pg_catalog.generate_series(1,1000) AS g(i);
    IF modkit_events._json_to_j(raw) IS NOT NULL THEN RAISE EXCEPTION 'late duplicate accepted'; END IF;
    raw := pg_catalog.convert_to(E'{"é":null,"\\u0000":null,"":null}','UTF8');
    expected := pg_catalog.decode('6f00000003000000000000000000000000000000016e00000000000000010000000000000000016e0000000000000002c3a900000000000000016e','hex');
    IF modkit_events._json_to_j(raw) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'empty NUL nonASCII byte ordering'; END IF;
    raw := pg_catalog.convert_to('[null]','UTF8');
    r := modkit_events._json_value(raw,0,0,1);
    IF r.value IS NOT NULL OR r.after_pos IS NOT NULL OR r.nodes IS NOT NULL THEN RAISE EXCEPTION 'exhausted node budget'; END IF;
    r := modkit_events._json_value(raw,0,0,2);
    expected := pg_catalog.decode('610000000100000000000000016e','hex');
    IF r.value IS DISTINCT FROM expected OR r.after_pos IS DISTINCT FROM 6 OR r.nodes IS DISTINCT FROM 2 THEN RAISE EXCEPTION 'exact node budget'; END IF;
    IF modkit_events._j_nodes(expected,0,1) IS NOT NULL OR modkit_events._j_nodes(expected,0,2) IS DISTINCT FROM 2 THEN RAISE EXCEPTION 'canonical node budget'; END IF;
    raw := pg_catalog.convert_to('["'||pg_catalog.repeat('a',1048567)||'"]','UTF8');
    IF modkit_events._json_to_j(raw) IS NOT NULL THEN RAISE EXCEPTION 'valid child oversized parent'; END IF;
    -- MKPF single-byte tag t; independent count/length framing.
    frame := pg_catalog.decode('4d4b50460100000000000000017400000020','hex')||pg_catalog.decode(pg_catalog.repeat('0000000000000000',32),'hex');
    fields := modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),32);
    IF fields IS DISTINCT FROM pg_catalog.array_fill(''::pg_catalog.bytea,ARRAY[32]::pg_catalog.int4[]) THEN RAISE EXCEPTION '32 empty fields'; END IF;
    FOREACH frame IN ARRAY ARRAY[
      pg_catalog.decode('4d4b504601ffffffffffffffff','hex'),
      pg_catalog.decode('4d4b504601000000','hex'),
      pg_catalog.decode('4d4b50460100000000000000017400000001000000000000000261','hex'),
      pg_catalog.decode('4d4b50460100000000000000017400000001000000000000000000','hex')
    ] LOOP
      IF modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),1) IS NOT NULL THEN RAISE EXCEPTION 'adversarial frame accepted'; END IF;
    END LOOP;
    frame := pg_catalog.decode('4d4b50460100000000000000017400000021','hex')||pg_catalog.decode(pg_catalog.repeat('0000000000000000',33),'hex');
    IF modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),33) IS NOT NULL THEN RAISE EXCEPTION '33 fields accepted'; END IF;
    app := pg_catalog.convert_to(pg_catalog.repeat('a',256),'UTF8');
    frame := pg_catalog.decode('4d4b5343010100','hex')||app||pg_catalog.decode('0000','hex');
    IF modkit_events._scope_valid(frame,app,NULL,NULL) IS DISTINCT FROM TRUE THEN RAISE EXCEPTION '256 scope'; END IF;
    IF modkit_events._scope_valid(frame,app,pg_catalog.decode('61','hex'),NULL) IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'absence presence mismatch'; END IF;
    app := app||pg_catalog.decode('61','hex');
    frame := pg_catalog.decode('4d4b5343010101','hex')||app||pg_catalog.decode('0000','hex');
    IF modkit_events._scope_valid(frame,app,NULL,NULL) IS DISTINCT FROM FALSE THEN RAISE EXCEPTION '257 scope'; END IF;
END
$test$;

-- Correction3 reaching length/count cases. Existing short/parameter cases retained.
-- NOT_RUN. No production builder computes these byte frames.
DO $test$
DECLARE frame pg_catalog.bytea; fields pg_catalog.bytea[];
BEGIN
    -- Header5 + tag length8 + tag t1 + count4 + field length8 + byte a1 =27.
    frame := pg_catalog.decode('4d4b50460100000000000000017400000001000000000000000161','hex');
    fields := modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),1);
    IF fields IS DISTINCT FROM ARRAY[pg_catalog.decode('61','hex')]::pg_catalog.bytea[] THEN
        RAISE EXCEPTION 'valid field-length neighbor';
    END IF;
    --26 bytes: valid header/tag/count reaches field uint64 allFF at offset18.
    frame := pg_catalog.decode('4d4b50460100000000000000017400000001ffffffffffffffff','hex');
    IF modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),1) IS NOT NULL THEN
        RAISE EXCEPTION 'maximum uint64 field length accepted';
    END IF;
    --18 bytes: sufficient suffix passes outer minimum17 and reaches tag uint64.
    frame := pg_catalog.decode('4d4b504601ffffffffffffffff7400000000','hex');
    IF modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),0) IS NOT NULL THEN
        RAISE EXCEPTION 'maximum uint64 tag length accepted';
    END IF;
    -- Encoded33 reaches count decoder with valid expected p_count32.
    frame := pg_catalog.decode('4d4b50460100000000000000017400000021','hex')
          || pg_catalog.decode(pg_catalog.repeat('0000000000000000',33),'hex');
    IF modkit_events._record_fields(frame,pg_catalog.decode('74','hex'),32) IS NOT NULL THEN
        RAISE EXCEPTION 'encoded count33 accepted for valid requested32';
    END IF;
END
$test$;
