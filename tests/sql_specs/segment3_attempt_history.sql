-- Source-first independent expected outcomes. NOT_RUN. Owner/disposable caller transaction.
DO $test$
DECLARE w pg_catalog.uuid := '30000000-0000-0000-0000-000000000001'::pg_catalog.uuid;
    d pg_catalog.uuid := '30000000-0000-0000-0000-000000000002'::pg_catalog.uuid;
    changed pg_catalog.bool; i pg_catalog.int4; code pg_catalog.text; h pg_catalog.int8;
BEGIN
    INSERT INTO modkit_events.work(work_id,kind,namespace,command_type,schema_version_decimal,canonical_version,scope_evidence,scope_application,intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,original_available_at,state,cancellation_requested,ownership_revision,available_at,cycle,attempt_count,created_at,updated_at)
    VALUES(w,'job','n'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,pg_catalog.decode('4d4b5343010001610000','hex'),'a'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,''::pg_catalog.bytea,'application_safe',3,'2030-01-01 00:00:00+00','queued',FALSE,0,'2030-01-01 00:00:00+00',1,0,'2030-01-01 00:00:00+00','2030-01-01 00:00:00+00');
    INSERT INTO modkit_events.attempts VALUES(w,1,1,d,'effect'::pg_catalog.bytea,''::pg_catalog.bytea,NULL,pg_catalog.pg_current_xact_id(),'dispatched',''::pg_catalog.bytea,'2030-01-01 00:00:00+00');
    FOR i IN 1..6 LOOP
      changed := TRUE;
      BEGIN
        UPDATE modkit_events.attempts SET
          effect_id=CASE WHEN i=1 THEN 'changed'::pg_catalog.bytea ELSE effect_id END,
          request_evidence=CASE WHEN i=2 THEN 'changed'::pg_catalog.bytea ELSE request_evidence END,
          provider_key_reference=CASE WHEN i=3 THEN 'changed'::pg_catalog.bytea ELSE provider_key_reference END,
          recorded_at=CASE WHEN i=4 THEN '2030-01-02 00:00:00+00'::pg_catalog.timestamptz ELSE recorded_at END,
          dispatch_id=CASE WHEN i=5 THEN w ELSE dispatch_id END,
          dispatch_root_xid=CASE WHEN i=6 THEN '1'::pg_catalog.xid8 ELSE dispatch_root_xid END,
          outcome='uncertain' WHERE work_id=w;
      EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE;
      END;
      IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'immutable dispatch field changed'; END IF;
    END LOOP;
    changed := TRUE;
    BEGIN UPDATE modkit_events.attempts SET outcome='safe_retry' WHERE work_id=w;
    EXCEPTION WHEN SQLSTATE 'PZ004' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'direct dispatched to safe_retry'; END IF;
    changed := TRUE;
    BEGIN UPDATE modkit_events.attempts SET outcome='succeeded',evidence='not_generated'::pg_catalog.bytea WHERE work_id=w;
    EXCEPTION WHEN SQLSTATE 'PZ004' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'E10 local edge retained nongenerated evidence'; END IF;
    UPDATE modkit_events.attempts SET outcome='uncertain',evidence='audit'::pg_catalog.bytea WHERE work_id=w;
    UPDATE modkit_events.attempts SET outcome='safe_retry',evidence=''::pg_catalog.bytea WHERE work_id=w;
    changed := TRUE;
    BEGIN UPDATE modkit_events.attempts SET outcome='dispatched' WHERE work_id=w;
    EXCEPTION WHEN SQLSTATE 'PZ004' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'resolved attempt reset'; END IF;
    changed := TRUE;
    BEGIN DELETE FROM modkit_events.attempts WHERE work_id=w;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'attempt deleted'; END IF;
    INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
      VALUES(w,1,0,'intake_runnable','intake_runnable',NULL,0,''::pg_catalog.bytea,'2030-01-01 00:00:00+00') RETURNING history_id INTO h;
    changed := TRUE;
    BEGIN UPDATE modkit_events.work_history SET reason=reason WHERE history_id=h;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'history no-op update accepted'; END IF;
    changed := TRUE;
    BEGIN DELETE FROM modkit_events.work_history WHERE history_id=h;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'history deleted'; END IF;
    FOREACH code IN ARRAY ARRAY['claim','defer','recover_claim','failure_retry','reconcile_safe_retry'] LOOP
      changed := TRUE;
      BEGIN
        INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
          VALUES(w,1,1000,code,code,CASE WHEN code='claim' THEN d END,1,''::pg_catalog.bytea,'2030-01-01 00:00:00+00');
      EXCEPTION WHEN check_violation THEN changed := FALSE; END;
      IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'impossible history ordinal'; END IF;
    END LOOP;
    INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
      VALUES(w,1,1000,'renew','renew',d,1,''::pg_catalog.bytea,'2030-01-01 00:00:00+00');
END
$test$;
-- These isolated records do not assert a matching public dispatch/producer or
-- current work state; future full entrypoint fixture must establish those too.
