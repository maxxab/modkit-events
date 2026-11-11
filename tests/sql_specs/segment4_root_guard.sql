-- Prospective source-first segment4 oracles. ALL NOT_RUN.
-- No SQL/parser/compiler/runtime execution was released for this file.
-- Later authorized fixture executor must supply a FRESH READ COMMITTED root
-- under the existing schema owner, with no assigned xid before the first block.
-- The required schema snapshot/application is separately gated: the partial
-- candidate is NOT_READY to install. Caller must fully ROLLBACK afterward.
-- No transaction, role, grants, constraint-mode or service setup is done here.

-- T09-1 / T14-1: catches assigning E09, fabricated/absent root and extra rows.
DO $test$
DECLARE
    xid_before pg_catalog.xid8;
    xid_after pg_catalog.xid8;
    xid_result pg_catalog.xid8;
    row_count pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'fixture requires READ COMMITTED';
    END IF;
    xid_before := pg_catalog.pg_current_xact_id_if_assigned();
    IF xid_before IS NOT NULL THEN RAISE EXCEPTION 'fixture root already assigned'; END IF;
    SELECT pg_catalog.count(*) INTO row_count
      FROM modkit_events.e09('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,
        '40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,1,0);
    xid_after := pg_catalog.pg_current_xact_id_if_assigned();
    IF row_count IS DISTINCT FROM 0 OR xid_after IS NOT NULL THEN
        RAISE EXCEPTION 'E09 assigned root or fabricated guard';
    END IF;
    SELECT e.root_xid INTO STRICT xid_result FROM modkit_events.e14() AS e;
    IF xid_result IS NULL OR xid_result <= '0'::pg_catalog.xid8
       OR xid_result IS DISTINCT FROM pg_catalog.pg_current_xact_id_if_assigned() THEN
        RAISE EXCEPTION 'E14 did not return actual root';
    END IF;
    SELECT e.root_xid INTO STRICT xid_after FROM modkit_events.e14() AS e;
    IF xid_after IS DISTINCT FROM xid_result THEN RAISE EXCEPTION 'E14 root changed'; END IF;
END
$test$;

-- T09-4: catches STRICT/NULL-short-circuit and omitted argument boundaries.
-- Each literal invalid tuple must produce exactly PZ006, not arbitrary errors.
DO $test$
DECLARE
    c pg_catalog.record;
    rejected pg_catalog.bool;
BEGIN
    FOR c IN SELECT * FROM (VALUES
      (NULL::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1::pg_catalog.int8,1::pg_catalog.int4,1::pg_catalog.int4),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,NULL::pg_catalog.uuid,1,1,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,NULL::pg_catalog.int8,1,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,NULL::pg_catalog.int4,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,1,NULL::pg_catalog.int4),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,0,1,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,-1,1,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,0,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,2,1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,1,-1),
      ('40000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'40000000-0000-0000-0000-000000000003'::pg_catalog.uuid,1,1,1001)
    ) AS bad(work_id,token,ownership_revision,cycle,expected_attempt)
    LOOP
        rejected := FALSE;
        BEGIN
            PERFORM * FROM modkit_events.e09(c.work_id,c.token,c.ownership_revision,c.cycle,c.expected_attempt);
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN rejected := TRUE;
        END;
        IF rejected IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'E09 accepted invalid Fence'; END IF;
    END LOOP;
END
$test$;

-- T09-2/3/5/7: catches wrong projection, missing predicates, accepting
-- satisfied guards and unintended observation writes. The positive strict
-- fetch rejects missing/extra rows; absence of LIMIT is a source-review check,
-- not discrimination supplied by a fixture with valid unique guard identity.
-- Owner-only structural records deliberately do NOT prove public E08/E10,
-- dispatch provenance, or current live work. Opaque work admission fields are
-- valid only for the CURRENT partial table; never weaken later admission rules
-- to retain them as a full public fixture. All inserted guards end in rollback.
DO $test$
DECLARE
    w pg_catalog.uuid := '40000000-0000-0000-0000-000000000001'::pg_catalog.uuid;
    other_work pg_catalog.uuid := '40000000-0000-0000-0000-000000000002'::pg_catalog.uuid;
    tok pg_catalog.uuid := '40000000-0000-0000-0000-000000000003'::pg_catalog.uuid;
    guard pg_catalog.uuid := '40000000-0000-0000-0000-000000000004'::pg_catalog.uuid;
    actual_root pg_catalog.xid8 := pg_catalog.pg_current_xact_id();
    fake_other_root pg_catalog.xid8;
    result_row pg_catalog.record;
    guard_before pg_catalog.record;
    guard_after pg_catalog.record;
    work_before pg_catalog.record;
    work_after pg_catalog.record;
    row_count pg_catalog.int8;
    c pg_catalog.record;
BEGIN
    INSERT INTO modkit_events.work(work_id,kind,namespace,command_type,schema_version_decimal,canonical_version,scope_evidence,scope_application,intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,original_available_at,state,cancellation_requested,ownership_revision,available_at,cycle,attempt_count,created_at,updated_at)
      SELECT v.id,'job','n'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,
        pg_catalog.decode('4d4b5343010001610000','hex'),'a'::pg_catalog.bytea,
        'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,''::pg_catalog.bytea,
        'application_safe',1000,'2030-01-01 00:00:00+00'::pg_catalog.timestamptz,
        'queued',FALSE,0,'2030-01-01 00:00:00+00'::pg_catalog.timestamptz,1,0,
        '2030-01-01 00:00:00+00'::pg_catalog.timestamptz,'2030-01-01 00:00:00+00'::pg_catalog.timestamptz
      FROM (VALUES(w),(other_work)) AS v(id);
    INSERT INTO modkit_events.finalization_guards(guard_id,work_id,root_xid,token,ownership_revision,cycle,expected_attempt,satisfied)
      VALUES(guard,w,actual_root,tok,1,1,1,FALSE);
    -- This is a synthetic owner-only root mismatch, NOT another committed root.
    fake_other_root := CASE WHEN actual_root = '1'::pg_catalog.xid8 THEN '2'::pg_catalog.xid8 ELSE '1'::pg_catalog.xid8 END;
    INSERT INTO modkit_events.finalization_guards(guard_id,work_id,root_xid,token,ownership_revision,cycle,expected_attempt,satisfied)
      VALUES('40000000-0000-0000-0000-000000000005'::pg_catalog.uuid,other_work,fake_other_root,tok,1,1,1,FALSE);
    SELECT g.* INTO STRICT guard_before FROM modkit_events.finalization_guards AS g WHERE g.guard_id=guard;
    SELECT t.* INTO STRICT work_before FROM modkit_events.work AS t WHERE t.work_id=w;
    SELECT e.* INTO STRICT result_row FROM modkit_events.e09(w,tok,1,1,1) AS e;
    IF ROW(result_row.guard_id,result_row.work_id,result_row.root_xid,result_row.token,
        result_row.ownership_revision,result_row.cycle,result_row.expected_attempt,
        result_row.satisfied,result_row.final_fence_at,result_row.terminal_state,result_row.result_digest)
       IS DISTINCT FROM ROW(guard,w,actual_root,tok,1::pg_catalog.int8,1::pg_catalog.int4,1::pg_catalog.int4,
        FALSE,NULL::pg_catalog.timestamptz,NULL::pg_catalog.text,NULL::pg_catalog.bytea) THEN
        RAISE EXCEPTION 'E09 guard tuple mismatch';
    END IF;
    -- Legal inputs that cannot match the one current-root fixture, including
    -- general Fence attempt0 and upper/zero-UUID bounds, must yield zero rows.
    FOR c IN SELECT * FROM (VALUES
      (other_work,tok,1::pg_catalog.int8,1::pg_catalog.int4),
      ('00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,tok,1,1),
      (w,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,1),
      (w,tok,2,1),(w,tok,9223372036854775807::pg_catalog.int8,1),
      (w,tok,1,0),(w,tok,1,999),(w,tok,1,1000)
    ) AS misses(work_id,token,ownership_revision,expected_attempt)
    LOOP
        SELECT pg_catalog.count(*) INTO row_count FROM modkit_events.e09(c.work_id,c.token,c.ownership_revision,1,c.expected_attempt);
        IF row_count IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'E09 exposed nonmatching guard'; END IF;
    END LOOP;
    PERFORM * FROM modkit_events.e14();
    PERFORM * FROM modkit_events.e09(w,tok,1,1,1);
    SELECT g.* INTO STRICT guard_after FROM modkit_events.finalization_guards AS g WHERE g.guard_id=guard;
    SELECT t.* INTO STRICT work_after FROM modkit_events.work AS t WHERE t.work_id=w;
    IF guard_after IS DISTINCT FROM guard_before OR work_after IS DISTINCT FROM work_before THEN
        RAISE EXCEPTION 'root or guard observation changed records';
    END IF;
    SELECT pg_catalog.count(*) INTO row_count FROM modkit_events.work_history AS h WHERE h.work_id IN (w,other_work);
    IF row_count IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'observation appended work history'; END IF;
    SELECT pg_catalog.count(*) INTO row_count FROM modkit_events.attempts AS a WHERE a.work_id IN (w,other_work);
    IF row_count IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'observation inserted attempt'; END IF;
    -- Owner structural satisfaction tests only the E09 satisfied predicate.
    -- It is not an E10/final-fence/result-provenance test or commit certificate.
    UPDATE modkit_events.finalization_guards AS g SET satisfied=TRUE,
      final_fence_at='2030-01-01 00:00:00+00'::pg_catalog.timestamptz,
      terminal_state='succeeded',result_digest=pg_catalog.sha256('result'::pg_catalog.bytea)
      WHERE g.guard_id=guard;
    SELECT pg_catalog.count(*) INTO row_count FROM modkit_events.e09(w,tok,1,1,1);
    IF row_count IS DISTINCT FROM 0 THEN RAISE EXCEPTION 'E09 exposed satisfied guard'; END IF;
END
$test$;
-- Caller MUST fully roll back this disposable root. The synthetic other-root
-- guard remains unsatisfied. Do not disable triggers or commit this fixture.
-- Isolation, savepoint, cross-root, valid positive upper-endpoint guard, exact
-- installed signature/ACL and real producer schedules are in the companion MD.
