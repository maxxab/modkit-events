-- NOT_RUN. Same disposable owner fixture transaction as segment3_attempt_history.sql.
-- Tests structural storage only, not authority/current state/operation entrypoints.
DO $test$
DECLARE w pg_catalog.uuid := '30000000-0000-0000-0000-000000000001'::pg_catalog.uuid;
    d pg_catalog.uuid := '30000000-0000-0000-0000-000000000002'::pg_catalog.uuid;
    o pg_catalog.uuid := '30000000-0000-0000-0000-000000000003'::pg_catalog.uuid;
    o2 pg_catalog.uuid := '30000000-0000-0000-0000-000000000004'::pg_catalog.uuid;
    changed pg_catalog.bool; observed pg_catalog.record;
BEGIN
    INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,work_id,expected_revision,cycle,attempt,dispatch_id,requested_outcome,retry_at,evidence,binding,resolution_root_xid,recorded_at)
      VALUES(o,'reconcile_work',w,1,1,1,d,'safe_retry','2030-01-02 00:00:00+00',''::pg_catalog.bytea,''::pg_catalog.bytea,pg_catalog.pg_current_xact_id(),'2030-01-01 00:00:00+00');
    SELECT requested_reason,requested_result,result_digest,requested_receipt,resulting_revision,token,event_id,requested_outcome,dispatch_id
      INTO observed FROM modkit_events.mutation_operations WHERE operation_id=o;
    IF NOT FOUND THEN RAISE EXCEPTION 'operation missing'; END IF;
    IF observed.requested_reason IS NOT NULL OR observed.requested_result IS NOT NULL OR observed.result_digest IS NOT NULL
       OR observed.requested_receipt IS NOT NULL OR observed.resulting_revision IS NOT NULL OR observed.token IS NOT NULL
       OR observed.event_id IS NOT NULL OR observed.requested_outcome IS DISTINCT FROM 'safe_retry' OR observed.dispatch_id IS DISTINCT FROM d THEN
      RAISE EXCEPTION 'operation tuple changed'; END IF;
    changed := TRUE;
    BEGIN UPDATE modkit_events.mutation_operations SET binding=binding WHERE operation_id=o;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'operation no-op update accepted'; END IF;
    changed := TRUE;
    BEGIN DELETE FROM modkit_events.mutation_operations WHERE operation_id=o;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'operation deleted'; END IF;
    changed := TRUE;
    BEGIN
      INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,work_id,expected_revision,cycle,attempt,dispatch_id,requested_outcome,retry_at,requested_reason,evidence,binding,resolution_root_xid,recorded_at)
        VALUES(o2,'reconcile_work',w,1,1,1,d,'safe_retry','2030-01-02 00:00:00+00','reconcile_safe_retry',''::pg_catalog.bytea,''::pg_catalog.bytea,pg_catalog.pg_current_xact_id(),'2030-01-01 00:00:00+00');
    EXCEPTION WHEN check_violation THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'E31 generated history reason leaked into request'; END IF;
    INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,work_id,expected_revision,token,cycle,attempt,dispatch_id,failed_business_root,requested_reason,evidence,binding,resulting_revision,recorded_at)
      VALUES(o2,'hold_uncertain',w,1,d,1,1,d,'1'::pg_catalog.xid8,'unknown',''::pg_catalog.bytea,''::pg_catalog.bytea,2,'2030-01-01 00:00:00+00');
    changed := TRUE;
    BEGIN
      INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,work_id,expected_revision,token,cycle,attempt,dispatch_id,failed_business_root,requested_reason,evidence,binding,resulting_revision,recorded_at)
        VALUES(o2,'hold_uncertain',w,1,d,1,1,d,'1'::pg_catalog.xid8,'changed',''::pg_catalog.bytea,''::pg_catalog.bytea,2,'2030-01-01 00:00:00+00');
    EXCEPTION WHEN unique_violation THEN changed := FALSE; END;
    IF changed IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'global operation ID reused'; END IF;
END
$test$;
-- Full typed exact-repeat returns/conflicts require future E27/E31/E32 source;
-- unique INSERT failure alone is not replay-safe reconciliation evidence.
