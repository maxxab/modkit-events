-- Segment5 E08 prospective oracles, authored before production. ALL NOT_RUN.
-- No SQL/parser/compiler/test/runtime execution is authorized. This partial
-- schema is NOT_READY to install. A later separately authorized executor must
-- supply an isolated owner fixture database, fresh READ COMMITTED caller root,
-- and initially DEFERRED guard constraint. Caller must fully ROLLBACK afterward.
-- No role/constraint/session/transaction changes are made by this fixture.
-- Owner rows below are structural only: canonical intent/subtype/public producer
-- provenance and dispatch COMMIT are NOT established by these rows.
-- The companion schedules contain mandatory N1 reachability/stage, N2 lock,
-- N3 committed public-producer and N4 driver savepoint obligations.

-- S5-ARG: mutation removing NULL/range validation or treating attempt0 as an
-- invalid argument must fail. Native typed coercion/overflow precedes E08.
DO $test$
DECLARE c pg_catalog.record; got pg_catalog.text;
BEGIN
    FOR c IN SELECT * FROM (VALUES
      (NULL::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1::pg_catalog.int8,1::pg_catalog.int4,1::pg_catalog.int4),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,NULL::pg_catalog.uuid,1,1,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,NULL::pg_catalog.int8,1,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,0,1,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,-1,1,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,NULL::pg_catalog.int4,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,0,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,2,1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,1,NULL::pg_catalog.int4),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,1,-1),
      ('50000000-0000-0000-0000-000000000001'::pg_catalog.uuid,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,1,1,1001)
    ) AS invalid(w,t,r,cy,a)
    LOOP
        BEGIN
            PERFORM * FROM modkit_events.e08(c.w,c.t,c.r,c.cy,c.a);
            RAISE EXCEPTION 'invalid E08 call returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got = RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM 'PZ006' THEN RAISE; END IF;
        END;
    END LOOP;
END
$test$;

-- S5-POS/DUP/FOOTPRINT: exact full positive result and selected duplicate key.
-- Discriminates request-only echoes, extra/missing rows, narrowed legal bounds,
-- root-only duplicate detection, non-guard writes and idempotent E08 repeats.
DO $test$
DECLARE
    c pg_catalog.record; returned_guard pg_catalog.record; stored_guard pg_catalog.record;
    after_guard pg_catalog.record; dup pg_catalog.int4; got pg_catalog.text;
    actual_root pg_catalog.xid8; t0 pg_catalog.timestamptz := pg_catalog.clock_timestamp();
    dispatch pg_catalog.uuid; before_count pg_catalog.int8; after_count pg_catalog.int8;
    wb modkit_events.work[]; wa modkit_events.work[];
    ab modkit_events.attempts[]; aa modkit_events.attempts[];
    sb modkit_events.subscriptions[]; sa modkit_events.subscriptions[];
    hb modkit_events.work_history[]; ha modkit_events.work_history[];
BEGIN
    SELECT r.root_xid INTO STRICT actual_root FROM modkit_events.e14() AS r;
    INSERT INTO modkit_events.subscriptions VALUES
      ('segment5-positive'::pg_catalog.bytea,''::pg_catalog.bytea,'sentinel'::pg_catalog.bytea,10,3,t0);
    FOR c IN SELECT * FROM (VALUES
      ('50000000-0000-0000-0000-000000000011'::pg_catalog.uuid,'job'::pg_catalog.text,1::pg_catalog.int4,1::pg_catalog.int8,FALSE),
      ('50000000-0000-0000-0000-000000000012'::pg_catalog.uuid,'job',999,9223372036854775807::pg_catalog.int8,TRUE),
      ('00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,'job',1000,1,FALSE),
      ('50000000-0000-0000-0000-000000000014'::pg_catalog.uuid,'inbox',1,1,TRUE),
      ('50000000-0000-0000-0000-000000000015'::pg_catalog.uuid,'inbox',999,1,FALSE),
      ('50000000-0000-0000-0000-000000000016'::pg_catalog.uuid,'inbox',1000,9223372036854775807::pg_catalog.int8,TRUE)
    ) AS positive(w,kind,a,r,capped)
    LOOP
        dispatch := pg_catalog.gen_random_uuid();
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
          schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
          intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,deadline,
          original_available_at,state,cancellation_requested,token,ownership_revision,lease_until,
          available_at,cycle,attempt_count,dispatch_id,created_at,updated_at)
        VALUES(c.w,c.kind,CASE WHEN c.kind='inbox' THEN 'segment5-positive'::pg_catalog.bytea END,
          'n'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,1,1,
          pg_catalog.decode('4d4b5343010001610000','hex'),'a'::pg_catalog.bytea,
          'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,''::pg_catalog.bytea,
          'application_safe',c.a,CASE WHEN c.capped THEN t0+'2 hours'::pg_catalog.interval END,
          t0,'running',FALSE,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,
          c.r,t0+'1 hour'::pg_catalog.interval,t0,1,c.a,dispatch,t0,t0);
        IF c.kind='inbox' THEN
            INSERT INTO modkit_events.inbox VALUES(c.w,'segment5-positive'::pg_catalog.bytea,
              pg_catalog.convert_to(c.w::pg_catalog.text,'UTF8'),DEFAULT,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea);
        END IF;
        INSERT INTO modkit_events.attempts VALUES(c.w,1,c.a,dispatch,'effect'::pg_catalog.bytea,
          'request'::pg_catalog.bytea,NULL,actual_root,'dispatched',''::pg_catalog.bytea,t0);
        SELECT pg_catalog.array_agg(w ORDER BY w.work_id) INTO wb FROM modkit_events.work AS w;
        SELECT pg_catalog.array_agg(a ORDER BY a.work_id,a.cycle,a.attempt) INTO ab FROM modkit_events.attempts AS a;
        SELECT pg_catalog.array_agg(s ORDER BY s.subscription_id) INTO sb FROM modkit_events.subscriptions AS s;
        SELECT pg_catalog.array_agg(h ORDER BY h.history_id) INTO hb FROM modkit_events.work_history AS h;
        SELECT pg_catalog.count(*) INTO before_count FROM modkit_events.finalization_guards;
        SELECT e.* INTO STRICT returned_guard FROM modkit_events.e08(c.w,
          '00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,c.r,1,c.a) AS e;
        SELECT g.* INTO STRICT stored_guard FROM modkit_events.finalization_guards AS g
          WHERE g.guard_id=returned_guard.guard_id;
        IF returned_guard IS DISTINCT FROM stored_guard OR returned_guard.guard_id IS NULL
          OR ROW(returned_guard.work_id,returned_guard.root_xid,returned_guard.token,
            returned_guard.ownership_revision,returned_guard.cycle,returned_guard.expected_attempt,
            returned_guard.satisfied,returned_guard.final_fence_at,returned_guard.terminal_state,returned_guard.result_digest)
          IS DISTINCT FROM ROW(c.w,actual_root,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,
            c.r,1::pg_catalog.int4,c.a,FALSE,NULL::pg_catalog.timestamptz,NULL::pg_catalog.text,NULL::pg_catalog.bytea)
        THEN RAISE EXCEPTION 'E08 did not return exactly the persisted full guard'; END IF;
        SELECT pg_catalog.count(*) INTO after_count FROM modkit_events.finalization_guards;
        IF after_count IS DISTINCT FROM before_count+1 THEN RAISE EXCEPTION 'unexpected guard write count'; END IF;
        FOR dup IN 1..2 LOOP
            BEGIN
                PERFORM * FROM modkit_events.e08(c.w,CASE WHEN dup=1
                  THEN '00000000-0000-0000-0000-000000000000'::pg_catalog.uuid
                  ELSE '50000000-0000-0000-0000-000000000099'::pg_catalog.uuid END,c.r,1,c.a);
                RAISE EXCEPTION 'duplicate E08 returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got = RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ008' THEN RAISE; END IF;
            END;
            SELECT g.* INTO STRICT after_guard FROM modkit_events.finalization_guards AS g WHERE g.guard_id=returned_guard.guard_id;
            IF after_guard IS DISTINCT FROM stored_guard THEN RAISE EXCEPTION 'duplicate changed guard'; END IF;
        END LOOP;
        -- Owner structural satisfied-row case only, NOT an E10 certificate.
        UPDATE modkit_events.finalization_guards SET satisfied=TRUE,final_fence_at=t0,
          terminal_state='succeeded',result_digest=pg_catalog.sha256('result'::pg_catalog.bytea)
          WHERE guard_id=returned_guard.guard_id;
        SELECT g.* INTO STRICT stored_guard FROM modkit_events.finalization_guards AS g WHERE g.guard_id=returned_guard.guard_id;
        BEGIN
            PERFORM * FROM modkit_events.e08(c.w,'00000000-0000-0000-0000-000000000000'::pg_catalog.uuid,c.r,1,c.a);
            RAISE EXCEPTION 'satisfied duplicate E08 returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got = RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM 'PZ008' THEN RAISE; END IF;
        END;
        SELECT g.* INTO STRICT after_guard FROM modkit_events.finalization_guards AS g WHERE g.guard_id=returned_guard.guard_id;
        SELECT pg_catalog.count(*) INTO after_count FROM modkit_events.finalization_guards;
        IF after_guard IS DISTINCT FROM stored_guard OR after_count IS DISTINCT FROM before_count+1
        THEN RAISE EXCEPTION 'duplicate changed or added guard'; END IF;
        SELECT pg_catalog.array_agg(w ORDER BY w.work_id) INTO wa FROM modkit_events.work AS w;
        SELECT pg_catalog.array_agg(a ORDER BY a.work_id,a.cycle,a.attempt) INTO aa FROM modkit_events.attempts AS a;
        SELECT pg_catalog.array_agg(s ORDER BY s.subscription_id) INTO sa FROM modkit_events.subscriptions AS s;
        SELECT pg_catalog.array_agg(h ORDER BY h.history_id) INTO ha FROM modkit_events.work_history AS h;
        IF wa IS DISTINCT FROM wb OR aa IS DISTINCT FROM ab OR sa IS DISTINCT FROM sb OR ha IS DISTINCT FROM hb
        THEN RAISE EXCEPTION 'E08 changed non-guard records'; END IF;
    END LOOP;
END
$test$;

-- S5-FAIL: real allowed structural defects; every call must fail with its exact
-- category. Normal return raises P0001 and FAILS the test, not a swallowed pass.
-- The exception block uses PostgreSQL's automatic subtransaction recovery, then
-- checks full state BEFORE any outer rollback. It does not by itself qualify
-- driver SAVEPOINT behavior. N4's separate driver schedule records the actual
-- failed call first, then performs explicit cleanup and the same comparisons.
DO $test$
DECLARE
    c pg_catalog.record; w pg_catalog.uuid; d pg_catalog.uuid;
    root_id pg_catalog.xid8 := pg_catalog.pg_current_xact_id();
    tok pg_catalog.uuid := '50000000-0000-0000-0000-000000000098'::pg_catalog.uuid;
    t0 pg_catalog.timestamptz := pg_catalog.clock_timestamp(); got pg_catalog.text;
    wb modkit_events.work[]; wa modkit_events.work[];
    ab modkit_events.attempts[]; aa modkit_events.attempts[];
    sb modkit_events.subscriptions[]; sa modkit_events.subscriptions[];
    hb modkit_events.work_history[]; ha modkit_events.work_history[];
    gb modkit_events.finalization_guards[]; ga modkit_events.finalization_guards[];
BEGIN
    INSERT INTO modkit_events.subscriptions VALUES
      ('segment5-sentinel'::pg_catalog.bytea,''::pg_catalog.bytea,'preserve-me'::pg_catalog.bytea,1,0,t0);
    FOR c IN SELECT * FROM (VALUES
      ('missing_attempt'::pg_catalog.text,'PZ012'::pg_catalog.text),('wrong_dispatch','PZ012'),
      ('wrong_ordinal','PZ012'),('resolved_attempt','PZ012'),('null_runnable','PZ012'),
      ('result_leak','PZ012'),('infinite_lease','PZ012'),('infinite_deadline','PZ012'),
      ('uncapped_lease','PZ012'),('cancelled_and_expired','PZ003'),('lease_expired','PZ003'),
      ('both_expired','PZ009'),('claimed_zero','PZ004'),('claimed_positive','PZ004'),
      ('request_zero','PZ003'),('stale_token','PZ003')
    ) AS cases(fault,expected)
    LOOP
        w:=pg_catalog.gen_random_uuid(); d:=pg_catalog.gen_random_uuid();
        INSERT INTO modkit_events.work(work_id,kind,namespace,command_type,schema_version_decimal,
          runnable_version,canonical_version,scope_evidence,scope_application,intent_evidence,
          semantic_input,replay_input,protected_binding,replay_policy,max_attempts,deadline,
          original_available_at,state,cancellation_requested,token,ownership_revision,lease_until,
          available_at,cycle,attempt_count,dispatch_id,result,created_at,updated_at)
        VALUES(w,'job','n'::pg_catalog.bytea,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,
          CASE WHEN c.fault='null_runnable' THEN NULL ELSE 1 END,1,
          pg_catalog.decode('4d4b5343010001610000','hex'),'a'::pg_catalog.bytea,
          'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,''::pg_catalog.bytea,'application_safe',1000,
          CASE WHEN c.fault='infinite_deadline' THEN 'infinity'::pg_catalog.timestamptz
            WHEN c.fault='uncapped_lease' THEN t0+'30 minutes'::pg_catalog.interval
            WHEN c.fault='both_expired' THEN t0-'1 minute'::pg_catalog.interval END,
          t0,CASE WHEN c.fault IN ('claimed_zero','claimed_positive') THEN 'claimed' ELSE 'running' END,
          c.fault='cancelled_and_expired',tok,1,
          CASE WHEN c.fault='infinite_lease' THEN 'infinity'::pg_catalog.timestamptz
            WHEN c.fault IN ('cancelled_and_expired','lease_expired','both_expired') THEN t0-'2 minutes'::pg_catalog.interval
            ELSE t0+'1 hour'::pg_catalog.interval END,
          t0,1,CASE WHEN c.fault='claimed_zero' THEN 0 ELSE 1 END,
          CASE WHEN c.fault IN ('claimed_zero','claimed_positive') THEN NULL ELSE d END,
          CASE WHEN c.fault='result_leak' THEN 'result'::pg_catalog.bytea END,t0,t0);
        IF c.fault NOT IN ('missing_attempt','claimed_zero','claimed_positive') THEN
            INSERT INTO modkit_events.attempts VALUES(w,1,CASE WHEN c.fault='wrong_ordinal' THEN 2 ELSE 1 END,
              CASE WHEN c.fault='wrong_dispatch' THEN pg_catalog.gen_random_uuid() ELSE d END,
              'effect'::pg_catalog.bytea,'request'::pg_catalog.bytea,NULL,root_id,'dispatched',''::pg_catalog.bytea,t0);
            IF c.fault='resolved_attempt' THEN
                UPDATE modkit_events.attempts SET outcome='succeeded' WHERE work_id=w;
            END IF;
        END IF;
        SELECT pg_catalog.array_agg(x ORDER BY x.work_id) INTO wb FROM modkit_events.work AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.work_id,x.cycle,x.attempt) INTO ab FROM modkit_events.attempts AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.subscription_id) INTO sb FROM modkit_events.subscriptions AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.history_id) INTO hb FROM modkit_events.work_history AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.guard_id) INTO gb FROM modkit_events.finalization_guards AS x;
        BEGIN
            PERFORM * FROM modkit_events.e08(w,CASE WHEN c.fault='stale_token' THEN pg_catalog.gen_random_uuid() ELSE tok END,
              1,1,CASE WHEN c.fault IN ('claimed_zero','request_zero') THEN 0 ELSE 1 END);
            RAISE EXCEPTION 'E08 returned normally for failure case %',c.fault;
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got = RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM c.expected THEN RAISE; END IF;
        END;
        -- No unconditional ROLLBACK precedes this decisive observation.
        IF EXISTS(SELECT 1 FROM modkit_events.finalization_guards AS g WHERE g.work_id=w AND g.root_xid=root_id)
        THEN RAISE EXCEPTION 'failed E08 left a provisional guard'; END IF;
        SELECT pg_catalog.array_agg(x ORDER BY x.work_id) INTO wa FROM modkit_events.work AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.work_id,x.cycle,x.attempt) INTO aa FROM modkit_events.attempts AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.subscription_id) INTO sa FROM modkit_events.subscriptions AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.history_id) INTO ha FROM modkit_events.work_history AS x;
        SELECT pg_catalog.array_agg(x ORDER BY x.guard_id) INTO ga FROM modkit_events.finalization_guards AS x;
        IF wa IS DISTINCT FROM wb OR aa IS DISTINCT FROM ab OR sa IS DISTINCT FROM sb
          OR ha IS DISTINCT FROM hb OR ga IS DISTINCT FROM gb
        THEN RAISE EXCEPTION 'failed E08 changed records or lost sentinel'; END IF;
    END LOOP;
END
$test$;
-- No execution result exists. Full caller rollback is required even though the
-- positive fixtures used owner-only satisfaction; they are NOT lawful success.
