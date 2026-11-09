-- Prospective E16/E34 owner-structural controls; AB-SQL v2.
-- NOT_RUN / not parsed. Requires a separately reviewed source with both bodies.
-- Root owns READ COMMITTED trusted-owner setup and full final ROLLBACK.
-- No hash override, disabled constraint, lawful producer or orphan fabrication.
DO $test$
DECLARE
    ids pg_catalog.uuid[]:=ARRAY[
        '9e340000-0000-0000-0000-000000000010','9e340000-0000-0000-0000-000000000020',
        '9e340000-0000-0000-0000-000000000030','9e340000-0000-0000-0000-000000000040',
        '9e340000-0000-0000-0000-000000000050','9e340000-0000-0000-0000-000000000060']::pg_catalog.uuid[];
    absent_id pg_catalog.uuid:='9e340000-0000-0000-0000-000000000000';
    sub pg_catalog.bytea:='s10-sub'::pg_catalog.bytea;
    scope_bytes pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    obj pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    binding pg_catalog.bytea; intent pg_catalog.bytea; semantic pg_catalog.bytea; replay pg_catalog.bytea;
    event_ids pg_catalog.bytea[]:=ARRAY['s10-direct','s10-key','s10-event','s10-bad','s10-missing','s10-job']::pg_catalog.bytea[];
    keys pg_catalog.bytea[]:=ARRAY['key-direct','key-key','key-event','key-bad','key-missing','key-job']::pg_catalog.bytea[];
    intents pg_catalog.bytea[]; semantics pg_catalog.bytea[]; replays pg_catalog.bytea[];
    kind_value pg_catalog.text; row_sub pg_catalog.bytea; ns pg_catalog.bytea;
    k pg_catalog.int4; n pg_catalog.int8; observed pg_catalog.record; returned_ids pg_catalog.uuid[];
    bad_bytes pg_catalog.bytea; bad_input pg_catalog.record;
    relation_name pg_catalog.text; contents pg_catalog.jsonb;
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
    after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
BEGIN
    INSERT INTO modkit_events.subscriptions VALUES(sub,''::pg_catalog.bytea,'s10-group'::pg_catalog.bytea,32,5,t);
    binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
        'absent'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        'retain'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,obj]::pg_catalog.bytea[]);
    FOR k IN 1..6 LOOP
        kind_value:=CASE WHEN k<=5 THEN 'inbox' ELSE 'job' END;
        row_sub:=CASE WHEN k<=5 THEN sub END;
        ns:=CASE WHEN k<=5 THEN 'events'::pg_catalog.bytea ELSE 'jobs'::pg_catalog.bytea END;
        IF k<=5 THEN
            replay:=pg_catalog.convert_to('{"event_id":"'||pg_catalog.convert_from(event_ids[k],'UTF8')||
                '","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
            semantic:=modkit_events._event_replay_frame(replay);
        ELSE
            replay:='{}'::pg_catalog.bytea; semantic:=obj;
        END IF;
        intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
            pg_catalog.convert_to(kind_value,'UTF8'),modkit_events._optional_bytes(row_sub),ns,'cmd'::pg_catalog.bytea,
            '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_bytes,modkit_events._optional_bytes(keys[k]),semantic,binding,
            'disabled'::pg_catalog.bytea,'2'::pg_catalog.bytea,'0'::pg_catalog.bytea,modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);
        intents[k]:=intent; semantics[k]:=semantic; replays[k]:=replay;
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
            schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
            idempotency_key,intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
            original_available_at,state,cancellation_requested,ownership_revision,available_at,cycle,attempt_count,created_at,updated_at)
        VALUES(ids[k],kind_value,row_sub,ns,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,1,scope_bytes,'a'::pg_catalog.bytea,
            keys[k],intent,semantic,replay,binding,'disabled',2,t,'queued',FALSE,0,t,1,0,t,t);
        IF k<=4 THEN
            -- Every installed inbox half passes the intact composition trigger.
            INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                VALUES(ids[k],sub,event_ids[k],semantic,replay);
        ELSIF k>=6 THEN
            INSERT INTO modkit_events.job_payloads VALUES(ids[k],'a'::pg_catalog.bytea,NULL,NULL,binding,semantic,
                'absent',NULL,NULL,NULL,NULL,NULL,''::pg_catalog.bytea,'retain',obj);
        END IF;
    END LOOP;
    -- k5 is a reachable work-only gap, with no event-index entry.
    -- k4 was installed coherently. Only mutable updated_at now leaves E15's
    -- supported time domain; intact work UPDATE checks/trigger allow this.
    UPDATE modkit_events.work SET updated_at='infinity'::pg_catalog.timestamptz WHERE work_id=ids[4];
    IF NOT FOUND THEN RAISE EXCEPTION 'S10 timestamp setup missed work40'; END IF;
    -- Missing-work inbox insertion fails at the BEFORE INSERT composition
    -- trigger, before FK checking. This SETUP guard is not a reader oracle.
    BEGIN
        INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
            VALUES(absent_id,sub,'s10-impossible-orphan'::pg_catalog.bytea,semantics[1],replays[1]);
        RAISE EXCEPTION 'S10 missing-work subtype setup unexpectedly returned normally';
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
    END;
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

    -- E16 genuine indexed absence, then strict singleton and literal evidence.
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e16(sub,'s10-absent'::pg_catalog.bytea);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S10 E16 absence cardinality differs'; END IF;
    SELECT r.* INTO STRICT observed FROM modkit_events.e16(sub,event_ids[1]) r;
    IF observed.work_id IS DISTINCT FROM ids[1] OR observed.kind IS DISTINCT FROM 'inbox'
       OR observed.subscription_id IS DISTINCT FROM sub OR observed.namespace IS DISTINCT FROM 'events'::pg_catalog.bytea
       OR observed.command_type IS DISTINCT FROM 'cmd'::pg_catalog.bytea OR observed.idempotency_key IS DISTINCT FROM keys[1]
       OR observed.scope_evidence IS DISTINCT FROM scope_bytes OR observed.scope_application IS DISTINCT FROM 'a'::pg_catalog.bytea
       OR observed.intent_evidence IS DISTINCT FROM intents[1] OR observed.semantic_input IS DISTINCT FROM semantics[1]
       OR observed.replay_input IS DISTINCT FROM replays[1] OR observed.protected_binding IS DISTINCT FROM binding
       OR observed.state IS DISTINCT FROM 'queued' OR observed.attempt_count IS DISTINCT FROM 0
       OR observed.resolution_present IS DISTINCT FROM FALSE
       OR observed.inbox_subscription_id IS DISTINCT FROM sub OR observed.original_event_id IS DISTINCT FROM event_ids[1]
       OR observed.envelope_evidence IS DISTINCT FROM semantics[1] OR observed.original_replay_input IS DISTINCT FROM replays[1] THEN
        RAISE EXCEPTION 'S10 E16 original full evidence differs';
    END IF;
    -- Different subscription remains absent. A work-only gap is not event-index discoverable.
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e16('s10-other-sub'::pg_catalog.bytea,event_ids[1]);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S10 E16 subscription partition differs'; END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e16(sub,event_ids[5]);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S10 E16 indexed discovery limit differs'; END IF;
    FOREACH k IN ARRAY ARRAY[4]::pg_catalog.int4[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e16(sub,event_ids[k]);
            RAISE EXCEPTION 'S10 E16 unsupported stored timestamp returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
    END LOOP;
    FOREACH bad_bytes IN ARRAY ARRAY[NULL::pg_catalog.bytea,''::pg_catalog.bytea,' '::pg_catalog.bytea,
        pg_catalog.decode('ff','hex'),pg_catalog.convert_to(pg_catalog.repeat('a',257),'UTF8')]::pg_catalog.bytea[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e16(bad_bytes,'s10-absent'::pg_catalog.bytea);
            RAISE EXCEPTION 'S10 E16 malformed subscription returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
        BEGIN
            PERFORM * FROM modkit_events.e16(sub,bad_bytes);
            RAISE EXCEPTION 'S10 E16 malformed event returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
    END LOOP;

    -- E34 zero rows, event-only singleton, key-only singleton, direct/key/event overlap.
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e34(absent_id,'inbox',sub,'events'::pg_catalog.bytea,
        'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S10 E34 absence cardinality differs'; END IF;
    FOR k IN 1..3 LOOP
        SELECT r.* INTO STRICT observed FROM modkit_events.e34(
            CASE WHEN k=3 THEN ids[1] ELSE absent_id END,'inbox',sub,'events'::pg_catalog.bytea,
            'cmd'::pg_catalog.bytea,scope_bytes,CASE WHEN k>=2 THEN keys[1] END,
            CASE WHEN k=2 THEN 's10-absent'::pg_catalog.bytea ELSE event_ids[1] END) r;
        IF observed.work_id IS DISTINCT FROM ids[1] OR observed.intent_evidence IS DISTINCT FROM intents[1]
           OR observed.semantic_input IS DISTINCT FROM semantics[1] OR observed.replay_input IS DISTINCT FROM replays[1]
           OR observed.protected_binding IS DISTINCT FROM binding OR observed.scope_evidence IS DISTINCT FROM scope_bytes
           OR observed.idempotency_key IS DISTINCT FROM keys[1] OR observed.state IS DISTINCT FROM 'queued'
           OR observed.resolution_present IS DISTINCT FROM FALSE OR observed.inbox_half_present IS DISTINCT FROM TRUE
           OR observed.inbox_subscription_id IS DISTINCT FROM sub OR observed.original_event_id IS DISTINCT FROM event_ids[1]
           OR observed.envelope_evidence IS DISTINCT FROM semantics[1] OR observed.original_replay_input IS DISTINCT FROM replays[1] THEN
            RAISE EXCEPTION 'S10 E34 singleton/dedup evidence differs';
        END IF;
    END LOOP;
    -- Three independent winners; oracle orders by returned ordinality, not ID.
    SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
      FROM modkit_events.e34(ids[1],'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
          scope_bytes,keys[2],event_ids[3]) WITH ORDINALITY r;
    IF returned_ids IS DISTINCT FROM ARRAY[ids[1],ids[2],ids[3]]::pg_catalog.uuid[] THEN
        RAISE EXCEPTION 'S10 E34 three-way cardinality/order differs';
    END IF;
    FOR observed IN SELECT r.* FROM modkit_events.e34(ids[1],'inbox',sub,'events'::pg_catalog.bytea,
        'cmd'::pg_catalog.bytea,scope_bytes,keys[2],event_ids[3]) WITH ORDINALITY r LOOP
        k:=observed.ordinality::pg_catalog.int4;
        IF k<1 OR k>3 OR observed.work_id IS DISTINCT FROM ids[k]
           OR observed.kind IS DISTINCT FROM 'inbox' OR observed.subscription_id IS DISTINCT FROM sub
           OR observed.intent_evidence IS DISTINCT FROM intents[k] OR observed.semantic_input IS DISTINCT FROM semantics[k]
           OR observed.replay_input IS DISTINCT FROM replays[k] OR observed.protected_binding IS DISTINCT FROM binding
           OR observed.idempotency_key IS DISTINCT FROM keys[k] OR observed.scope_evidence IS DISTINCT FROM scope_bytes
           OR observed.state IS DISTINCT FROM 'queued' OR observed.attempt_count IS DISTINCT FROM 0
           OR observed.resolution_present IS DISTINCT FROM FALSE OR observed.inbox_half_present IS DISTINCT FROM TRUE
           OR observed.inbox_subscription_id IS DISTINCT FROM sub OR observed.original_event_id IS DISTINCT FROM event_ids[k]
           OR observed.envelope_evidence IS DISTINCT FROM semantics[k] OR observed.original_replay_input IS DISTINCT FROM replays[k] THEN
            RAISE EXCEPTION 'S10 E34 split original evidence differs';
        END IF;
    END LOOP;
    -- Direct/key overlap and event/key overlap each preserve exactly two winners.
    SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
      FROM modkit_events.e34(ids[1],'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
          scope_bytes,keys[1],event_ids[3]) WITH ORDINALITY r;
    IF returned_ids IS DISTINCT FROM ARRAY[ids[1],ids[3]]::pg_catalog.uuid[] THEN
        RAISE EXCEPTION 'S10 E34 direct-key overlap cardinality differs'; END IF;
    SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
      FROM modkit_events.e34(ids[1],'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
          scope_bytes,keys[2],event_ids[2]) WITH ORDINALITY r;
    IF returned_ids IS DISTINCT FROM ARRAY[ids[1],ids[2]]::pg_catalog.uuid[] THEN
        RAISE EXCEPTION 'S10 E34 event-key overlap cardinality differs'; END IF;
    -- A coherent job at the direct ID remains actual evidence: false plus4NULL.
    SELECT r.* INTO STRICT observed FROM modkit_events.e34(ids[6],'inbox',sub,'events'::pg_catalog.bytea,
        'other'::pg_catalog.bytea,pg_catalog.decode('4d4b5343010001620000','hex'),NULL,'s10-absent'::pg_catalog.bytea) r;
    IF observed.work_id IS DISTINCT FROM ids[6] OR observed.kind IS DISTINCT FROM 'job'
       OR observed.subscription_id IS NOT NULL OR observed.namespace IS DISTINCT FROM 'jobs'::pg_catalog.bytea
       OR observed.command_type IS DISTINCT FROM 'cmd'::pg_catalog.bytea OR observed.idempotency_key IS DISTINCT FROM keys[6]
       OR observed.intent_evidence IS DISTINCT FROM intents[6] OR observed.semantic_input IS DISTINCT FROM obj
       OR observed.replay_input IS DISTINCT FROM replays[6] OR observed.protected_binding IS DISTINCT FROM binding
       OR observed.scope_evidence IS DISTINCT FROM scope_bytes OR observed.state IS DISTINCT FROM 'queued'
       OR observed.resolution_present IS DISTINCT FROM FALSE OR observed.inbox_half_present IS DISTINCT FROM FALSE
       OR observed.inbox_subscription_id IS NOT NULL OR observed.original_event_id IS NOT NULL
       OR observed.envelope_evidence IS NOT NULL OR observed.original_replay_input IS NOT NULL THEN
        RAISE EXCEPTION 'S10 E34 wrong-kind actual evidence/false4NULL differs';
    END IF;
    -- Full result aggregation prevents an accepted usable prefix. Both malformed
    -- event-only and malformed key-only later candidates invalidate the family.
    FOR k IN 1..2 LOOP
        BEGIN
            SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
              FROM modkit_events.e34(ids[1],'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
                  scope_bytes,CASE WHEN k=1 THEN keys[2] ELSE keys[4] END,
                  CASE WHEN k=1 THEN event_ids[4] ELSE event_ids[3] END) WITH ORDINALITY r;
            RAISE EXCEPTION 'S10 E34 later malformed candidate yielded usable result';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
    END LOOP;
    FOREACH k IN ARRAY ARRAY[5]::pg_catalog.int4[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e34(ids[k],'inbox',sub,'events'::pg_catalog.bytea,
                'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea);
            RAISE EXCEPTION 'S10 E34 missing direct inbox half returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
    END LOOP;
    -- E34 validates all required input before any candidate relation access.
    FOR bad_input IN SELECT * FROM (VALUES
        (NULL::pg_catalog.uuid,'inbox'::pg_catalog.text,sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL::pg_catalog.bytea,'s10-absent'::pg_catalog.bytea),
        (absent_id,'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'INBOX',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',NULL,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,NULL,'cmd'::pg_catalog.bytea,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,NULL,scope_bytes,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,NULL,NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes||pg_catalog.decode('00','hex'),NULL,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,''::pg_catalog.bytea,'s10-absent'::pg_catalog.bytea),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL,NULL),
        (absent_id,'inbox',sub,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL,''::pg_catalog.bytea)
    ) x(wid,kind,sid,ns,cmd,scope,key_value,event_value) LOOP
        BEGIN
            PERFORM * FROM modkit_events.e34(bad_input.wid,bad_input.kind,bad_input.sid,bad_input.ns,
                bad_input.cmd,bad_input.scope,bad_input.key_value,bad_input.event_value);
            RAISE EXCEPTION 'S10 E34 malformed arguments returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
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
        RAISE EXCEPTION 'S10 E16/E34 read families changed fixture footprint';
    END IF;
END
$test$;
