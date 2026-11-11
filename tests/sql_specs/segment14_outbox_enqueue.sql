-- NEW prospective S14: lawful E02 enqueue provenance. NOT_RUN/not parsed.
-- Disposable caller READ COMMITTED transaction; no owner outbox/history setup writes.
DO $test$
DECLARE
    e pg_catalog.bytea:='outbox-enqueue'::pg_catalog.bytea;
    replay pg_catalog.bytea:=pg_catalog.convert_to('{"event_id":"outbox-enqueue","name":"cmd","schema_version":2147483648,"payload":{},"metadata":{}}','UTF8');
    envelope pg_catalog.bytea; alternate pg_catalog.bytea; candidate_envelope pg_catalog.bytea;
    receipt pg_catalog.record; observed pg_catalog.record; first_row pg_catalog.record; history pg_catalog.record;
    contents pg_catalog.jsonb; relation_name pg_catalog.text; n pg_catalog.int8; k pg_catalog.int4;
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb; after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
BEGIN
    envelope:=modkit_events._event_replay_frame(replay);
    IF envelope IS NULL THEN RAISE EXCEPTION 'S14 valid replay setup failed'; END IF;
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
    SELECT * INTO STRICT receipt FROM modkit_events.e02(e,1,envelope,replay);
    IF receipt.inserted IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S14 first receipt differs'; END IF;
    SELECT * INTO STRICT observed FROM modkit_events.e28(e);
    IF observed.event_id IS DISTINCT FROM e OR observed.canonical_version IS DISTINCT FROM 1
       OR observed.envelope_evidence IS DISTINCT FROM envelope OR observed.replay_input IS DISTINCT FROM replay
       OR observed.state IS DISTINCT FROM 'pending' OR observed.token IS NOT NULL
       OR observed.ownership_revision IS DISTINCT FROM 0 OR observed.lease_until IS NOT NULL
       OR observed.intent_id IS NOT NULL OR observed.receipt IS NOT NULL OR observed.outcome_evidence IS NOT NULL
       OR modkit_events._instant_bytes(observed.created_at) IS NULL
       OR modkit_events._instant_bytes(observed.updated_at) IS NULL THEN
        RAISE EXCEPTION 'S14 first full13 differs'; END IF;
    first_row:=observed;
    SELECT * INTO STRICT history FROM modkit_events.publication_history WHERE event_id=e;
    IF history.history_id<=0 OR history.event_id IS DISTINCT FROM e
       OR history.event_digest IS DISTINCT FROM pg_catalog.sha256(e)
       OR history.intent_id IS NOT NULL OR history.operation_id IS NOT NULL OR history.receipt IS NOT NULL
       OR history.status IS DISTINCT FROM 'enqueue' OR history.evidence IS DISTINCT FROM ''::pg_catalog.bytea
       OR history.binding IS DISTINCT FROM ''::pg_catalog.bytea
       OR history.recorded_at IS DISTINCT FROM first_row.updated_at
       OR modkit_events._instant_bytes(history.recorded_at) IS NULL THEN
        RAISE EXCEPTION 'S14 enqueue history differs'; END IF;
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
    IF (after_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']::pg_catalog.text[])
        IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']::pg_catalog.text[]) THEN
        RAISE EXCEPTION 'S14 new enqueue changed unrelated footprint'; END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.outbox;
    IF n<>1 THEN RAISE EXCEPTION 'S14 extra outbox row'; END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.publication_history;
    IF n<>1 THEN RAISE EXCEPTION 'S14 extra publication history'; END IF;
    -- Next baseline includes all selected rows plus all three sequence scalars.
    before_state:=after_state;
    SELECT * INTO STRICT receipt FROM modkit_events.e02(e,1,envelope,replay);
    IF receipt.inserted IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'S14 duplicate receipt differs'; END IF;
    SELECT * INTO STRICT observed FROM modkit_events.e28(e);
    IF pg_catalog.to_jsonb(observed) IS DISTINCT FROM pg_catalog.to_jsonb(first_row) THEN
        RAISE EXCEPTION 'S14 duplicate rewrote full outbox'; END IF;
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
    IF before_state IS DISTINCT FROM after_state THEN RAISE EXCEPTION 'S14 duplicate changed footprint'; END IF;
    -- Both alternatives are well-typed, helper-valid, complete EventInput.
    FOR k IN 1..2 LOOP
        IF k=1 THEN alternate:=pg_catalog.convert_to(' {"event_id":"outbox-enqueue","name":"cmd","schema_version":2147483648,"payload":{},"metadata":{}} ','UTF8');
        ELSE alternate:=pg_catalog.convert_to('{"event_id":"outbox-enqueue","name":"changed","schema_version":2147483648,"payload":{},"metadata":{}}','UTF8'); END IF;
        candidate_envelope:=modkit_events._event_replay_frame(alternate);
        IF candidate_envelope IS NULL THEN RAISE EXCEPTION 'S14 conflict input invalid'; END IF;
        IF k=1 AND candidate_envelope IS DISTINCT FROM envelope THEN RAISE EXCEPTION 'S14 whitespace canonical changed'; END IF;
        BEGIN
            PERFORM * FROM modkit_events.e02(e,1,candidate_envelope,alternate);
            RAISE EXCEPTION 'S14 changed full replay/intent returned';
        EXCEPTION WHEN SQLSTATE 'PZ002' THEN NULL; END;
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
        IF before_state IS DISTINCT FROM after_state THEN RAISE EXCEPTION 'S14 conflict changed footprint'; END IF;
    END LOOP;
END
$test$;
