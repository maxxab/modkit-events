-- NEW prospective S13: owner-structural E28 reader ONLY. NOT_RUN/not parsed.
-- Disposable caller READ COMMITTED transaction; setup is not public enqueue provenance.
DO $test$
DECLARE
    e pg_catalog.bytea:='outbox-reader'::pg_catalog.bytea;
    replay pg_catalog.bytea:=pg_catalog.convert_to('{"event_id":"outbox-reader","name":"cmd","schema_version":2147483648,"payload":{},"metadata":{}}','UTF8');
    envelope pg_catalog.bytea; t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    tok pg_catalog.uuid:='13000000-0000-0000-0000-000000000001';
    intent pg_catalog.uuid:='13000000-0000-0000-0000-000000000002';
    phase pg_catalog.text; stored pg_catalog.record; observed pg_catalog.record;
    k pg_catalog.int4; contents pg_catalog.jsonb; relation_name pg_catalog.text;
    before_state pg_catalog.jsonb; after_state pg_catalog.jsonb;
BEGIN
    envelope:=modkit_events._event_replay_frame(replay);
    IF envelope IS NULL THEN RAISE EXCEPTION 'S13 valid replay setup failed'; END IF;
    before_state:='{}'::pg_catalog.jsonb;
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
    IF EXISTS(SELECT FROM modkit_events.e28(e)) THEN RAISE EXCEPTION 'S13 absent row returned'; END IF;
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
    IF before_state IS DISTINCT FROM after_state THEN RAISE EXCEPTION 'S13 absent reader changed footprint'; END IF;
    INSERT INTO modkit_events.outbox(event_id,canonical_version,envelope_evidence,replay_input,state,
        ownership_revision,created_at,updated_at)
        VALUES(e,1,envelope,replay,'pending',0,t,t);
    FOREACH phase IN ARRAY ARRAY['pending','claimed','publishing','published','rejected','held']::pg_catalog.text[] LOOP
        UPDATE modkit_events.outbox SET state=phase,
            token=CASE WHEN phase IN ('claimed','publishing') THEN tok ELSE NULL END,
            lease_until=CASE WHEN phase IN ('claimed','publishing') THEN t ELSE NULL END,
            ownership_revision=CASE WHEN phase IN ('claimed','publishing') THEN 1 ELSE 0 END,
            intent_id=CASE WHEN phase IN ('pending','claimed') THEN NULL ELSE intent END,
            receipt=''::pg_catalog.bytea,outcome_evidence=''::pg_catalog.bytea WHERE event_id=e;
        SELECT * INTO STRICT stored FROM modkit_events.outbox WHERE event_id=e;
        before_state:='{}'::pg_catalog.jsonb;
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
        SELECT * INTO STRICT observed FROM modkit_events.e28(e);
        IF pg_catalog.to_jsonb(observed) IS DISTINCT FROM (pg_catalog.to_jsonb(stored)-'event_digest') THEN
            RAISE EXCEPTION 'S13 full13 projection differs'; END IF;
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
        IF before_state IS DISTINCT FROM after_state THEN RAISE EXCEPTION 'S13 reader changed footprint'; END IF;
    END LOOP;
    -- Each mutation is accepted by current table CHECKs. No trigger/schema bypass.
    FOR k IN 1..3 LOOP
        UPDATE modkit_events.outbox SET state='claimed',token=tok,lease_until=t,ownership_revision=1,
            intent_id=NULL,envelope_evidence=envelope,replay_input=replay,updated_at=t WHERE event_id=e;
        IF k=1 THEN UPDATE modkit_events.outbox SET replay_input='x'::pg_catalog.bytea WHERE event_id=e;
        ELSIF k=2 THEN UPDATE modkit_events.outbox SET updated_at='infinity'::pg_catalog.timestamptz WHERE event_id=e;
        ELSE UPDATE modkit_events.outbox SET ownership_revision=0 WHERE event_id=e; END IF;
        before_state:='{}'::pg_catalog.jsonb;
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
        BEGIN
            PERFORM * FROM modkit_events.e28(e);
            RAISE EXCEPTION 'S13 malformed selected row returned';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL; END;
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
        IF before_state IS DISTINCT FROM after_state THEN RAISE EXCEPTION 'S13 rejected reader changed footprint'; END IF;
    END LOOP;
END
$test$;
