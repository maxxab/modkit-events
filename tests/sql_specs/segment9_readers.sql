-- AB-READERS-1 prospective E18/E17 controls, authored before bodies.
-- NOT_RUN/not parsed. Root owns reviewed isolated setup/execution. Explicit
-- READ COMMITTED caller transaction, trusted schema owner, final full rollback.
-- No E15 fixture replay or lawful admission/dispatch provenance is claimed.
-- No actual SHA256 collision, override, constraint bypass or public helper.

DO $test$
DECLARE
    observed pg_catalog.record; n pg_catalog.int8;
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
    after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
    relation_name pg_catalog.text; contents pg_catalog.jsonb;
BEGIN
    INSERT INTO modkit_events.subscriptions VALUES
        ('s9-valid'::pg_catalog.bytea,''::pg_catalog.bytea,'group'::pg_catalog.bytea,2,0,t),
        ('s9-invalid-time'::pg_catalog.bytea,'opaque'::pg_catalog.bytea,'group2'::pg_catalog.bytea,2,0,'infinity');
    -- Snapshot all fixture-owned tables and identity sequences before reads.
    -- Dynamic identifiers come only from this fixed literal list, not input.
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
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e18('s9-absent'::pg_catalog.bytea);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S9 E18 absence cardinality differs'; END IF;
    SELECT r.* INTO STRICT observed FROM modkit_events.e18('s9-valid'::pg_catalog.bytea) r;
    IF observed.subscription_id IS DISTINCT FROM 's9-valid'::pg_catalog.bytea
       OR observed.manifest IS DISTINCT FROM ''::pg_catalog.bytea
       OR observed.consumer_group IS DISTINCT FROM 'group'::pg_catalog.bytea
       OR observed.capacity IS DISTINCT FROM 2 OR observed.nonterminal_count IS DISTINCT FROM 0
       OR observed.created_at IS DISTINCT FROM t THEN
        RAISE EXCEPTION 'S9 E18 literal six-field empty-manifest observation differs';
    END IF;
    BEGIN
        PERFORM * FROM modkit_events.e18(NULL::pg_catalog.bytea);
        RAISE EXCEPTION 'S9 E18 NULL returned normally';
    EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
    END;
    BEGIN
        PERFORM * FROM modkit_events.e18('s9-invalid-time'::pg_catalog.bytea);
        RAISE EXCEPTION 'S9 E18 unsupported stored timestamp returned normally';
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
        after_state:=after_state||pg_catalog.jsonb_build_object(relation_name,contents);
    END LOOP;
    IF after_state IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'S9 E18 read changed fixture footprint'; END IF;
END
$test$;

DO $test$
DECLARE
    ids pg_catalog.uuid[]:=ARRAY['9e170000-0000-0000-0000-000000000010','9e170000-0000-0000-0000-000000000020',
        '9e170000-0000-0000-0000-000000000030','9e170000-0000-0000-0000-000000000040']::pg_catalog.uuid[];
    absent_id pg_catalog.uuid:='9e170000-0000-0000-0000-000000000000';
    obj pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    scope_bytes pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    binding pg_catalog.bytea; intent pg_catalog.bytea; replay pg_catalog.bytea; semantic pg_catalog.bytea;
    key_value pg_catalog.bytea; sub pg_catalog.bytea; kind_value pg_catalog.text; ns pg_catalog.bytea;
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    k pg_catalog.int4; n pg_catalog.int8; observed pg_catalog.record; returned_ids pg_catalog.uuid[];
    intents pg_catalog.bytea[]; replays pg_catalog.bytea[]; semantics pg_catalog.bytea[];
    invalid_scope pg_catalog.bytea; valid_scope pg_catalog.bytea; input_case pg_catalog.record;
    app pg_catalog.bytea; tenant pg_catalog.bytea; owner_value pg_catalog.bytea;
    relation_name pg_catalog.text; contents pg_catalog.jsonb;
    before_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb; after_state pg_catalog.jsonb:='{}'::pg_catalog.jsonb;
BEGIN
    binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
        'absent'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        'retain'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,obj]::pg_catalog.bytea[]);
    FOR k IN 1..4 LOOP
        kind_value:=CASE WHEN k=3 THEN 'inbox' ELSE 'job' END;
        sub:=CASE WHEN k=3 THEN 's9-valid'::pg_catalog.bytea END;
        ns:=CASE WHEN k=3 THEN 'events'::pg_catalog.bytea ELSE 'jobs'::pg_catalog.bytea END;
        key_value:=CASE k WHEN 1 THEN 'key-a'::pg_catalog.bytea WHEN 2 THEN 'key-b'::pg_catalog.bytea
            WHEN 4 THEN 'key-bad'::pg_catalog.bytea END;
        IF k=3 THEN
            replay:=pg_catalog.convert_to('{"event_id":"s9-event","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
            semantic:=modkit_events._event_replay_frame(replay);
        ELSE replay:='{}'::pg_catalog.bytea; semantic:=obj;
        END IF;
        intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
            pg_catalog.convert_to(kind_value,'UTF8'),modkit_events._optional_bytes(sub),ns,'cmd'::pg_catalog.bytea,
            '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_bytes,modkit_events._optional_bytes(key_value),semantic,binding,
            'disabled'::pg_catalog.bytea,'2'::pg_catalog.bytea,'0'::pg_catalog.bytea,modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);
        intents[k]:=intent; replays[k]:=replay; semantics[k]:=semantic;
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
            schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
            idempotency_key,intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
            original_available_at,state,cancellation_requested,ownership_revision,available_at,cycle,attempt_count,created_at,updated_at)
        VALUES(ids[k],kind_value,sub,ns,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,1,scope_bytes,'a'::pg_catalog.bytea,
            key_value,intent,semantic,replay,binding,'disabled',2,t,'queued',FALSE,0,t,1,0,t,t);
        IF k=3 THEN
            INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                VALUES(ids[k],sub,'s9-event'::pg_catalog.bytea,semantic,replay);
        ELSIF k<>4 THEN
            INSERT INTO modkit_events.job_payloads VALUES(ids[k],'a'::pg_catalog.bytea,NULL,NULL,binding,semantic,
                'absent',NULL,NULL,NULL,NULL,NULL,''::pg_catalog.bytea,'retain',obj);
        END IF;
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
        before_state:=before_state||pg_catalog.jsonb_build_object(relation_name,contents);
    END LOOP;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e17(absent_id,'job',NULL,'jobs'::pg_catalog.bytea,
        'cmd'::pg_catalog.bytea,scope_bytes,NULL);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S9 E17 absence/NULL-key cardinality differs'; END IF;
    -- Direct-only and coincident direct/key each yield exactly one full record.
    FOR k IN 0..1 LOOP
        SELECT r.* INTO STRICT observed FROM modkit_events.e17(ids[1],'job',NULL,'jobs'::pg_catalog.bytea,
            'cmd'::pg_catalog.bytea,scope_bytes,CASE WHEN k=1 THEN 'key-a'::pg_catalog.bytea END) r;
        IF observed.work_id IS DISTINCT FROM ids[1] OR observed.kind IS DISTINCT FROM 'job'
           OR observed.idempotency_key IS DISTINCT FROM 'key-a'::pg_catalog.bytea
           OR observed.intent_evidence IS DISTINCT FROM intents[1] OR observed.replay_input IS DISTINCT FROM replays[1]
           OR observed.semantic_input IS DISTINCT FROM obj OR observed.protected_binding IS DISTINCT FROM binding
           OR observed.scope_evidence IS DISTINCT FROM scope_bytes OR observed.scope_application IS DISTINCT FROM 'a'::pg_catalog.bytea
           OR observed.scope_tenant IS NOT NULL OR observed.scope_owner IS NOT NULL
           OR observed.state IS DISTINCT FROM 'queued' OR observed.attempt_count IS DISTINCT FROM 0
           OR observed.dispatch_id IS NOT NULL OR observed.resolution_present IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'S9 E17 direct/dedup full evidence differs';
        END IF;
    END LOOP;
    SELECT r.* INTO STRICT observed FROM modkit_events.e17(absent_id,'job',NULL,'jobs'::pg_catalog.bytea,
        'cmd'::pg_catalog.bytea,scope_bytes,'key-b'::pg_catalog.bytea) r;
    IF observed.work_id IS DISTINCT FROM ids[2] OR observed.kind IS DISTINCT FROM 'job'
       OR observed.idempotency_key IS DISTINCT FROM 'key-b'::pg_catalog.bytea
       OR observed.intent_evidence IS DISTINCT FROM intents[2] OR observed.replay_input IS DISTINCT FROM replays[2]
       OR observed.semantic_input IS DISTINCT FROM obj OR observed.protected_binding IS DISTINCT FROM binding
       OR observed.scope_evidence IS DISTINCT FROM scope_bytes OR observed.state IS DISTINCT FROM 'queued'
       OR observed.resolution_present IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'S9 E17 key-only original evidence differs';
    END IF;
    -- Distinct direct/key winners retain both, sorted by UUID; no LIMIT/prefix.
    SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
      FROM modkit_events.e17(ids[2],'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,'key-a'::pg_catalog.bytea)
        WITH ORDINALITY r;
    IF returned_ids IS DISTINCT FROM ARRAY[ids[1],ids[2]]::pg_catalog.uuid[] THEN
        RAISE EXCEPTION 'S9 E17 split winner ordering/cardinality differs';
    END IF;
    -- Wrong kind/direct scope/key/namespace/command mismatch remains evidence.
    SELECT r.* INTO STRICT observed FROM modkit_events.e17(ids[3],'job',NULL,'other'::pg_catalog.bytea,
        'other'::pg_catalog.bytea,pg_catalog.decode('4d4b5343010001620000','hex'),NULL) r;
    IF observed.work_id IS DISTINCT FROM ids[3] OR observed.kind IS DISTINCT FROM 'inbox'
       OR observed.subscription_id IS DISTINCT FROM 's9-valid'::pg_catalog.bytea
       OR observed.namespace IS DISTINCT FROM 'events'::pg_catalog.bytea OR observed.command_type IS DISTINCT FROM 'cmd'::pg_catalog.bytea
       OR observed.intent_evidence IS DISTINCT FROM intents[3] OR observed.replay_input IS DISTINCT FROM replays[3]
       OR observed.semantic_input IS DISTINCT FROM semantics[3] OR observed.protected_binding IS DISTINCT FROM binding
       OR observed.scope_evidence IS DISTINCT FROM scope_bytes
       OR observed.resolution_present IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'S9 E17 wrong-kind direct full evidence hidden';
    END IF;
    BEGIN
        PERFORM * FROM modkit_events.e17(ids[4],'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,NULL);
        RAISE EXCEPTION 'S9 E17 missing half returned normally';
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
    END;
    BEGIN
        SELECT pg_catalog.array_agg(r.work_id ORDER BY r.ordinality) INTO returned_ids
          FROM modkit_events.e17(ids[1],'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,scope_bytes,'key-bad'::pg_catalog.bytea)
            WITH ORDINALITY r;
        RAISE EXCEPTION 'S9 E17 later malformed candidate yielded usable result';
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
    END;
    -- Valid frames: nullable optionals, UTF8 multibyte bound, raw NUL, maximum781.
    FOR k IN 1..4 LOOP
        app:=CASE k WHEN 1 THEN 'a'::pg_catalog.bytea WHEN 2 THEN pg_catalog.convert_to(pg_catalog.repeat('é',128),'UTF8')
            ELSE pg_catalog.decode(pg_catalog.repeat('00',256),'hex') END;
        tenant:=CASE WHEN k=4 THEN app END; owner_value:=CASE WHEN k=4 THEN app END;
        valid_scope:=pg_catalog.decode('4d4b534301','hex')||pg_catalog.int2send(pg_catalog.octet_length(app)::pg_catalog.int2)||app
            ||CASE WHEN tenant IS NULL THEN pg_catalog.decode('00','hex') ELSE pg_catalog.decode('01','hex')||pg_catalog.int2send(pg_catalog.octet_length(tenant)::pg_catalog.int2)||tenant END
            ||CASE WHEN owner_value IS NULL THEN pg_catalog.decode('00','hex') ELSE pg_catalog.decode('01','hex')||pg_catalog.int2send(pg_catalog.octet_length(owner_value)::pg_catalog.int2)||owner_value END;
        SELECT pg_catalog.count(*) INTO n FROM modkit_events.e17(absent_id,'job',NULL,'jobs'::pg_catalog.bytea,
            'cmd'::pg_catalog.bytea,valid_scope,NULL);
        IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S9 E17 valid Unicode/NULL/max scope absence differs'; END IF;
    END LOOP;
    -- Input rejection before candidate access, even with no matches.
    FOREACH invalid_scope IN ARRAY ARRAY[NULL::pg_catalog.bytea,''::pg_catalog.bytea,
        pg_catalog.decode('4d4b5343020001610000','hex'),pg_catalog.decode('4d4b5343010100610000','hex'),
        pg_catalog.decode('4d4b5343010000610000','hex'),pg_catalog.decode('4d4b5343010001ff0000','hex'),
        pg_catalog.decode('4d4b5343010001610200','hex'),pg_catalog.decode('4d4b5343010001610100','hex'),
        pg_catalog.decode('4d4b53430100016101000000','hex'),scope_bytes||pg_catalog.decode('00','hex'),
        pg_catalog.substr(scope_bytes,1,9)]::pg_catalog.bytea[] LOOP
        BEGIN
            PERFORM * FROM modkit_events.e17(absent_id,'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,invalid_scope,NULL);
            RAISE EXCEPTION 'S9 E17 malformed scope returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL;
        END;
    END LOOP;
    FOR input_case IN SELECT * FROM (VALUES
        (NULL::pg_catalog.uuid,'job'::pg_catalog.text,NULL::pg_catalog.bytea,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea),
        (absent_id,NULL,NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea),
        (absent_id,'JOB',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea),
        (absent_id,'job','unexpected'::pg_catalog.bytea,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea),
        (absent_id,'inbox',NULL,'events'::pg_catalog.bytea,'cmd'::pg_catalog.bytea),
        (absent_id,'job',NULL,NULL,'cmd'::pg_catalog.bytea),
        (absent_id,'job',NULL,'jobs'::pg_catalog.bytea,NULL),
        (absent_id,'job',NULL,''::pg_catalog.bytea,'cmd'::pg_catalog.bytea)
    ) x(wid,kind,sub,ns,cmd) LOOP
        BEGIN
            PERFORM * FROM modkit_events.e17(input_case.wid,input_case.kind,input_case.sub,input_case.ns,input_case.cmd,scope_bytes,NULL);
            RAISE EXCEPTION 'S9 E17 required argument/kind/subscription shape returned normally';
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
    IF after_state IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'S9 E17 reads/rejections changed fixture footprint'; END IF;
END
$test$;
