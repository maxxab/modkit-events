-- Prospective S7 owner-only structural assertions. NOT_RUN, not parsed/compiled.
-- Run only after separate authorization in an isolated installed schema, caller
-- READ COMMITTED, default DEFERRED guard constraint, explicit rollback harness.
-- These same-root owner records are NOT public committed dispatch provenance.
DO $test$
DECLARE
    wid pg_catalog.uuid; tok pg_catalog.uuid; did pg_catalog.uuid;
    k pg_catalog.int4; material pg_catalog.int4; got pg_catalog.text;
    kind_value pg_catalog.text; sub pg_catalog.bytea; ns pg_catalog.bytea;
    obj pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    scope_value pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    binding pg_catalog.bytea; intent pg_catalog.bytea; replay pg_catalog.bytea;
    semantic pg_catalog.bytea; event_value pg_catalog.bytea;
    sidecar pg_catalog.bytea; reference_value pg_catalog.bytea; codec pg_catalog.bytea;
    key_value pg_catalog.bytea; recovery pg_catalog.bytea; material_state pg_catalog.text;
    t0 pg_catalog.timestamptz; expiry pg_catalog.timestamptz; result_value pg_catalog.bytea;
    root_value pg_catalog.xid8; revision_value pg_catalog.int8; ok_value pg_catalog.bool;
    w0 modkit_events.work%ROWTYPE; w1 modkit_events.work%ROWTYPE; we modkit_events.work%ROWTYPE;
    a0 modkit_events.attempts%ROWTYPE; a1 modkit_events.attempts%ROWTYPE; ae modkit_events.attempts%ROWTYPE;
    g0 modkit_events.finalization_guards%ROWTYPE; g1 modkit_events.finalization_guards%ROWTYPE;
    ge modkit_events.finalization_guards%ROWTYPE;
    s0 modkit_events.subscriptions%ROWTYPE; s1 modkit_events.subscriptions%ROWTYPE;
    j0 modkit_events.job_payloads%ROWTYPE; j1 modkit_events.job_payloads%ROWTYPE;
    i0 modkit_events.inbox%ROWTYPE; i1 modkit_events.inbox%ROWTYPE;
    h modkit_events.work_history%ROWTYPE; n pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'fixture requires READ COMMITTED';
    END IF;
    root_value:=pg_catalog.pg_current_xact_id();
    t0:=pg_catalog.clock_timestamp();
    INSERT INTO modkit_events.subscriptions VALUES
      ('s7-parent'::pg_catalog.bytea,''::pg_catalog.bytea,'s7-group'::pg_catalog.bytea,100,3,t0);
    FOR k IN 1..2 LOOP
      FOR material IN 0..2 LOOP
        wid:=pg_catalog.gen_random_uuid();tok:=pg_catalog.gen_random_uuid();did:=pg_catalog.gen_random_uuid();
        kind_value:=CASE WHEN k=1 THEN 'job' ELSE 'inbox' END;
        sub:=CASE WHEN k=2 THEN 's7-parent'::pg_catalog.bytea END;
        ns:=pg_catalog.convert_to(CASE WHEN k=1 THEN 'jobs' ELSE 'events' END,'UTF8');
        event_value:=pg_catalog.convert_to(wid::pg_catalog.text,'UTF8');
        sidecar:=NULL;reference_value:=NULL;codec:=NULL;key_value:=NULL;
        recovery:=''::pg_catalog.bytea;material_state:='absent';
        IF material>0 THEN
            material_state:='present';codec:=pg_catalog.decode('6300','hex');key_value:='k'::pg_catalog.bytea;
            recovery:=obj;
            IF material=1 THEN sidecar:=pg_catalog.decode('ff00','hex');
            ELSE reference_value:=pg_catalog.decode('ff00','hex'); END IF;
        END IF;
        binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
          pg_catalog.convert_to(material_state,'UTF8'),modkit_events._optional_bytes(codec),
          modkit_events._optional_bytes(key_value),'0'::pg_catalog.bytea,'retain'::pg_catalog.bytea,
          modkit_events._optional_bytes(sidecar),modkit_events._optional_bytes(reference_value),
          CASE WHEN material>0 THEN 'binding'::pg_catalog.bytea ELSE ''::pg_catalog.bytea END,recovery,obj]::pg_catalog.bytea[]);
        IF k=1 THEN replay:='{}'::pg_catalog.bytea;semantic:=obj;
        ELSE
            replay:=pg_catalog.convert_to('{"event_id":"'||wid::pg_catalog.text||'","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
            semantic:=modkit_events._event_replay_frame(replay);
        END IF;
        intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
          pg_catalog.convert_to(kind_value,'UTF8'),modkit_events._optional_bytes(sub),ns,'cmd'::pg_catalog.bytea,
          '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_value,'0'::pg_catalog.bytea,semantic,binding,
          'application_safe'::pg_catalog.bytea,'1000'::pg_catalog.bytea,'0'::pg_catalog.bytea,
          modkit_events._instant_bytes(t0)]::pg_catalog.bytea[]);
        revision_value:=CASE WHEN material=2 THEN 9223372036854775806::pg_catalog.int8 ELSE 1::pg_catalog.int8 END;
        expiry:=pg_catalog.clock_timestamp()+'1 hour'::pg_catalog.interval;
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
          schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
          intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
          original_available_at,state,cancellation_requested,token,ownership_revision,lease_until,
          available_at,cycle,attempt_count,dispatch_id,created_at,updated_at)
        VALUES(wid,kind_value,sub,ns,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,1,scope_value,'a'::pg_catalog.bytea,
          intent,semantic,replay,binding,'application_safe',1000,t0,'running',FALSE,tok,revision_value,expiry,
          t0,1,CASE WHEN material=2 THEN 1000 ELSE 1 END,did,t0,t0) RETURNING * INTO w0;
        IF k=1 THEN
            INSERT INTO modkit_events.job_payloads VALUES(wid,'a'::pg_catalog.bytea,NULL,NULL,binding,semantic,
              material_state,sidecar,reference_value,codec,key_value,NULL,recovery,'retain',obj) RETURNING * INTO j0;
        ELSE
            INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
              VALUES(wid,sub,event_value,semantic,replay) RETURNING * INTO i0;
        END IF;
        INSERT INTO modkit_events.attempts VALUES(wid,1,w0.attempt_count,did,'effect'::pg_catalog.bytea,
          ''::pg_catalog.bytea,NULL,root_value,'dispatched',''::pg_catalog.bytea,t0) RETURNING * INTO a0;
        SELECT armed.* INTO STRICT g0 FROM modkit_events.e08(wid,tok,revision_value,1,w0.attempt_count) AS armed;
        -- Legal attempt0 grammar must reach matching-guard rejection, not PZ006.
        BEGIN
            PERFORM * FROM modkit_events.e10(g0.guard_id,wid,root_value,tok,revision_value,1,0,''::pg_catalog.bytea);
            RAISE EXCEPTION 'attempt0 returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM 'PZ008' THEN RAISE; END IF;
        END;
        -- Same owner fixture can lawfully change lifecycle fields, not immutable
        -- intent. Max revision beats cancellation and an expired lease.
        BEGIN
            UPDATE modkit_events.work SET ownership_revision=9223372036854775807,cancellation_requested=TRUE,
              lease_until=t0-'1 second'::pg_catalog.interval WHERE work_id=wid;
            -- Existing guard captures old revision, so this is stale PZ003,
            -- NOT an exhausted-revision oracle. The separate schedule creates
            -- its matching max guard first. Preserve this discriminator.
            BEGIN
                PERFORM * FROM modkit_events.e10(g0.guard_id,wid,root_value,tok,revision_value,1,w0.attempt_count,''::pg_catalog.bytea);
                RAISE EXCEPTION 'stale fence returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ003' THEN RAISE; END IF;
            END;
            RAISE EXCEPTION USING ERRCODE='Z7001',MESSAGE='rollback lifecycle setup';
        EXCEPTION WHEN SQLSTATE 'Z7001' THEN NULL;
        END;
        SELECT w.* INTO STRICT w1 FROM modkit_events.work AS w WHERE w.work_id=wid;
        SELECT a.* INTO STRICT a1 FROM modkit_events.attempts AS a WHERE a.work_id=wid AND a.cycle=1 AND a.attempt=w0.attempt_count;
        SELECT g.* INTO STRICT g1 FROM modkit_events.finalization_guards AS g WHERE g.guard_id=g0.guard_id;
        IF w1 IS DISTINCT FROM w0 OR a1 IS DISTINCT FROM a0 OR g1 IS DISTINCT FROM g0
           OR EXISTS(SELECT 1 FROM modkit_events.work_history AS x WHERE x.work_id=wid) THEN
            RAISE EXCEPTION 'negative call changed footprint';
        END IF;
        SELECT s.* INTO STRICT s0 FROM modkit_events.subscriptions AS s WHERE s.subscription_id='s7-parent'::pg_catalog.bytea;
        result_value:=CASE WHEN material=0 THEN ''::pg_catalog.bytea
                          WHEN material=2 THEN pg_catalog.decode(pg_catalog.repeat('ff',1048576),'hex')
                          ELSE pg_catalog.decode('00ff','hex') END;
        SELECT completed.ok INTO STRICT ok_value FROM modkit_events.e10(g0.guard_id,wid,root_value,tok,
          revision_value,1,w0.attempt_count,result_value) AS completed;
        IF ok_value IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'completion did not return true'; END IF;
        SELECT w.* INTO STRICT w1 FROM modkit_events.work AS w WHERE w.work_id=wid;
        SELECT a.* INTO STRICT a1 FROM modkit_events.attempts AS a WHERE a.work_id=wid AND a.cycle=1 AND a.attempt=w0.attempt_count;
        SELECT g.* INTO STRICT g1 FROM modkit_events.finalization_guards AS g WHERE g.guard_id=g0.guard_id;
        we:=w0;we.state:='succeeded';we.token:=NULL;we.lease_until:=NULL;we.ownership_revision:=revision_value+1;
        we.result:=result_value;we.success_origin:='guarded';we.completion_guard_id:=g0.guard_id;
        we.final_fence_at:=g1.final_fence_at;we.completion_result_digest:=pg_catalog.sha256(result_value);
        we.updated_at:=g1.final_fence_at;
        ae:=a0;ae.outcome:='succeeded';ae.evidence:=''::pg_catalog.bytea;
        ge:=g0;ge.satisfied:=TRUE;ge.final_fence_at:=w1.final_fence_at;ge.terminal_state:='succeeded';ge.result_digest:=pg_catalog.sha256(result_value);
        IF w1 IS DISTINCT FROM we OR a1 IS DISTINCT FROM ae OR g1 IS DISTINCT FROM ge
           OR modkit_events._instant_bytes(w1.final_fence_at) IS NULL
           OR w1.final_fence_at<t0 OR w1.final_fence_at>=expiry THEN
            RAISE EXCEPTION 'full terminal witness mismatch';
        END IF;
        SELECT pg_catalog.count(*) INTO n FROM modkit_events.work_history AS x WHERE x.work_id=wid;
        IF n<>1 THEN RAISE EXCEPTION 'not exactly one history'; END IF;
        SELECT x.* INTO STRICT h FROM modkit_events.work_history AS x WHERE x.work_id=wid;
        IF h.history_id<=0 OR ROW(h.work_id,h.cycle,h.attempt,h.transition,h.reason,h.token,
          h.ownership_revision,h.evidence,h.recorded_at) IS DISTINCT FROM
          ROW(wid,1,w0.attempt_count,'complete'::pg_catalog.text,'complete'::pg_catalog.text,NULL::pg_catalog.uuid,
              revision_value+1,''::pg_catalog.bytea,w1.final_fence_at) THEN RAISE EXCEPTION 'history witness mismatch'; END IF;
        SELECT s.* INTO STRICT s1 FROM modkit_events.subscriptions AS s WHERE s.subscription_id=s0.subscription_id;
        IF k=2 THEN s0.nonterminal_count:=s0.nonterminal_count-1; END IF;
        IF s1 IS DISTINCT FROM s0 THEN RAISE EXCEPTION 'parent footprint mismatch'; END IF;
        IF k=1 THEN
            SELECT j.* INTO STRICT j1 FROM modkit_events.job_payloads AS j WHERE j.job_work_id=wid;
            IF j1 IS DISTINCT FROM j0 OR EXISTS(SELECT 1 FROM modkit_events.inbox AS i WHERE i.work_id=wid)
              THEN RAISE EXCEPTION 'job subtype footprint mismatch'; END IF;
        ELSE
            SELECT i.* INTO STRICT i1 FROM modkit_events.inbox AS i WHERE i.work_id=wid;
            IF i1 IS DISTINCT FROM i0 OR EXISTS(SELECT 1 FROM modkit_events.job_payloads AS j WHERE j.job_work_id=wid)
              THEN RAISE EXCEPTION 'inbox subtype footprint mismatch'; END IF;
        END IF;
        BEGIN
            PERFORM * FROM modkit_events.e10(g0.guard_id,wid,root_value,tok,revision_value,1,w0.attempt_count,result_value);
            RAISE EXCEPTION 'same-root second completion returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM 'PZ008' THEN RAISE; END IF;
        END;
        SELECT w.* INTO STRICT w1 FROM modkit_events.work AS w WHERE w.work_id=wid;
        SELECT g.* INTO STRICT g1 FROM modkit_events.finalization_guards AS g WHERE g.guard_id=g0.guard_id;
        SELECT pg_catalog.count(*) INTO n FROM modkit_events.work_history AS x WHERE x.work_id=wid;
        IF w1 IS DISTINCT FROM we OR g1 IS DISTINCT FROM ge OR n<>1 THEN RAISE EXCEPTION 'repeat changed witness'; END IF;
      END LOOP;
    END LOOP;
END
$test$;
