-- AB-E15-1 prospective behavior controls. NOT_RUN; not parsed or compiled.
-- This file does not authorize a connection, installation, SQL execution,
-- role/default/constraint alteration or service start. Future executor needs
-- a separately approved isolated PG16+ schema-owner fixture, explicit caller
-- READ COMMITTED transaction and final full ROLLBACK. Owner structural records
-- are not public admission/dispatch provenance. No production helper is added.
-- RED boundary: before E15 exists the first actual call fails 42883. That is
-- the intended missing-function cause; do not swallow it or call it a PASS.
-- No source-string presence assertion substitutes for running this behavior.

DO $test$
DECLARE
    absent_id pg_catalog.uuid := '8e150000-0000-0000-0000-000000000001';
    n pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'S8 fixture requires READ COMMITTED';
    END IF;
    -- Executor must use a fresh fixture; never delete a colliding row.
    IF EXISTS (SELECT FROM modkit_events.work WHERE work_id=absent_id)
       OR EXISTS (SELECT FROM modkit_events.inbox WHERE work_id=absent_id)
       OR EXISTS (SELECT FROM modkit_events.job_payloads WHERE job_work_id=absent_id) THEN
        RAISE EXCEPTION 'S8 reserved fixture identity occupied';
    END IF;
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e15(absent_id);
    IF n IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'S8 genuine absence must return zero rows'; END IF;
    BEGIN
        PERFORM * FROM modkit_events.e15(NULL::pg_catalog.uuid);
        RAISE EXCEPTION 'S8 NULL input returned normally';
    EXCEPTION WHEN SQLSTATE 'PZ006' THEN
        NULL;
    END;
END
$test$;

-- S8-MATRIX: owner structural rows only. These literal state/evidence oracles
-- catch pointer-only attempt joins, empty-only uncertainty, root-equality,
-- guard old/successor confusion and filtered-away malformed second histories.
DO $test$
DECLARE
    k pg_catalog.int4; material pg_catalog.int4; arm pg_catalog.int4;
    wid pg_catalog.uuid; did pg_catalog.uuid; did2 pg_catalog.uuid; tok pg_catalog.uuid;
    gid pg_catalog.uuid; oid pg_catalog.uuid;
    kind_value pg_catalog.text; sub pg_catalog.bytea; ns pg_catalog.bytea;
    state_value pg_catalog.text; outcome_value pg_catalog.text; transition_value pg_catalog.text;
    result_value pg_catalog.bytea; binding pg_catalog.bytea; intent pg_catalog.bytea;
    replay pg_catalog.bytea; semantic pg_catalog.bytea;
    sidecar pg_catalog.bytea; reference_value pg_catalog.bytea; codec pg_catalog.bytea;
    key_value pg_catalog.bytea; recovery pg_catalog.bytea; material_state pg_catalog.text;
    obj pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    scope_value pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    t pg_catalog.timestamptz:='2026-01-02 03:04:05+00';
    final_t pg_catalog.timestamptz:='2026-01-02 03:04:06+00';
    observed pg_catalog.record;
BEGIN
    INSERT INTO modkit_events.subscriptions VALUES
        ('s8-parent'::pg_catalog.bytea,''::pg_catalog.bytea,'s8-group'::pg_catalog.bytea,100,0,t);
    FOR k IN 1..2 LOOP
      FOR material IN 0..2 LOOP
        wid:=pg_catalog.gen_random_uuid(); did:=pg_catalog.gen_random_uuid();
        did2:=pg_catalog.gen_random_uuid(); tok:=pg_catalog.gen_random_uuid();
        kind_value:=CASE WHEN k=1 THEN 'job' ELSE 'inbox' END;
        sub:=CASE WHEN k=2 THEN 's8-parent'::pg_catalog.bytea END;
        ns:=pg_catalog.convert_to(CASE WHEN k=1 THEN 'jobs' ELSE 'events' END,'UTF8');
        material_state:=CASE WHEN material=0 THEN 'absent' ELSE 'present' END;
        sidecar:=NULL; reference_value:=NULL; codec:=NULL; key_value:=NULL; recovery:=''::pg_catalog.bytea;
        IF material>0 THEN
            codec:='c'::pg_catalog.bytea; key_value:='k'::pg_catalog.bytea; recovery:=obj;
            IF material=1 THEN sidecar:=pg_catalog.decode('ff00','hex');
            ELSE reference_value:=pg_catalog.decode('ff00','hex'); END IF;
        END IF;
        binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
            pg_catalog.convert_to(material_state,'UTF8'),modkit_events._optional_bytes(codec),
            modkit_events._optional_bytes(key_value),'0'::pg_catalog.bytea,'retain'::pg_catalog.bytea,
            modkit_events._optional_bytes(sidecar),modkit_events._optional_bytes(reference_value),
            CASE WHEN material>0 THEN 'binding'::pg_catalog.bytea ELSE ''::pg_catalog.bytea END,
            recovery,obj]::pg_catalog.bytea[]);
        IF k=1 THEN replay:='{}'::pg_catalog.bytea; semantic:=obj;
        ELSE
            replay:=pg_catalog.convert_to('{"event_id":"'||wid::pg_catalog.text||'","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
            semantic:=modkit_events._event_replay_frame(replay);
        END IF;
        intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
            pg_catalog.convert_to(kind_value,'UTF8'),modkit_events._optional_bytes(sub),ns,'cmd'::pg_catalog.bytea,
            '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_value,'0'::pg_catalog.bytea,semantic,binding,
            'application_safe'::pg_catalog.bytea,'1000'::pg_catalog.bytea,'0'::pg_catalog.bytea,
            modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
            schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
            intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
            original_available_at,state,cancellation_requested,token,ownership_revision,lease_until,
            available_at,cycle,attempt_count,dispatch_id,created_at,updated_at)
        VALUES(wid,kind_value,sub,ns,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,1,scope_value,'a'::pg_catalog.bytea,
            intent,semantic,replay,binding,'application_safe',1000,t,'running',FALSE,tok,3,t,t,1,1,did,t,t);
        IF k=1 THEN
            INSERT INTO modkit_events.job_payloads VALUES(wid,'a'::pg_catalog.bytea,NULL,NULL,binding,semantic,
                material_state,sidecar,reference_value,codec,key_value,NULL,recovery,'retain',obj);
        ELSE
            INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                VALUES(wid,sub,pg_catalog.convert_to(wid::pg_catalog.text,'UTF8'),semantic,replay);
        END IF;
        BEGIN
            PERFORM * FROM modkit_events.e15(wid);
            RAISE EXCEPTION 'S8 missing latest running attempt returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
        INSERT INTO modkit_events.attempts VALUES(wid,1,1,did,'effect'::pg_catalog.bytea,
            'request'::pg_catalog.bytea,NULL,'333'::pg_catalog.xid8,'dispatched',''::pg_catalog.bytea,t);
        SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
        IF observed.state IS DISTINCT FROM 'running' OR observed.dispatch_id IS DISTINCT FROM did
           OR observed.lease_until IS DISTINCT FROM t OR observed.protected_binding IS DISTINCT FROM binding THEN
            RAISE EXCEPTION 'S8 expired live dispatch must remain readable';
        END IF;
        UPDATE modkit_events.work SET state='held',token=NULL,lease_until=NULL WHERE work_id=wid;
        BEGIN
            PERFORM * FROM modkit_events.e15(wid);
            RAISE EXCEPTION 'S8 held dispatched attempt returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
        -- E12 generated hold alternative, separately rolled back.
        BEGIN
            UPDATE modkit_events.attempts SET outcome='cancelled_unresolved',evidence=''::pg_catalog.bytea
                WHERE work_id=wid AND attempt=1;
            SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
            IF observed.work_id IS DISTINCT FROM wid OR observed.state IS DISTINCT FROM 'held'
               OR observed.dispatch_id IS DISTINCT FROM did OR observed.attempt_count IS DISTINCT FROM 1
               OR observed.resolution_present IS DISTINCT FROM FALSE
               OR observed.cancellation_requested IS DISTINCT FROM FALSE
               OR observed.token IS NOT NULL OR observed.lease_until IS NOT NULL THEN
                RAISE EXCEPTION 'S8 cancelled-unresolved held observation differs';
            END IF;
            RAISE EXCEPTION USING ERRCODE='ZX801',MESSAGE='S8 intentional fixture rollback';
        EXCEPTION WHEN SQLSTATE 'ZX801' THEN NULL;
        END;
        UPDATE modkit_events.attempts SET outcome='uncertain',evidence='held-evidence'::pg_catalog.bytea
            WHERE work_id=wid AND attempt=1;
        SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
        IF observed.work_id IS DISTINCT FROM wid OR observed.state IS DISTINCT FROM 'held'
           OR observed.dispatch_id IS DISTINCT FROM did OR observed.attempt_count IS DISTINCT FROM 1
           OR observed.resolution_present IS DISTINCT FROM FALSE
           OR observed.cancellation_requested IS DISTINCT FROM FALSE
           OR observed.token IS NOT NULL OR observed.lease_until IS NOT NULL THEN
            RAISE EXCEPTION 'S8 uncertain held observation differs';
        END IF;
        UPDATE modkit_events.work SET cancellation_requested=TRUE WHERE work_id=wid;
        SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
        IF observed.work_id IS DISTINCT FROM wid OR observed.state IS DISTINCT FROM 'held'
           OR observed.dispatch_id IS DISTINCT FROM did OR observed.attempt_count IS DISTINCT FROM 1
           OR observed.resolution_present IS DISTINCT FROM FALSE
           OR observed.cancellation_requested IS DISTINCT FROM TRUE
           OR observed.token IS NOT NULL OR observed.lease_until IS NOT NULL THEN
            RAISE EXCEPTION 'S8 held-after-cancellation observation differs';
        END IF;
        UPDATE modkit_events.work SET state='retry_waiting',dispatch_id=NULL,cancellation_requested=FALSE WHERE work_id=wid;
        BEGIN
            PERFORM * FROM modkit_events.e15(wid);
            RAISE EXCEPTION 'S8 unresolved cleared-pointer attempt returned normally';
        EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
        END;
        UPDATE modkit_events.attempts SET outcome='safe_retry',evidence='retry-evidence'::pg_catalog.bytea
            WHERE work_id=wid AND attempt=1;
        SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
        IF observed.attempt_count IS DISTINCT FROM 1 OR observed.dispatch_id IS NOT NULL
           OR observed.resolution_present IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'S8 resolved positive-count pointer-clear differs';
        END IF;
        FOREACH state_value IN ARRAY ARRAY['queued','blocked_schema','failed','cancelled','expired']::pg_catalog.text[] LOOP
            UPDATE modkit_events.work SET state=state_value WHERE work_id=wid;
            SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
            IF observed.work_id IS DISTINCT FROM wid OR observed.state IS DISTINCT FROM state_value
               OR observed.dispatch_id IS NOT NULL OR observed.attempt_count IS DISTINCT FROM 1
               OR observed.resolution_present IS DISTINCT FROM FALSE
               OR observed.cancellation_requested IS DISTINCT FROM FALSE
               OR observed.token IS NOT NULL OR observed.lease_until IS NOT NULL THEN
                RAISE EXCEPTION 'S8 retained prior-attempt state observation differs';
            END IF;
        END LOOP;
        UPDATE modkit_events.work SET state='claimed',token=tok,lease_until=t WHERE work_id=wid;
        SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
        IF observed.work_id IS DISTINCT FROM wid OR observed.state IS DISTINCT FROM 'claimed'
           OR observed.dispatch_id IS NOT NULL OR observed.attempt_count IS DISTINCT FROM 1
           OR observed.resolution_present IS DISTINCT FROM FALSE
           OR observed.cancellation_requested IS DISTINCT FROM FALSE
           OR observed.token IS DISTINCT FROM tok OR observed.lease_until IS DISTINCT FROM t THEN
            RAISE EXCEPTION 'S8 claimed prior-attempt observation differs';
        END IF;
        UPDATE modkit_events.work SET state='running',attempt_count=2,dispatch_id=did2 WHERE work_id=wid;
        INSERT INTO modkit_events.attempts VALUES(wid,1,2,did2,'effect2'::pg_catalog.bytea,
            'request2'::pg_catalog.bytea,'provider'::pg_catalog.bytea,'333'::pg_catalog.xid8,'dispatched',''::pg_catalog.bytea,t);
        -- Direct E11 terminal failure/cancel and retry evidence may be nonempty.
        FOR arm IN 1..3 LOOP
          BEGIN
            state_value:=CASE arm WHEN 1 THEN 'failed' WHEN 2 THEN 'cancelled' ELSE 'retry_waiting' END;
            outcome_value:=CASE WHEN arm=2 THEN 'cancelled' ELSE 'failed' END;
            UPDATE modkit_events.attempts SET outcome=outcome_value,evidence='submitted-e11'::pg_catalog.bytea
                WHERE work_id=wid AND attempt=2;
            UPDATE modkit_events.work SET state=state_value,token=NULL,lease_until=NULL,
                dispatch_id=CASE WHEN arm=3 THEN NULL ELSE did2 END WHERE work_id=wid;
            SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
            IF observed.state IS DISTINCT FROM state_value OR observed.resolution_present IS DISTINCT FROM FALSE THEN
                RAISE EXCEPTION 'S8 direct E11 state/evidence rejected';
            END IF;
            RAISE EXCEPTION USING ERRCODE='ZX801',MESSAGE='S8 intentional fixture rollback';
          EXCEPTION WHEN SQLSTATE 'ZX801' THEN NULL;
          END;
        END LOOP;
        -- E31 terminal operation/evidence/history is structural, not an E31 call.
        FOR arm IN 1..3 LOOP
          BEGIN
            oid:=pg_catalog.gen_random_uuid();
            state_value:=CASE arm WHEN 1 THEN 'succeeded' WHEN 2 THEN 'failed' ELSE 'cancelled' END;
            outcome_value:=CASE arm WHEN 1 THEN 'confirmed_success' WHEN 2 THEN 'confirmed_rejection' ELSE 'confirmed_cancelled' END;
            transition_value:=CASE arm WHEN 1 THEN 'reconcile_success' WHEN 2 THEN 'reconcile_rejection' ELSE 'reconcile_cancelled' END;
            result_value:=CASE WHEN arm=1 THEN 'result'::pg_catalog.bytea END;
            UPDATE modkit_events.attempts SET outcome='uncertain',evidence='original-hold'::pg_catalog.bytea WHERE work_id=wid AND attempt=2;
            UPDATE modkit_events.attempts SET outcome=state_value,evidence='resolution-evidence'::pg_catalog.bytea WHERE work_id=wid AND attempt=2;
            INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,work_id,expected_revision,
                cycle,attempt,dispatch_id,requested_outcome,requested_result,result_digest,evidence,binding,resolution_root_xid,recorded_at)
            VALUES(oid,'reconcile_work',wid,3,1,2,did2,outcome_value,result_value,
                CASE WHEN arm=1 THEN pg_catalog.sha256(result_value) END,'resolution-evidence'::pg_catalog.bytea,
                'resolution-binding'::pg_catalog.bytea,'555'::pg_catalog.xid8,final_t);
            UPDATE modkit_events.work SET state=state_value,token=NULL,lease_until=NULL,ownership_revision=4,
                result=result_value,success_origin=CASE WHEN arm=1 THEN 'reconciled' END,
                resolution_operation_id=CASE WHEN arm=1 THEN oid END,terminal_resolution_operation_id=oid,
                updated_at=final_t WHERE work_id=wid;
            BEGIN
                PERFORM * FROM modkit_events.e15(wid);
                RAISE EXCEPTION 'S8 missing reconcile history returned normally';
            EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
            END;
            INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
            VALUES(wid,1,2,transition_value,transition_value,NULL,4,'resolution-evidence'::pg_catalog.bytea,final_t);
            SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
            IF observed.resolution_present IS DISTINCT FROM TRUE OR observed.resolution_record_operation_id IS DISTINCT FROM oid
               OR observed.resolution_record_reason IS NOT NULL OR observed.resolution_record_outcome IS DISTINCT FROM outcome_value
               OR observed.resolution_record_evidence IS DISTINCT FROM 'resolution-evidence'::pg_catalog.bytea
               OR observed.updated_at IS DISTINCT FROM final_t THEN
                RAISE EXCEPTION 'S8 exact resolution projection differs';
            END IF;
            UPDATE modkit_events.work SET ownership_revision=5 WHERE work_id=wid;
            BEGIN
                PERFORM * FROM modkit_events.e15(wid);
                RAISE EXCEPTION 'S8 resolution successor mismatch returned normally';
            EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
            END;
            UPDATE modkit_events.work SET ownership_revision=4 WHERE work_id=wid;
            -- Second candidate deliberately invalid as witness; must be counted
            -- BEFORE validity filtering, not dropped because revision differs.
            INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
            VALUES(wid,1,2,transition_value,transition_value,NULL,5,'resolution-evidence'::pg_catalog.bytea,final_t);
            BEGIN
                PERFORM * FROM modkit_events.e15(wid);
                RAISE EXCEPTION 'S8 malformed second reconcile history disappeared';
            EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
            END;
            RAISE EXCEPTION USING ERRCODE='ZX801',MESSAGE='S8 intentional fixture rollback';
          EXCEPTION WHEN SQLSTATE 'ZX801' THEN NULL;
          END;
        END LOOP;
        -- Satisfied owner guard with deliberately DISTINCT historical roots.
        -- This fixture checks E15, not lawful public dispatch or E10 execution.
        BEGIN
            gid:=pg_catalog.gen_random_uuid(); result_value:='guarded-result'::pg_catalog.bytea;
            INSERT INTO modkit_events.finalization_guards VALUES(gid,wid,'777'::pg_catalog.xid8,tok,3,1,2,
                TRUE,final_t,'succeeded',pg_catalog.sha256(result_value));
            UPDATE modkit_events.attempts SET outcome='succeeded',evidence=''::pg_catalog.bytea WHERE work_id=wid AND attempt=2;
            UPDATE modkit_events.work SET state='succeeded',token=NULL,lease_until=NULL,ownership_revision=4,
                result=result_value,success_origin='guarded',completion_guard_id=gid,final_fence_at=final_t,
                completion_result_digest=pg_catalog.sha256(result_value),updated_at=final_t WHERE work_id=wid;
            BEGIN
                PERFORM * FROM modkit_events.e15(wid);
                RAISE EXCEPTION 'S8 missing complete history returned normally';
            EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
            END;
            INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
            VALUES(wid,1,2,'complete','complete',NULL,4,''::pg_catalog.bytea,final_t);
            SELECT r.* INTO STRICT observed FROM modkit_events.e15(wid) AS r;
            IF observed.ownership_revision IS DISTINCT FROM 4 OR observed.completion_guard_id IS DISTINCT FROM gid
               OR observed.resolution_present IS DISTINCT FROM FALSE OR observed.final_fence_at IS DISTINCT FROM final_t THEN
                RAISE EXCEPTION 'S8 historical guarded witness rejected';
            END IF;
            INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
            VALUES(wid,1,2,'complete','complete',NULL,5,''::pg_catalog.bytea,final_t);
            BEGIN
                PERFORM * FROM modkit_events.e15(wid);
                RAISE EXCEPTION 'S8 malformed second complete history disappeared';
            EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL;
            END;
            RAISE EXCEPTION USING ERRCODE='ZX801',MESSAGE='S8 intentional fixture rollback';
        EXCEPTION WHEN SQLSTATE 'ZX801' THEN NULL;
        END;
      END LOOP;
    END LOOP;
END
$test$;

-- Independently literal scope/canonical object, existing schema frame helpers
-- only for fixture construction. E15 projection/corruption assertions below
-- compare supplied bytes; expected row is not built by E15 or its validators.
DO $test$
DECLARE
    wid pg_catalog.uuid := '8e150000-0000-0000-0000-000000000002';
    t pg_catalog.timestamptz := '2026-01-02 03:04:05+00';
    obj pg_catalog.bytea := pg_catalog.decode('6f00000000','hex');
    scope_bytes pg_catalog.bytea := pg_catalog.decode('4d4b5343010001610000','hex');
    binding pg_catalog.bytea;
    intent pg_catalog.bytea;
    got pg_catalog.record;
    n pg_catalog.int8;
BEGIN
    binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,ARRAY[
        'absent'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        'retain'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        ''::pg_catalog.bytea,''::pg_catalog.bytea,obj]::pg_catalog.bytea[]);
    intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
        'job'::pg_catalog.bytea,'0'::pg_catalog.bytea,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,
        '1'::pg_catalog.bytea,'1'::pg_catalog.bytea,scope_bytes,'0'::pg_catalog.bytea,obj,binding,
        'disabled'::pg_catalog.bytea,'2'::pg_catalog.bytea,'0'::pg_catalog.bytea,
        modkit_events._instant_bytes(t)]::pg_catalog.bytea[]);
    INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
        schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
        intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
        original_available_at,state,cancellation_requested,ownership_revision,available_at,
        cycle,attempt_count,created_at,updated_at)
    VALUES(wid,'job',NULL,'jobs'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,
        1,1,scope_bytes,'a'::pg_catalog.bytea,intent,obj,'{}'::pg_catalog.bytea,binding,'disabled',2,
        t,'queued',FALSE,0,t,1,0,t,t);
    -- A work-only owner structural row is observable corruption, not absence.
    BEGIN
        PERFORM * FROM modkit_events.e15(wid);
        RAISE EXCEPTION 'S8 missing required job half returned normally';
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN
        NULL;
    END;
    INSERT INTO modkit_events.job_payloads VALUES(wid,'a'::pg_catalog.bytea,NULL,NULL,binding,obj,
        'absent',NULL,NULL,NULL,NULL,NULL,''::pg_catalog.bytea,'retain',obj);
    SELECT pg_catalog.count(*) INTO n FROM modkit_events.e15(wid);
    IF n IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'S8 present job optional cardinality differs'; END IF;
    SELECT r.* INTO STRICT got FROM modkit_events.e15(wid) AS r;
    IF got.work_id IS DISTINCT FROM wid OR got.kind IS DISTINCT FROM 'job'
       OR got.state IS DISTINCT FROM 'queued' OR got.attempt_count IS DISTINCT FROM 0
       OR got.intent_evidence IS DISTINCT FROM intent OR got.protected_binding IS DISTINCT FROM binding
       OR got.scope_evidence IS DISTINCT FROM scope_bytes OR got.semantic_input IS DISTINCT FROM obj
       OR got.replay_input IS DISTINCT FROM '{}'::pg_catalog.bytea
       OR got.resolution_present IS DISTINCT FROM FALSE
       OR got.resolution_record_operation_id IS NOT NULL
       OR got.resolution_record_operation_kind IS NOT NULL
       OR got.resolution_record_work_id IS NOT NULL
       OR got.resolution_record_expected_revision IS NOT NULL
       OR got.resolution_record_cycle IS NOT NULL OR got.resolution_record_attempt IS NOT NULL
       OR got.resolution_record_dispatch_id IS NOT NULL OR got.resolution_record_outcome IS NOT NULL
       OR got.resolution_record_retry_at IS NOT NULL OR got.resolution_record_result IS NOT NULL
       OR got.resolution_record_result_digest IS NOT NULL OR got.resolution_record_reason IS NOT NULL
       OR got.resolution_record_evidence IS NOT NULL OR got.resolution_record_binding IS NOT NULL
       OR got.resolution_record_resolution_root_xid IS NOT NULL
       OR got.resolution_record_recorded_at IS NOT NULL THEN
        RAISE EXCEPTION 'S8 queued job/full false-NULL projection differs';
    END IF;
END
$test$;
