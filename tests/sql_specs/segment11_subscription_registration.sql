-- Prospective E01 registration→following-command E18 controls; AB-SQLv2.
-- NOT_RUN/not parsed; requires future reviewed E01 body and root setup/ROLLBACK.
-- Owner structural seeds below pass intact subscription rules; no bypass.
DO $test$
DECLARE
    new_id pg_catalog.bytea:=pg_catalog.decode('610062','hex');
    new_group pg_catalog.bytea:=pg_catalog.convert_to(pg_catalog.repeat('é',128),'UTF8');
    opaque pg_catalog.bytea:=pg_catalog.decode('ff00','hex');
    large_manifest pg_catalog.bytea:=pg_catalog.decode(pg_catalog.repeat('00',1048576),'hex');
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    created_time pg_catalog.timestamptz; observed pg_catalog.record; result_row pg_catalog.record;
    bad_bytes pg_catalog.bytea; k pg_catalog.int4; n pg_catalog.int8;
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
    after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
    relation_name pg_catalog.text; contents pg_catalog.jsonb;
BEGIN
    -- No subscriptions user trigger/FK/generated column exists. IDs/groups and
    -- bounds pass table checks; infinity created_at is table-legal but reader-invalid.
    INSERT INTO modkit_events.subscriptions VALUES
        ('s11-seed'::pg_catalog.bytea,opaque,'seed-group'::pg_catalog.bytea,3,2,t),
        ('s11-large'::pg_catalog.bytea,large_manifest,'large-group'::pg_catalog.bytea,1,1,t),
        ('s11-bad-time'::pg_catalog.bytea,''::pg_catalog.bytea,'bad-group'::pg_catalog.bytea,3,0,'infinity');
    FOREACH relation_name IN ARRAY ARRAY['schema_versions','subscriptions','work','inbox','job_payloads','attempts',
        'finalization_guards','work_history','delivery_history','outbox','publication_history','mutation_operations',
        'work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq']::pg_catalog.text[] LOOP
        IF relation_name IN ('work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq') THEN
            EXECUTE pg_catalog.format('SELECT pg_catalog.jsonb_build_object(''last_value'',last_value,''log_cnt'',log_cnt,''is_called'',is_called) FROM %I.%I',
                'modkit_events',relation_name) INTO contents;
        ELSE
            EXECUTE pg_catalog.format('SELECT COALESCE(jsonb_agg(v ORDER BY v::text COLLATE pg_catalog."C"),''[]''::jsonb) FROM (SELECT to_jsonb(x) v FROM %I.%I x) q',
                'modkit_events',relation_name) INTO contents;
        END IF;
        before_state:=before_state||pg_catalog.jsonb_build_object(relation_name,contents);
    END LOOP;

    -- E01 Unit is exactly one literal true, never inserted/status/count metadata.
    SELECT r.* INTO STRICT result_row FROM modkit_events.e01(new_id,''::pg_catalog.bytea,new_group,2147483647) r;
    IF result_row.ok IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S11 E01 first registration Unit differs'; END IF;
    -- Separate SPI SELECT after E01: no same-invoking-command STABLE visibility assumption.
    SELECT r.* INTO STRICT observed FROM modkit_events.e18(new_id) r;
    IF observed.subscription_id IS DISTINCT FROM new_id OR observed.manifest IS DISTINCT FROM ''::pg_catalog.bytea
       OR observed.consumer_group IS DISTINCT FROM new_group OR observed.capacity IS DISTINCT FROM 2147483647
       OR observed.nonterminal_count IS DISTINCT FROM 0 OR modkit_events._instant_bytes(observed.created_at) IS NULL THEN
        RAISE EXCEPTION 'S11 first registration six-field evidence differs';
    END IF;
    created_time:=observed.created_at;
    FOREACH relation_name IN ARRAY ARRAY['schema_versions','subscriptions','work','inbox','job_payloads','attempts',
        'finalization_guards','work_history','delivery_history','outbox','publication_history','mutation_operations',
        'work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq']::pg_catalog.text[] LOOP
        IF relation_name IN ('work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq') THEN
            EXECUTE pg_catalog.format('SELECT pg_catalog.jsonb_build_object(''last_value'',last_value,''log_cnt'',log_cnt,''is_called'',is_called) FROM %I.%I',
                'modkit_events',relation_name) INTO contents;
        ELSE
            EXECUTE pg_catalog.format('SELECT COALESCE(jsonb_agg(v ORDER BY v::text COLLATE pg_catalog."C"),''[]''::jsonb) FROM (SELECT to_jsonb(x) v FROM %I.%I x) q',
                'modkit_events',relation_name) INTO contents;
        END IF;
        after_state:=after_state||pg_catalog.jsonb_build_object(relation_name,contents);
    END LOOP;

    IF (after_state-'subscriptions') IS DISTINCT FROM (before_state-'subscriptions') THEN
        RAISE EXCEPTION 'S11 registration changed non-subscription footprint'; END IF;
    SELECT COALESCE(pg_catalog.jsonb_agg(v ORDER BY v::pg_catalog.text COLLATE pg_catalog."C"),'[]'::pg_catalog.jsonb)
      INTO contents FROM (SELECT pg_catalog.to_jsonb(s) AS v FROM modkit_events.subscriptions AS s WHERE s.subscription_id<>new_id) q;
    IF contents IS DISTINCT FROM before_state->'subscriptions' THEN
        RAISE EXCEPTION 'S11 registration changed unrelated subscription'; END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.subscriptions;
    IF n IS DISTINCT FROM 4 THEN RAISE EXCEPTION 'S11 first registration cardinality differs'; END IF;
    before_state:=after_state;
    -- Identical repeat preserves created_at and count; no reset/rewrites.
    SELECT r.* INTO STRICT result_row FROM modkit_events.e01(new_id,''::pg_catalog.bytea,new_group,2147483647) r;
    IF result_row.ok IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S11 repeat Unit differs'; END IF;
    SELECT r.* INTO STRICT observed FROM modkit_events.e18(new_id) r;
    IF observed.subscription_id IS DISTINCT FROM new_id OR observed.manifest IS DISTINCT FROM ''::pg_catalog.bytea
       OR observed.consumer_group IS DISTINCT FROM new_group OR observed.capacity IS DISTINCT FROM 2147483647
       OR observed.nonterminal_count IS DISTINCT FROM 0 OR observed.created_at IS DISTINCT FROM created_time THEN
        RAISE EXCEPTION 'S11 repeat changed registration'; END IF;
    SELECT r.* INTO STRICT result_row FROM modkit_events.e01('s11-seed'::pg_catalog.bytea,opaque,'seed-group'::pg_catalog.bytea,3) r;
    IF result_row.ok IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S11 existing parent repeat Unit differs'; END IF;
    SELECT r.* INTO STRICT observed FROM modkit_events.e18('s11-seed'::pg_catalog.bytea) r;
    IF observed.subscription_id IS DISTINCT FROM 's11-seed'::pg_catalog.bytea OR observed.manifest IS DISTINCT FROM opaque
       OR observed.consumer_group IS DISTINCT FROM 'seed-group'::pg_catalog.bytea OR observed.capacity IS DISTINCT FROM 3
       OR observed.nonterminal_count IS DISTINCT FROM 2 OR observed.created_at IS DISTINCT FROM t THEN
        RAISE EXCEPTION 'S11 existing parent count/time/evidence changed'; END IF;
    SELECT r.* INTO STRICT result_row FROM modkit_events.e01('s11-large'::pg_catalog.bytea,large_manifest,'large-group'::pg_catalog.bytea,1) r;
    IF result_row.ok IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S11 max opaque manifest repeat differs'; END IF;
    -- Full manifest/group/capacity conflicts each reject after stored integrity.
    FOR k IN 1..3 LOOP
        BEGIN
            PERFORM * FROM modkit_events.e01('s11-seed'::pg_catalog.bytea,
                CASE WHEN k=1 THEN ''::pg_catalog.bytea ELSE opaque END,
                CASE WHEN k=2 THEN 'other-group'::pg_catalog.bytea ELSE 'seed-group'::pg_catalog.bytea END,
                CASE WHEN k=3 THEN 4 ELSE 3 END);
            RAISE EXCEPTION 'S11 immutable registration conflict returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ002' THEN NULL;
        END;
    END LOOP;
    -- Same and conflicting caller inputs both see malformed stored time asPZ012.
    FOR k IN 0..1 LOOP
        BEGIN
            PERFORM * FROM modkit_events.e01('s11-bad-time'::pg_catalog.bytea,
                CASE WHEN k=1 THEN opaque ELSE ''::pg_catalog.bytea END,'bad-group'::pg_catalog.bytea,3);
            RAISE EXCEPTION 'S11 malformed existing parent returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
    END LOOP;
    FOREACH bad_bytes IN ARRAY ARRAY[NULL::pg_catalog.bytea,''::pg_catalog.bytea,' '::pg_catalog.bytea,
        pg_catalog.decode('ff','hex'),pg_catalog.convert_to(pg_catalog.repeat('a',257),'UTF8')]::pg_catalog.bytea[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e01(bad_bytes,''::pg_catalog.bytea,new_group,1);
            RAISE EXCEPTION 'S11 invalid subscription input returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
        BEGIN
            PERFORM * FROM modkit_events.e01(new_id,''::pg_catalog.bytea,bad_bytes,1);
            RAISE EXCEPTION 'S11 invalid group input returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
    END LOOP;
    FOR k IN 0..1 LOOP
        BEGIN
            PERFORM * FROM modkit_events.e01(new_id,CASE WHEN k=0 THEN NULL::pg_catalog.bytea
                ELSE pg_catalog.decode(pg_catalog.repeat('00',1048577),'hex') END,new_group,1);
            RAISE EXCEPTION 'S11 invalid manifest input returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
    END LOOP;
    FOREACH k IN ARRAY ARRAY[NULL::pg_catalog.int4,0,-1]::pg_catalog.int4[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e01(new_id,''::pg_catalog.bytea,new_group,k);
            RAISE EXCEPTION 'S11 invalid capacity input returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
    END LOOP;
    BEGIN
        PERFORM * FROM modkit_events.e01(new_id,''::pg_catalog.bytea,new_group,2147483648::pg_catalog.int4);
        RAISE EXCEPTION 'S11 native int4 overflow returned normally';
    EXCEPTION WHEN SQLSTATE '22003' THEN NULL;
    END;
    after_state:='{}'::pg_catalog.jsonb;
    FOREACH relation_name IN ARRAY ARRAY['schema_versions','subscriptions','work','inbox','job_payloads','attempts',
        'finalization_guards','work_history','delivery_history','outbox','publication_history','mutation_operations',
        'work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq']::pg_catalog.text[] LOOP
        IF relation_name IN ('work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq') THEN
            EXECUTE pg_catalog.format('SELECT pg_catalog.jsonb_build_object(''last_value'',last_value,''log_cnt'',log_cnt,''is_called'',is_called) FROM %I.%I',
                'modkit_events',relation_name) INTO contents;
        ELSE
            EXECUTE pg_catalog.format('SELECT COALESCE(jsonb_agg(v ORDER BY v::text COLLATE pg_catalog."C"),''[]''::jsonb) FROM (SELECT to_jsonb(x) v FROM %I.%I x) q',
                'modkit_events',relation_name) INTO contents;
        END IF;
        after_state:=after_state||pg_catalog.jsonb_build_object(relation_name,contents);
    END LOOP;

    IF after_state IS DISTINCT FROM before_state THEN
        RAISE EXCEPTION 'S11 repeat/rejected families changed full fixture footprint'; END IF;
END
$test$;
