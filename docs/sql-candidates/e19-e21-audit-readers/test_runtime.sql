SELECT * FROM modkit_events.e01('e30-sub'::bytea,''::bytea,'e30-group'::bytea,10000);
CREATE FUNCTION pg_temp.seed_e30(p_id uuid,p_namespace bytea,p_created timestamptz,p_complete bool DEFAULT TRUE)
RETURNS void LANGUAGE plpgsql AS $fixture$
DECLARE
    sub bytea:='e30-sub'::bytea;
    scope_bytes bytea:=decode('4d4b5343010001610000','hex');
    obj bytea:=decode('6f00000000','hex');
    binding bytea; replay bytea; semantic bytea; intent bytea;
BEGIN
    binding:=modkit_events._make_record('protected-binding'::bytea,ARRAY[
        'absent'::bytea,'0'::bytea,'0'::bytea,'0'::bytea,'retain'::bytea,
        '0'::bytea,'0'::bytea,''::bytea,''::bytea,obj]::bytea[]);
    replay:=convert_to('{"event_id":"'||p_id::text||'","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
    semantic:=modkit_events._event_replay_frame(replay);
    intent:=modkit_events._make_record('work-intent'::bytea,ARRAY[
        'inbox'::bytea,modkit_events._optional_bytes(sub),p_namespace,'cmd'::bytea,
        '1'::bytea,'1'::bytea,scope_bytes,'0'::bytea,semantic,binding,
        'disabled'::bytea,'2'::bytea,'0'::bytea,modkit_events._instant_bytes(p_created)]::bytea[]);
    INSERT INTO modkit_events.work
        (work_id,kind,subscription_id,namespace,command_type,schema_version_decimal,runnable_version,
         canonical_version,scope_evidence,scope_application,scope_tenant,scope_owner,idempotency_key,
         intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
         deadline,original_available_at,state,cancellation_requested,token,ownership_revision,
         lease_until,available_at,cycle,attempt_count,dispatch_id,result,created_at,updated_at,
         success_origin,completion_guard_id,final_fence_at,completion_result_digest,
         resolution_operation_id,terminal_resolution_operation_id)
    VALUES(p_id,'inbox',sub,p_namespace,'cmd'::bytea,'1'::bytea,1,
         1,scope_bytes,'a'::bytea,NULL,NULL,NULL,intent,semantic,replay,binding,'disabled',2,
         NULL,p_created,'queued',FALSE,NULL,0,NULL,p_created,1,0,NULL,NULL,p_created,p_created,
         NULL,NULL,NULL,NULL,NULL,NULL);
    IF p_complete THEN
        INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
        VALUES(p_id,sub,convert_to(p_id::text,'UTF8'),semantic,replay);
    END IF;
    UPDATE modkit_events.subscriptions SET nonterminal_count=nonterminal_count+1 WHERE subscription_id=sub;
END
$fixture$;

-- Run only on a fresh disposable fixture, inside its caller-owned READ COMMITTED
-- transaction after the full migration. This uses structural rows, not lifecycle proof.
-- The two identities are independent; no E10 call or native driver is involved.
SELECT pg_temp.seed_e30('ea190000-0000-0000-0000-000000000001','audit'::bytea,'2026-01-02 03:04:05+00');
SELECT pg_temp.seed_e30('ea190000-0000-0000-0000-000000000002','other'::bytea,'2026-01-02 03:04:05+00');
INSERT INTO modkit_events.work_history(history_id,work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
OVERRIDING SYSTEM VALUE
SELECT n*2,'ea190000-0000-0000-0000-000000000001',1,0,'intake_runnable','intake_runnable',NULL,0,''::bytea,'2026-01-02 03:04:05+00'::timestamptz
FROM generate_series(1,260) n;
INSERT INTO modkit_events.delivery_history(history_id,work_id,broker_reference,transport_observation,recorded_at)
OVERRIDING SYSTEM VALUE
SELECT n*2,'ea190000-0000-0000-0000-000000000001',convert_to(n::text,'UTF8'),''::bytea,'2026-01-02 03:04:05+00'::timestamptz
FROM generate_series(1,260) n;
INSERT INTO modkit_events.attempts(work_id,cycle,attempt,dispatch_id,effect_id,request_evidence,provider_key_reference,dispatch_root_xid,outcome,evidence,recorded_at)
SELECT 'ea190000-0000-0000-0000-000000000001',1,n,('ea210000-0000-0000-0000-'||lpad(n::text,12,'0'))::uuid,'effect'::bytea,''::bytea,NULL,pg_current_xact_id(),'dispatched',''::bytea,'2026-01-02 03:04:05+00'::timestamptz
FROM generate_series(1,260) n;
-- Other-parent records must never enter a requested page.
INSERT INTO modkit_events.work_history(history_id,work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
OVERRIDING SYSTEM VALUE VALUES(1,'ea190000-0000-0000-0000-000000000002',1,0,'intake_runnable','intake_runnable',NULL,0,''::bytea,'2026-01-02 03:04:05+00');
INSERT INTO modkit_events.delivery_history(history_id,work_id,broker_reference,transport_observation,recorded_at)
OVERRIDING SYSTEM VALUE VALUES(1,'ea190000-0000-0000-0000-000000000002','other'::bytea,''::bytea,'2026-01-02 03:04:05+00');
INSERT INTO modkit_events.attempts(work_id,cycle,attempt,dispatch_id,effect_id,request_evidence,provider_key_reference,dispatch_root_xid,outcome,evidence,recorded_at)
VALUES('ea190000-0000-0000-0000-000000000002',1,1,'ea210000-0000-0000-0001-000000000001','effect'::bytea,''::bytea,NULL,pg_current_xact_id(),'dispatched',''::bytea,'2026-01-02 03:04:05+00');

CREATE FUNCTION pg_temp.audit_snapshot() RETURNS jsonb LANGUAGE sql AS $snapshot$
SELECT jsonb_build_array(
 (SELECT jsonb_agg(to_jsonb(x) ORDER BY x.history_id) FROM modkit_events.work_history x),
 (SELECT jsonb_agg(to_jsonb(x) ORDER BY x.history_id) FROM modkit_events.delivery_history x),
 (SELECT jsonb_agg(to_jsonb(x) ORDER BY x.work_id,x.cycle,x.attempt) FROM modkit_events.attempts x),
 (SELECT jsonb_build_array(last_value,log_cnt,is_called) FROM modkit_events.work_history_history_id_seq),
 (SELECT jsonb_build_array(last_value,log_cnt,is_called) FROM modkit_events.delivery_history_history_id_seq));
$snapshot$;

DO $tests$
DECLARE
    id uuid:='ea190000-0000-0000-0000-000000000001';
    ids bigint[]; expected bigint[]; actual jsonb; want jsonb; before_state jsonb;
    fn text; query text; rejection_count integer; count_rows integer;
BEGIN
    before_state:=pg_temp.audit_snapshot();
    FOR fn IN SELECT unnest(ARRAY['e19','e20']) LOOP
        EXECUTE format('SELECT array_agg(history_id) FROM modkit_events.%I($1,0,256)',fn) INTO ids USING id;
        SELECT array_agg((n*2)::bigint ORDER BY n) INTO expected FROM generate_series(1,256) n;
        IF ids IS DISTINCT FROM expected THEN RAISE EXCEPTION '% first page differs',fn; END IF;
        EXECUTE format('SELECT array_agg(history_id) FROM modkit_events.%I($1,512,256)',fn) INTO ids USING id;
        IF ids IS DISTINCT FROM ARRAY[514,516,518,520]::bigint[] THEN RAISE EXCEPTION '% continuation differs',fn; END IF;
        EXECUTE format('SELECT array_agg(history_id) FROM modkit_events.%I($1,3,1)',fn) INTO ids USING id;
        IF ids IS DISTINCT FROM ARRAY[4]::bigint[] THEN RAISE EXCEPTION '% missing cursor differs',fn; END IF;
        EXECUTE format('SELECT count(*) FROM modkit_events.%I($1,9223372036854775807,256)',fn) INTO count_rows USING id;
        IF count_rows<>0 THEN RAISE EXCEPTION '% end cursor differs',fn; END IF;
        EXECUTE format('SELECT count(*) FROM modkit_events.%I($1,0,256)',fn) INTO count_rows USING '00000000-0000-0000-0000-000000000000'::uuid;
        IF count_rows<>0 THEN RAISE EXCEPTION '% absent parent leaked rows',fn; END IF;
    END LOOP;
    SELECT jsonb_agg(to_jsonb(x)) INTO actual FROM modkit_events.e19(id,0,1) x;
    SELECT jsonb_agg(to_jsonb(x)) INTO want FROM modkit_events.work_history x WHERE history_id=2;
    IF actual IS DISTINCT FROM want THEN RAISE EXCEPTION 'E19 complete row differs'; END IF;
    SELECT jsonb_agg(to_jsonb(x)) INTO actual FROM modkit_events.e20(id,0,1) x;
    SELECT jsonb_agg(to_jsonb(x)) INTO want FROM modkit_events.delivery_history x WHERE history_id=2;
    IF actual IS DISTINCT FROM want THEN RAISE EXCEPTION 'E20 complete row differs'; END IF;
    SELECT array_agg(attempt::bigint) INTO ids FROM modkit_events.e21(id,0,0,256);
    SELECT array_agg(n::bigint ORDER BY n) INTO expected FROM generate_series(1,256) n;
    IF ids IS DISTINCT FROM expected THEN RAISE EXCEPTION 'E21 first page differs'; END IF;
    SELECT array_agg(attempt::bigint) INTO ids FROM modkit_events.e21(id,1,256,256);
    IF ids IS DISTINCT FROM ARRAY[257,258,259,260]::bigint[] THEN RAISE EXCEPTION 'E21 continuation differs'; END IF;
    SELECT jsonb_agg(to_jsonb(x)) INTO actual FROM modkit_events.e21(id,0,2147483647,1) x;
    SELECT jsonb_agg(to_jsonb(x)) INTO want FROM modkit_events.attempts x WHERE work_id=id AND attempt=1;
    IF actual IS DISTINCT FROM want THEN RAISE EXCEPTION 'E21 lexicographic cursor or full row differs'; END IF;
    IF EXISTS(SELECT 1 FROM modkit_events.e21(id,1,260,256))
       OR EXISTS(SELECT 1 FROM modkit_events.e21(id,2147483647,0,256))
       OR EXISTS(SELECT 1 FROM modkit_events.e21('00000000-0000-0000-0000-000000000000',0,0,256)) THEN
        RAISE EXCEPTION 'E21 end or absent-parent cursor leaked rows';
    END IF;

    -- Each target is outside its exception handler if it fails to reject.
    FOREACH query IN ARRAY ARRAY[
        'SELECT * FROM modkit_events.e19(NULL,0,1)',
        format('SELECT * FROM modkit_events.e19(%L,NULL,1)',id),
        format('SELECT * FROM modkit_events.e19(%L,-1,1)',id),
        format('SELECT * FROM modkit_events.e19(%L,0,NULL)',id),
        format('SELECT * FROM modkit_events.e19(%L,0,0)',id),
        format('SELECT * FROM modkit_events.e19(%L,0,257)',id),
        'SELECT * FROM modkit_events.e20(NULL,0,1)',
        format('SELECT * FROM modkit_events.e20(%L,NULL,1)',id),
        format('SELECT * FROM modkit_events.e20(%L,-1,1)',id),
        format('SELECT * FROM modkit_events.e20(%L,0,NULL)',id),
        format('SELECT * FROM modkit_events.e20(%L,0,0)',id),
        format('SELECT * FROM modkit_events.e20(%L,0,257)',id),
        'SELECT * FROM modkit_events.e21(NULL,0,0,1)',
        format('SELECT * FROM modkit_events.e21(%L,NULL,0,1)',id),
        format('SELECT * FROM modkit_events.e21(%L,-1,0,1)',id),
        format('SELECT * FROM modkit_events.e21(%L,0,NULL,1)',id),
        format('SELECT * FROM modkit_events.e21(%L,0,-1,1)',id),
        format('SELECT * FROM modkit_events.e21(%L,0,0,NULL)',id),
        format('SELECT * FROM modkit_events.e21(%L,0,0,0)',id),
        format('SELECT * FROM modkit_events.e21(%L,0,0,257)',id)
    ] LOOP
        rejection_count:=0;
        BEGIN EXECUTE query; EXCEPTION WHEN SQLSTATE 'PZ006' THEN rejection_count:=1; END;
        IF rejection_count<>1 THEN RAISE EXCEPTION 'invalid input accepted: %',query; END IF;
    END LOOP;
    IF pg_temp.audit_snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'audit readers changed rows or sequences'; END IF;
END
$tests$;

-- Deliberate damaged-storage simulation, confined to this rollback transaction.
-- Relax only the three timestamp CHECKs; the product migration stays unchanged.
ALTER TABLE modkit_events.work_history DROP CONSTRAINT work_history_time_supported;
ALTER TABLE modkit_events.delivery_history DROP CONSTRAINT delivery_history_time_supported;
ALTER TABLE modkit_events.attempts DROP CONSTRAINT attempt_time_supported;

-- A representable page must not scan and reject later rows, but selecting a
-- malformed record fails the complete statement rather than silently dropping it.
INSERT INTO modkit_events.work_history(history_id,work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
OVERRIDING SYSTEM VALUE VALUES(999,'ea190000-0000-0000-0000-000000000001',1,0,'intake_runnable','intake_runnable',NULL,0,''::bytea,'infinity');
INSERT INTO modkit_events.delivery_history(history_id,work_id,broker_reference,transport_observation,recorded_at)
OVERRIDING SYSTEM VALUE VALUES(999,'ea190000-0000-0000-0000-000000000001','poison'::bytea,''::bytea,'infinity');
INSERT INTO modkit_events.attempts(work_id,cycle,attempt,dispatch_id,effect_id,request_evidence,provider_key_reference,dispatch_root_xid,outcome,evidence,recorded_at)
VALUES('ea190000-0000-0000-0000-000000000001',1,999,'ea210000-0000-0000-0000-000000000999','effect'::bytea,''::bytea,NULL,pg_current_xact_id(),'dispatched',''::bytea,'infinity');
DO $corruption$
DECLARE
    id uuid:='ea190000-0000-0000-0000-000000000001';
    query text; rejected bool; before_state jsonb;
BEGIN
    before_state:=pg_temp.audit_snapshot();
    IF (SELECT count(*) FROM modkit_events.e19(id,0,256))<>256
       OR (SELECT count(*) FROM modkit_events.e20(id,0,256))<>256
       OR (SELECT count(*) FROM modkit_events.e21(id,0,0,256))<>256 THEN
        RAISE EXCEPTION 'corruption beyond limit affected bounded page';
    END IF;
    FOREACH query IN ARRAY ARRAY[
        format('SELECT * FROM modkit_events.e19(%L,512,256)',id),
        format('SELECT * FROM modkit_events.e20(%L,512,256)',id),
        format('SELECT * FROM modkit_events.e21(%L,1,256,256)',id)
    ] LOOP
        rejected:=FALSE;
        BEGIN EXECUTE query; EXCEPTION WHEN SQLSTATE 'PZ012' THEN rejected:=TRUE; END;
        IF NOT rejected THEN RAISE EXCEPTION 'selected malformed record accepted: %',query; END IF;
    END LOOP;
    IF pg_temp.audit_snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'rejected readers changed state'; END IF;
END
$corruption$;
SELECT 'AUDIT_READER_RUNTIME_PASS' AS result;
