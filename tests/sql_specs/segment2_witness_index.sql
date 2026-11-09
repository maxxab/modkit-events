-- NOT_RUN. Partial-table owner fixture only. No registry/full certificate proof.
-- Run in caller-owned disposable test transaction; caller rolls it back.
DO $test$
DECLARE r pg_catalog.record; accepted pg_catalog.bool;
    id pg_catalog.uuid := '00000000-0000-0000-0000-000000000001'::pg_catalog.uuid;
    a pg_catalog.uuid := '00000000-0000-0000-0000-000000000002'::pg_catalog.uuid;
    b pg_catalog.uuid := '00000000-0000-0000-0000-000000000003'::pg_catalog.uuid;
BEGIN
    INSERT INTO modkit_events.work(work_id,kind,namespace,command_type,schema_version_decimal,canonical_version,scope_evidence,scope_application,intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,original_available_at,state,cancellation_requested,ownership_revision,available_at,cycle,attempt_count,created_at,updated_at)
    VALUES(id,'job','x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,pg_catalog.decode('4d4b5343010001610000','hex'),'a'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,''::pg_catalog.bytea,'application_safe',3,'2030-01-01 00:00:00+00','queued',FALSE,0,'2030-01-01 00:00:00+00',1,0,'2030-01-01 00:00:00+00','2030-01-01 00:00:00+00');
    FOR r IN SELECT * FROM (VALUES
        ('queued',NULL::pg_catalog.text,FALSE,NULL::pg_catalog.uuid,NULL::pg_catalog.uuid,TRUE),
        ('retry_waiting',NULL,FALSE,NULL,NULL,TRUE),
        ('queued',NULL,FALSE,a,NULL,FALSE),('queued',NULL,FALSE,NULL,a,FALSE),
        ('retry_waiting',NULL,FALSE,a,a,FALSE),('running',NULL,FALSE,a,a,FALSE),
        ('succeeded','guarded',TRUE,NULL,NULL,TRUE),
        ('succeeded','guarded',TRUE,a,NULL,FALSE),('succeeded','guarded',TRUE,NULL,a,FALSE),
        ('succeeded','reconciled',FALSE,a,a,TRUE),
        ('succeeded','reconciled',FALSE,NULL,a,FALSE),('succeeded','reconciled',FALSE,a,b,FALSE),
        ('succeeded',NULL,FALSE,NULL,NULL,FALSE),('succeeded','unknown',FALSE,a,a,FALSE),
        ('blocked_schema',NULL,FALSE,NULL,a,FALSE),('claimed',NULL,FALSE,NULL,a,FALSE),
        ('failed',NULL,FALSE,NULL,a,TRUE),('cancelled',NULL,FALSE,NULL,a,TRUE),
        ('failed',NULL,FALSE,a,a,FALSE),('expired',NULL,FALSE,NULL,a,FALSE),
        ('held',NULL,FALSE,NULL,a,FALSE),('cancelled',NULL,FALSE,NULL,NULL,TRUE)
      ) AS cases(state,origin,certificate,resolution,terminal,valid) LOOP
        accepted := TRUE;
        BEGIN
            UPDATE modkit_events.work SET state=r.state,success_origin=r.origin,
              completion_guard_id=CASE WHEN r.certificate THEN b END,
              final_fence_at=CASE WHEN r.certificate THEN '2030-01-01 00:00:00+00'::pg_catalog.timestamptz END,
              completion_result_digest=CASE WHEN r.certificate THEN pg_catalog.sha256(''::pg_catalog.bytea) END,
              result=CASE WHEN r.state='succeeded' THEN ''::pg_catalog.bytea END,
              resolution_operation_id=r.resolution,terminal_resolution_operation_id=r.terminal,
              attempt_count=1,dispatch_id=CASE WHEN r.state IN ('running','held','succeeded') THEN a END,
              token=CASE WHEN r.state IN ('running','claimed') THEN b END,
              lease_until=CASE WHEN r.state IN ('running','claimed') THEN '2030-01-01 00:00:00+00'::pg_catalog.timestamptz END
              WHERE work_id=id;
        EXCEPTION WHEN check_violation THEN accepted := FALSE;
        END;
        IF accepted IS DISTINCT FROM r.valid THEN RAISE EXCEPTION 'witness nullable union differs'; END IF;
    END LOOP;
    -- Existing partial indexes must not stand in for full immutable discovery.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_index AS i JOIN pg_catalog.pg_class AS c ON c.oid=i.indexrelid
      JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace
      WHERE n.nspname='modkit_events' AND c.relname='work_discovery_scan' AND i.indpred IS NULL AND i.indisvalid AND i.indisready
        AND i.indrelid='modkit_events.work'::pg_catalog.regclass
        AND pg_catalog.pg_get_indexdef(i.indexrelid,1,TRUE)='namespace'
        AND pg_catalog.pg_get_indexdef(i.indexrelid,2,TRUE)='kind'
        AND pg_catalog.pg_get_indexdef(i.indexrelid,3,TRUE)='work_id' AND i.indnkeyatts=3) THEN
      RAISE EXCEPTION 'full partition discovery index missing';
    END IF;
END
$test$;
-- Later E31 fixture must additionally retain immutable safe_retry operation while
-- current retry_waiting row has both resolution IDs NULL. Registry not authored.

-- Same caller-owned disposable fixture transaction as above. NOT_RUN.
DO $test$
DECLARE id pg_catalog.uuid := '00000000-0000-0000-0000-000000000001'::pg_catalog.uuid;
    a pg_catalog.uuid := '00000000-0000-0000-0000-000000000002'::pg_catalog.uuid;
    i pg_catalog.int4; mode pg_catalog.text; accepted pg_catalog.bool;
BEGIN
    FOREACH mode IN ARRAY ARRAY['guarded','reconciled'] LOOP
      FOR i IN 0..8 LOOP
        -- Independently reset all relevant arms to a valid success control.
        UPDATE modkit_events.work SET state='succeeded',success_origin=mode,
          result=''::pg_catalog.bytea,attempt_count=1,dispatch_id=a,token=NULL,lease_until=NULL,
          completion_guard_id=CASE WHEN mode='guarded' THEN a END,
          final_fence_at=CASE WHEN mode='guarded' THEN '2030-01-01 00:00:00+00'::pg_catalog.timestamptz END,
          completion_result_digest=CASE WHEN mode='guarded' THEN pg_catalog.sha256(''::pg_catalog.bytea) END,
          resolution_operation_id=CASE WHEN mode='reconciled' THEN a END,
          terminal_resolution_operation_id=CASE WHEN mode='reconciled' THEN a END WHERE work_id=id;
        IF i=0 THEN CONTINUE; END IF;
        accepted := TRUE;
        BEGIN
          IF mode='guarded' THEN
            UPDATE modkit_events.work SET
              completion_guard_id=CASE WHEN i=1 THEN NULL ELSE completion_guard_id END,
              final_fence_at=CASE WHEN i=2 THEN NULL ELSE final_fence_at END,
              completion_result_digest=CASE WHEN i=3 THEN NULL WHEN i=4 THEN pg_catalog.decode(pg_catalog.repeat('00',31),'hex') WHEN i=5 THEN pg_catalog.decode(pg_catalog.repeat('00',33),'hex') ELSE completion_result_digest END,
              result=CASE WHEN i=6 THEN NULL ELSE result END,
              dispatch_id=CASE WHEN i=7 THEN NULL ELSE dispatch_id END,
              success_origin=CASE WHEN i=8 THEN NULL ELSE success_origin END WHERE work_id=id;
          ELSE
            UPDATE modkit_events.work SET
              resolution_operation_id=CASE WHEN i=1 THEN NULL ELSE resolution_operation_id END,
              terminal_resolution_operation_id=CASE WHEN i=2 THEN NULL ELSE terminal_resolution_operation_id END,
              completion_guard_id=CASE WHEN i=3 THEN a ELSE completion_guard_id END,
              final_fence_at=CASE WHEN i=4 THEN '2030-01-01 00:00:00+00'::pg_catalog.timestamptz ELSE final_fence_at END,
              completion_result_digest=CASE WHEN i=5 THEN pg_catalog.sha256(''::pg_catalog.bytea) ELSE completion_result_digest END,
              result=CASE WHEN i=6 THEN NULL ELSE result END,
              dispatch_id=CASE WHEN i=7 THEN NULL ELSE dispatch_id END,
              success_origin=CASE WHEN i=8 THEN NULL ELSE success_origin END WHERE work_id=id;
          END IF;
        EXCEPTION WHEN check_violation THEN accepted := FALSE;
        END;
        IF accepted IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'missing/forbidden witness arm accepted'; END IF;
      END LOOP;
    END LOOP;
END
$test$;
