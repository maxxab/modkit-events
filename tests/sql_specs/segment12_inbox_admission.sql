-- Prospective E03 inbox-only slice under selected e03-contract-decision-v2. NOT_RUN/not parsed.
-- Body release/independent correction closure still required; E02 independent; W01 held.
DO $test$
DECLARE
    sub pg_catalog.bytea:='s12-sub'::pg_catalog.bytea;
    work_value pg_catalog.uuid:='9e030000-0000-0000-0000-000000000010';
    original_id pg_catalog.uuid:='9e030000-0000-0000-0000-000000000010';
    scope_bytes pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    obj pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    key_value pg_catalog.bytea:='key-a'::pg_catalog.bytea;
    event_value pg_catalog.bytea:='s12-event'::pg_catalog.bytea;
    broker pg_catalog.bytea:=''::pg_catalog.bytea; transport pg_catalog.bytea:=''::pg_catalog.bytea;
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    binding pg_catalog.bytea; replay pg_catalog.bytea; semantic pg_catalog.bytea; intent pg_catalog.bytea;
    max_value pg_catalog.int4:=2; receipt pg_catalog.record; observed pg_catalog.record;
    history pg_catalog.record; delivery pg_catalog.record; old_delivery pg_catalog.record; new_delivery pg_catalog.record;
    parent_before pg_catalog.record; first_work pg_catalog.record; k pg_catalog.int4; n pg_catalog.int8;
    relation_name pg_catalog.text; contents pg_catalog.jsonb;
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb; after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
BEGIN
    SELECT r.* INTO STRICT receipt FROM modkit_events.e01(sub,''::pg_catalog.bytea,'s12-group'::pg_catalog.bytea,1) r;
    IF receipt.ok IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'S12 parent setup Unit differs'; END IF;
    SELECT r.* INTO STRICT parent_before FROM modkit_events.e18(sub) r;
    IF parent_before.subscription_id IS DISTINCT FROM sub OR parent_before.manifest IS DISTINCT FROM ''::pg_catalog.bytea
       OR parent_before.consumer_group IS DISTINCT FROM 's12-group'::pg_catalog.bytea
       OR parent_before.capacity IS DISTINCT FROM 1 OR parent_before.nonterminal_count IS DISTINCT FROM 0
       OR modkit_events._instant_bytes(parent_before.created_at) IS NULL THEN
        RAISE EXCEPTION 'S12 full parent setup evidence differs'; END IF;
    binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
        'absent'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        'retain'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,obj]::pg_catalog.bytea[]);
    replay:=pg_catalog.convert_to('{"event_id":"'||pg_catalog.convert_from(event_value,'UTF8')||
        '","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
    semantic:=modkit_events._event_replay_frame(replay);
    intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
        'inbox'::pg_catalog.bytea,modkit_events._optional_bytes(sub),'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_bytes,modkit_events._optional_bytes(key_value),semantic,binding,
        'disabled'::pg_catalog.bytea,pg_catalog.convert_to(max_value::pg_catalog.text,'UTF8'),
        '0'::pg_catalog.bytea,modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);
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
    SELECT r.* INTO STRICT receipt FROM modkit_events.e03(work_value,'inbox'::pg_catalog.text,sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        scope_bytes,key_value,1,'1'::pg_catalog.bytea,'a'::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
        intent,semantic,replay,binding,'disabled'::pg_catalog.text,max_value,NULL::pg_catalog.timestamptz,t,
        event_value,1,semantic,replay,TRUE,broker,transport) r;
    IF receipt.work_id IS DISTINCT FROM original_id OR receipt.inserted IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'S12 first admission receipt differs'; END IF;
    SELECT r.* INTO STRICT observed FROM modkit_events.e16(sub,event_value) r;
    IF observed.work_id IS DISTINCT FROM original_id OR observed.kind IS DISTINCT FROM 'inbox'
       OR observed.intent_evidence IS DISTINCT FROM intent OR observed.scope_evidence IS DISTINCT FROM scope_bytes
       OR observed.semantic_input IS DISTINCT FROM semantic OR observed.replay_input IS DISTINCT FROM replay
       OR observed.protected_binding IS DISTINCT FROM binding OR observed.idempotency_key IS DISTINCT FROM key_value
       OR observed.state IS DISTINCT FROM 'queued' OR observed.runnable_version IS DISTINCT FROM 1
       OR observed.ownership_revision IS DISTINCT FROM 0 OR observed.cycle IS DISTINCT FROM 1
       OR observed.attempt_count IS DISTINCT FROM 0 OR observed.dispatch_id IS NOT NULL
       OR observed.original_event_id IS DISTINCT FROM event_value OR observed.inbox_subscription_id IS DISTINCT FROM sub
       OR observed.envelope_evidence IS DISTINCT FROM semantic OR observed.original_replay_input IS DISTINCT FROM replay THEN
        RAISE EXCEPTION 'S12 immutable first admission evidence differs'; END IF;
    first_work:=observed;
    SELECT r.* INTO STRICT observed FROM modkit_events.e18(sub) r;
    IF observed.subscription_id IS DISTINCT FROM parent_before.subscription_id
       OR observed.manifest IS DISTINCT FROM parent_before.manifest
       OR observed.consumer_group IS DISTINCT FROM parent_before.consumer_group
       OR observed.capacity IS DISTINCT FROM parent_before.capacity
       OR observed.created_at IS DISTINCT FROM parent_before.created_at
       OR parent_before.nonterminal_count IS DISTINCT FROM 0 OR observed.nonterminal_count IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'S12 first admission changed parent beyond count0-to1'; END IF;
    SELECT h.* INTO STRICT history FROM modkit_events.work_history h WHERE h.work_id=original_id;
    IF history.cycle IS DISTINCT FROM 1 OR history.attempt IS DISTINCT FROM 0
       OR history.transition IS DISTINCT FROM 'intake_runnable' OR history.reason IS DISTINCT FROM 'intake_runnable'
       OR history.token IS NOT NULL OR history.ownership_revision IS DISTINCT FROM 0 OR history.evidence IS DISTINCT FROM ''::pg_catalog.bytea
       OR history.history_id<=0 OR modkit_events._instant_bytes(history.recorded_at) IS NULL
       OR history.recorded_at IS DISTINCT FROM first_work.updated_at THEN
        RAISE EXCEPTION 'S12 new work history differs'; END IF;
    SELECT d.* INTO STRICT delivery FROM modkit_events.delivery_history d WHERE d.work_id=original_id;
    IF delivery.broker_reference IS DISTINCT FROM broker OR delivery.transport_observation IS DISTINCT FROM transport
       OR delivery.history_id<=0 OR modkit_events._instant_bytes(delivery.recorded_at) IS NULL
       OR delivery.recorded_at IS DISTINCT FROM first_work.updated_at THEN
        RAISE EXCEPTION 'S12 new delivery evidence/time coupling differs'; END IF;
    old_delivery:=delivery;
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

    -- Lawful new effects only. All15relations, including sequence scalars, retained.
    IF (after_state-ARRAY['subscriptions','work','inbox','work_history','delivery_history',
        'work_history_history_id_seq','delivery_history_history_id_seq']::pg_catalog.text[]) IS DISTINCT FROM
       (before_state-ARRAY['subscriptions','work','inbox','work_history','delivery_history',
        'work_history_history_id_seq','delivery_history_history_id_seq']::pg_catalog.text[]) THEN
        RAISE EXCEPTION 'S12 first admission changed unrelated footprint'; END IF;
    IF (SELECT pg_catalog.count(*) FROM modkit_events.work) IS DISTINCT FROM 1
       OR (SELECT pg_catalog.count(*) FROM modkit_events.inbox) IS DISTINCT FROM 1
       OR (SELECT pg_catalog.count(*) FROM modkit_events.work_history) IS DISTINCT FROM 1
       OR (SELECT pg_catalog.count(*) FROM modkit_events.delivery_history) IS DISTINCT FROM 1
       OR (SELECT pg_catalog.count(*) FROM modkit_events.subscriptions) IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'S12 first admission added unexpected rows'; END IF;
    before_state:=after_state; after_state:='{}'::pg_catalog.jsonb;
    -- Different proposed UUID with matching scoped/event intent returns originalID.
    work_value:='9e030000-0000-0000-0000-000000000020';
    SELECT r.* INTO STRICT receipt FROM modkit_events.e03(work_value,'inbox'::pg_catalog.text,sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        scope_bytes,key_value,1,'1'::pg_catalog.bytea,'a'::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
        intent,semantic,replay,binding,'disabled'::pg_catalog.text,max_value,NULL::pg_catalog.timestamptz,t,
        event_value,1,semantic,replay,TRUE,broker,transport) r;
    IF receipt.work_id IS DISTINCT FROM original_id OR receipt.inserted IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'S12 duplicate admission receipt differs'; END IF;
    -- Retain the complete original row; count/broker equality alone is insufficient.
    SELECT d.* INTO STRICT delivery FROM modkit_events.delivery_history d WHERE d.history_id=old_delivery.history_id;
    IF pg_catalog.to_jsonb(delivery) IS DISTINCT FROM pg_catalog.to_jsonb(old_delivery) THEN
        RAISE EXCEPTION 'S12 duplicate changed original complete delivery'; END IF;
    SELECT d.* INTO STRICT new_delivery FROM modkit_events.delivery_history d
        WHERE d.work_id=original_id AND d.history_id<>old_delivery.history_id;
    IF new_delivery.history_id IS NULL OR new_delivery.history_id<=0
       OR new_delivery.history_id IS NOT DISTINCT FROM old_delivery.history_id
       OR new_delivery.work_id IS DISTINCT FROM original_id
       OR new_delivery.broker_reference IS DISTINCT FROM broker OR new_delivery.transport_observation IS DISTINCT FROM transport
       OR modkit_events._instant_bytes(new_delivery.recorded_at) IS NULL THEN
        RAISE EXCEPTION 'S12 duplicate new delivery identity/evidence/time differs'; END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.delivery_history d WHERE d.work_id=original_id;
    IF n IS DISTINCT FROM 2 OR EXISTS(SELECT FROM modkit_events.delivery_history d WHERE d.work_id=original_id
        AND (d.broker_reference IS DISTINCT FROM broker OR d.transport_observation IS DISTINCT FROM transport)) THEN
        RAISE EXCEPTION 'S12 duplicate delivery-per-call evidence differs'; END IF;
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

    IF (after_state-ARRAY['delivery_history','delivery_history_history_id_seq']::pg_catalog.text[]) IS DISTINCT FROM
       (before_state-ARRAY['delivery_history','delivery_history_history_id_seq']::pg_catalog.text[]) THEN
        RAISE EXCEPTION 'S12 duplicate rewrote work/count/intake or unrelated footprint'; END IF;
    before_state:=after_state; after_state:='{}'::pg_catalog.jsonb;
    FOR k IN 1..2 LOOP
        max_value:=CASE WHEN k=1 THEN 3 ELSE 2 END;
        key_value:=CASE WHEN k=1 THEN 'key-a'::pg_catalog.bytea ELSE 'key-new'::pg_catalog.bytea END;
        event_value:=CASE WHEN k=1 THEN 's12-event'::pg_catalog.bytea ELSE 's12-new-event'::pg_catalog.bytea END;
    replay:=pg_catalog.convert_to('{"event_id":"'||pg_catalog.convert_from(event_value,'UTF8')||
        '","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
    semantic:=modkit_events._event_replay_frame(replay);
    intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
        'inbox'::pg_catalog.bytea,modkit_events._optional_bytes(sub),'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_bytes,modkit_events._optional_bytes(key_value),semantic,binding,
        'disabled'::pg_catalog.bytea,pg_catalog.convert_to(max_value::pg_catalog.text,'UTF8'),
        '0'::pg_catalog.bytea,modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);

        BEGIN
            PERFORM * FROM modkit_events.e03(work_value,'inbox'::pg_catalog.text,sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        scope_bytes,key_value,1,'1'::pg_catalog.bytea,'a'::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
        intent,semantic,replay,binding,'disabled'::pg_catalog.text,max_value,NULL::pg_catalog.timestamptz,t,
        event_value,1,semantic,replay,TRUE,broker,transport);
            RAISE EXCEPTION 'S12 conflict/capacity call returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ002' THEN
            IF k<>1 THEN RAISE; END IF;
        WHEN SQLSTATE 'PZ007' THEN
            IF k<>2 THEN RAISE; END IF;
        END;
    END LOOP;
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
        RAISE EXCEPTION 'S12 package rejection changed full footprint'; END IF;
END
$test$;
