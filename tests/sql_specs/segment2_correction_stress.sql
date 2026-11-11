-- SQL-S2-R3 independent expected bytes. NOT_RUN. Owner fixture after authorized installation only.
DO $test$
DECLARE raw pg_catalog.bytea; expected pg_catalog.bytea; parsed modkit_events._parse_result;
    text_value pg_catalog.text; i pg_catalog.int4;
BEGIN
    -- Long unescaped input: decoded raw string max from a1MiB replay envelope.
    raw := pg_catalog.convert_to('"'||pg_catalog.repeat('a',1048574)||'"','UTF8');
    parsed := modkit_events._json_string(raw,0);
    IF parsed.value IS DISTINCT FROM pg_catalog.convert_to(pg_catalog.repeat('a',1048574),'UTF8') OR parsed.after_pos IS DISTINCT FROM 1048576 OR parsed.nodes IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'plain max string'; END IF;
    -- J scalar including its9-byte framing reaches exactly1MiB.
    raw := pg_catalog.convert_to('"'||pg_catalog.repeat('a',1048567)||'"','UTF8');
    expected := pg_catalog.decode('73','hex')||pg_catalog.int8send(1048567::pg_catalog.int8)||pg_catalog.convert_to(pg_catalog.repeat('a',1048567),'UTF8');
    IF modkit_events._json_to_j(raw) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'canonical max scalar'; END IF;
    raw := pg_catalog.convert_to('"'||pg_catalog.repeat('a',1048568)||'"','UTF8');
    IF modkit_events._json_to_j(raw) IS NOT NULL THEN RAISE EXCEPTION 'canonical overflow'; END IF;
    raw := pg_catalog.convert_to('"'||pg_catalog.repeat(E'\\u0000',174762)||'"','UTF8');
    parsed := modkit_events._json_string(raw,0);
    IF parsed.value IS DISTINCT FROM pg_catalog.decode(pg_catalog.repeat('00',174762),'hex') OR parsed.after_pos IS DISTINCT FROM 1048574 OR parsed.nodes IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'escaped NUL stress'; END IF;
    -- Reject missing closure after emitted chunks; no prefix success.
    raw := pg_catalog.convert_to('"'||pg_catalog.repeat('a',8192)||E'\\uD800"','UTF8');
    parsed := modkit_events._json_string(raw,0);
    IF parsed.value IS NOT NULL OR parsed.after_pos IS NOT NULL OR parsed.nodes IS NOT NULL THEN RAISE EXCEPTION 'partial malformed surrogate'; END IF;
    raw := pg_catalog.convert_to('['||pg_catalog.repeat('null,',65535)||'null]','UTF8');
    expected := pg_catalog.decode('6100010000','hex')||pg_catalog.decode(pg_catalog.repeat('00000000000000016e',65536),'hex');
    IF modkit_events._json_to_j(raw) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'many array entries'; END IF;
    raw := pg_catalog.convert_to('['||pg_catalog.repeat('null,',65536)||'null]','UTF8');
    IF modkit_events._json_to_j(raw) IS NOT NULL THEN RAISE EXCEPTION 'entry overflow'; END IF;
    -- Sorted raw keys, not input order; exact independent fixture.
    raw := pg_catalog.convert_to('{"z":null,"a":true}','UTF8');
    expected := pg_catalog.decode('6f0000000200000000000000016100000000000000017400000000000000017a00000000000000016e','hex');
    IF modkit_events._json_to_j(raw) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'object sorting'; END IF;
    raw := pg_catalog.convert_to(E'{"a":null,"\\u0061":true}','UTF8');
    IF modkit_events._json_to_j(raw) IS NOT NULL THEN RAISE EXCEPTION 'decoded duplicate'; END IF;
    -- Independent many-small-object stress, descending input, ascending expected.
    SELECT '{'||pg_catalog.string_agg('"'||pg_catalog.lpad(g.i::pg_catalog.text,5,'0')||'":null',',' ORDER BY g.i DESC)||'}',
        pg_catalog.decode('6f','hex')||pg_catalog.int4send(30000)||pg_catalog.string_agg(
          pg_catalog.int8send(5::pg_catalog.int8)||pg_catalog.convert_to(pg_catalog.lpad(g.i::pg_catalog.text,5,'0'),'UTF8')||pg_catalog.decode('00000000000000016e','hex'),''::pg_catalog.bytea ORDER BY g.i)
      INTO text_value,expected FROM pg_catalog.generate_series(1,30000) AS g(i);
    IF modkit_events._json_to_j(pg_catalog.convert_to(text_value,'UTF8')) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'many object entries'; END IF;
    text_value := pg_catalog.repeat('[',32)||'null'||pg_catalog.repeat(']',32);
    expected := pg_catalog.decode('6e','hex');
    FOR i IN 1..32 LOOP expected := pg_catalog.decode('6100000001','hex')||pg_catalog.int8send(pg_catalog.octet_length(expected)::pg_catalog.int8)||expected; END LOOP;
    IF modkit_events._json_to_j(pg_catalog.convert_to(text_value,'UTF8')) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'depth32'; END IF;
    IF modkit_events._json_to_j(pg_catalog.convert_to('['||text_value||']','UTF8')) IS NOT NULL THEN RAISE EXCEPTION 'depth33'; END IF;
END
$test$;
