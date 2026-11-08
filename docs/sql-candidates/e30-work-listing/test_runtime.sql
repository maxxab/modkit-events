-- E30 reader qualification only. Run after the exact baseline plus e30.sql,
-- as the isolated schema owner in one caller-owned READ COMMITTED transaction.
-- Synthetic structural fixtures test reading, not public admission provenance.
-- All roles, schema, rows and grants must be rolled back by the invoking script.

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
SELECT pg_temp.seed_e30(('e3000000-0000-0000-0000-'||lpad((n*2)::text,12,'0'))::uuid,
    'e30-main'::bytea,'2026-01-02 03:04:05+00'::timestamptz)
FROM generate_series(1,260) AS n;
SELECT pg_temp.seed_e30('e3000000-0000-0000-0001-000000000001','e30-other'::bytea,'2026-01-02 03:04:05+00');
SELECT pg_temp.seed_e30('e3000000-0000-0000-0001-000000000002','jobs'::bytea,'2026-01-02 03:04:05+00');
SELECT pg_temp.seed_e30('e3000000-0000-0000-0001-000000000003','e30-broken'::bytea,'2026-01-02 03:04:05+00',FALSE);

CREATE FUNCTION pg_temp.data_snapshot() RETURNS jsonb LANGUAGE plpgsql AS $snapshot$
DECLARE item record; rows jsonb; result jsonb:='{}'::jsonb;
BEGIN
    FOR item IN SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='modkit_events' AND c.relkind IN ('r','S') ORDER BY c.relname
    LOOP
        IF item.relkind='S' THEN
            EXECUTE format('SELECT jsonb_build_object(''last_value'',last_value,''log_cnt'',log_cnt,''is_called'',is_called) FROM modkit_events.%I',item.relname) INTO rows;
        ELSE
        EXECUTE format('SELECT coalesce(jsonb_agg(entry ORDER BY entry::text COLLATE "C"),''[]''::jsonb) FROM (SELECT to_jsonb(x) AS entry FROM modkit_events.%I x) s',item.relname) INTO rows;
        END IF;
        result:=result||jsonb_build_object(item.relname,rows);
    END LOOP;
    RETURN result;
END
$snapshot$;

DO $tests$
DECLARE
    ids uuid[]; expected uuid[]; item record; before_state jsonb;
    t timestamptz:='2026-01-02 03:04:05+00';
BEGIN
    before_state:=pg_temp.data_snapshot();
    IF EXISTS (SELECT 1 FROM modkit_events.e30('absent'::bytea,NULL,NULL,256)) THEN
        RAISE EXCEPTION 'E30 empty namespace leaked rows'; END IF;
    SELECT array_agg(work_id ORDER BY created_at,work_id) INTO ids FROM modkit_events.e30('e30-main'::bytea,NULL,NULL,1);
    IF ids IS DISTINCT FROM ARRAY['e3000000-0000-0000-0000-000000000002'::uuid] THEN
        RAISE EXCEPTION 'E30 first page differs: %',ids; END IF;
    SELECT array_agg(('e3000000-0000-0000-0000-'||lpad((n*2)::text,12,'0'))::uuid ORDER BY n) INTO expected FROM generate_series(1,256) n;
    SELECT array_agg(work_id) INTO ids FROM modkit_events.e30('e30-main'::bytea,NULL,NULL,256);
    IF ids IS DISTINCT FROM expected THEN RAISE EXCEPTION 'E30 tied timestamp page order or limit differs'; END IF;
    SELECT array_agg(('e3000000-0000-0000-0000-'||lpad((n*2)::text,12,'0'))::uuid ORDER BY n) INTO expected FROM generate_series(257,260) n;
    SELECT array_agg(work_id) INTO ids FROM modkit_events.e30('e30-main'::bytea,t,'e3000000-0000-0000-0000-000000000512',256);
    IF ids IS DISTINCT FROM expected THEN RAISE EXCEPTION 'E30 continuation page differs'; END IF;
    SELECT array_agg(work_id) INTO ids FROM modkit_events.e30('e30-main'::bytea,t,'e3000000-0000-0000-0000-000000000003',1);
    IF ids IS DISTINCT FROM ARRAY['e3000000-0000-0000-0000-000000000004'::uuid] THEN
        RAISE EXCEPTION 'E30 requires an existing cursor or has wrong strict boundary'; END IF;
    IF EXISTS (SELECT 1 FROM modkit_events.e30('e30-main'::bytea,t,'e3000000-0000-0000-0000-000000000520',256)) THEN
        RAISE EXCEPTION 'E30 end cursor returned rows'; END IF;
    SELECT * INTO STRICT item FROM modkit_events.e30('jobs'::bytea,NULL,NULL,1);
    IF item.kind IS DISTINCT FROM 'inbox' OR item.namespace IS DISTINCT FROM 'jobs'::bytea THEN
        RAISE EXCEPTION 'E30 incorrectly restricts jobs namespace to job kind'; END IF;
    FOR item IN SELECT * FROM modkit_events.e30('e30-main'::bytea,NULL,NULL,256) LOOP
        IF to_jsonb(item) IS DISTINCT FROM (SELECT to_jsonb(w) FROM modkit_events.e15(item.work_id) w) THEN
            RAISE EXCEPTION 'E30 complete Work projection differs from E15'; END IF;
    END LOOP;
    BEGIN
        PERFORM * FROM modkit_events.e30('e30-broken'::bytea,NULL,NULL,1);
        RAISE EXCEPTION 'E30 silently accepted a missing subtype';
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL; END;
    FOR item IN SELECT * FROM (VALUES
        (NULL::bytea,NULL::timestamptz,NULL::uuid,1),
        (''::bytea,NULL::timestamptz,NULL::uuid,1),
        (decode('ff','hex'),NULL::timestamptz,NULL::uuid,1),
        (convert_to(repeat('a',257),'UTF8'),NULL::timestamptz,NULL::uuid,1),
        ('e30-main'::bytea,NULL::timestamptz,NULL::uuid,NULL::int4),
        ('e30-main'::bytea,NULL::timestamptz,NULL::uuid,0),
        ('e30-main'::bytea,NULL::timestamptz,NULL::uuid,257),
        ('e30-main'::bytea,t,NULL::uuid,1),
        ('e30-main'::bytea,NULL::timestamptz,'e3000000-0000-0000-0000-000000000002'::uuid,1),
        ('e30-main'::bytea,'infinity'::timestamptz,'e3000000-0000-0000-0000-000000000002'::uuid,1),
        ('e30-main'::bytea,'-infinity'::timestamptz,'e3000000-0000-0000-0000-000000000002'::uuid,1),
        ('e30-main'::bytea,'10000-01-01+00'::timestamptz,'e3000000-0000-0000-0000-000000000002'::uuid,1)
    ) AS invalid(ns,at,id,lim) LOOP
        BEGIN
            PERFORM * FROM modkit_events.e30(item.ns,item.at,item.id,item.lim);
            RAISE EXCEPTION 'E30 accepted invalid input';
        EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL; END;
    END LOOP;
    IF pg_temp.data_snapshot() IS DISTINCT FROM before_state THEN
        RAISE EXCEPTION 'E30 changed fixture rows or sequences'; END IF;
    RAISE NOTICE 'E30_BEHAVIOR_PASS: paging, ties, limit, namespace, full rows, malformed row, 12 input rejections, unchanged data';
END
$tests$;

ANALYZE modkit_events.work;
DO $plans$
DECLARE plan jsonb; query text; expected text;
BEGIN
    FOR query,expected IN SELECT * FROM (VALUES
        ($q$SELECT work_id,created_at FROM modkit_events.work WHERE namespace='e30-main'::bytea ORDER BY created_at,work_id LIMIT 1$q$,'work_namespace_created_page'),
        ($q$SELECT work_id,created_at FROM modkit_events.work WHERE namespace='e30-main'::bytea AND (created_at,work_id)>('2026-01-02 03:04:05+00'::timestamptz,'e3000000-0000-0000-0000-000000000512'::uuid) ORDER BY created_at,work_id LIMIT 1$q$,'work_namespace_created_page'),
        ($q$SELECT work_id,created_at FROM modkit_events.work WHERE namespace='jobs'::bytea AND kind COLLATE pg_catalog."C"='job' COLLATE pg_catalog."C" ORDER BY created_at,work_id LIMIT 1$q$,'work_jobs_created_page')
    ) q(statement,index_name) LOOP
        EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '||query INTO plan;
        IF position(expected in plan::text)=0 OR position('"Node Type": "Sort"' in plan::text)>0
           OR position('"Node Type": "Seq Scan"' in plan::text)>0 THEN
            RAISE EXCEPTION 'E30 discovery did not use expected bounded ordered index: %',plan; END IF;
        RAISE NOTICE 'E30_PLAN: %',plan;
    END LOOP;
END
$plans$;

DO $acl_before$
BEGIN
    IF has_function_privilege('modkit_operator','modkit_events.e30(bytea,timestamptz,uuid,integer)','EXECUTE') THEN
        RAISE EXCEPTION 'E30 grants execute before explicit installation grant'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE oid='modkit_events.e30(bytea,timestamptz,uuid,integer)'::regprocedure
        AND provolatile='s' AND prosecdef AND proconfig=ARRAY['search_path=pg_catalog, pg_temp']) THEN
        RAISE EXCEPTION 'E30 installed function properties differ'; END IF;
END
$acl_before$;
GRANT USAGE ON SCHEMA modkit_events TO modkit_operator;
SET LOCAL ROLE modkit_operator;
DO $denied$
BEGIN
    BEGIN
        PERFORM * FROM modkit_events.e30('e30-main'::bytea,NULL,NULL,1);
        RAISE EXCEPTION 'E30 unauthorized direct call succeeded';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END
$denied$;
SET LOCAL ROLE e30_owner;
GRANT EXECUTE ON FUNCTION modkit_events.e30(bytea,timestamptz,uuid,int4) TO modkit_operator;
SET LOCAL ROLE modkit_operator;
DO $allowed$
DECLARE item record;
BEGIN
    SELECT * INTO STRICT item FROM modkit_events.e30('e30-main'::bytea,NULL,NULL,1);
    IF item.work_id IS DISTINCT FROM 'e3000000-0000-0000-0000-000000000002'::uuid THEN
        RAISE EXCEPTION 'E30 operator read differs'; END IF;
    BEGIN
        PERFORM * FROM modkit_events.work;
        RAISE EXCEPTION 'E30 operator can read private storage directly';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    RAISE NOTICE 'E30_ACL_PASS: default denial, explicit function grant, private-table denial';
END
$allowed$;
RESET ROLE;
