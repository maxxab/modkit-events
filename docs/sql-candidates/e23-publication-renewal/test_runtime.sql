-- E23 bounded fixture in a fresh caller-owned READ COMMITTED transaction.
-- E02/E22/E23/E28/E29 plus immutable helpers only. No E10.
CREATE FUNCTION pg_temp.snapshot() RETURNS jsonb LANGUAGE plpgsql AS $test$
DECLARE name text; value jsonb; result jsonb:='{}';
BEGIN
 FOREACH name IN ARRAY ARRAY['schema_versions','subscriptions','work','inbox','job_payloads','attempts',
  'finalization_guards','work_history','delivery_history','outbox','publication_history','mutation_operations',
  'work_history_history_id_seq','delivery_history_history_id_seq','publication_history_history_id_seq'] LOOP
  IF name LIKE '%_seq' THEN
   EXECUTE format('SELECT jsonb_build_array(last_value,log_cnt,is_called) FROM modkit_events.%I',name) INTO value;
  ELSE
   EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text COLLATE "C"),''[]''::jsonb) FROM modkit_events.%I t',name) INTO value;
  END IF;
  result:=result||jsonb_build_object(name,value);
 END LOOP;
 RETURN result;
END $test$;
CREATE FUNCTION pg_temp.seed(id text) RETURNS void LANGUAGE plpgsql AS $test$
DECLARE replay bytea; inserted_value bool;
BEGIN
 replay:=convert_to(jsonb_build_object('event_id',id,'name','cmd','schema_version',2147483648,
  'payload','{}'::jsonb,'metadata','{}'::jsonb)::text,'UTF8');
 SELECT inserted INTO STRICT inserted_value FROM modkit_events.e02(convert_to(id,'UTF8'),1,
  modkit_events._event_replay_frame(replay),replay);
 IF inserted_value IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'duplicate fixture seed'; END IF;
END $test$;

CREATE FUNCTION pg_temp.expect_error(id bytea,t uuid,r bigint,s float8,expected text)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); actual text;
BEGIN
 BEGIN
  PERFORM * FROM modkit_events.e23(id,t,r,s);
  RAISE EXCEPTION 'renewal unexpectedly accepted';
 EXCEPTION WHEN OTHERS THEN
  GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
  IF actual IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'expected %, got %',expected,actual;
  END IF;
 END;
 IF pg_temp.snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'rejected renewal wrote'; END IF;
END $test$;

CREATE FUNCTION pg_temp.check_renew(id bytea,s float8,expected_us bigint)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_row modkit_events.outbox%ROWTYPE; after_row modkit_events.outbox%ROWTYPE;
 h modkit_events.publication_history%ROWTYPE; returned timestamptz; before_state jsonb; old_count bigint;
BEGIN
 SELECT * INTO STRICT before_row FROM modkit_events.outbox WHERE event_id=id;
 SELECT count(*) INTO old_count FROM modkit_events.publication_history WHERE event_id=id;
 before_state:=pg_temp.snapshot();
 SELECT lease_until INTO STRICT returned FROM modkit_events.e23(id,before_row.token,before_row.ownership_revision,s);
 SELECT * INTO STRICT after_row FROM modkit_events.outbox WHERE event_id=id;
 IF returned IS DISTINCT FROM after_row.lease_until
 OR after_row.lease_until IS DISTINCT FROM greatest(before_row.lease_until,after_row.updated_at+expected_us*interval '1 microsecond')
 OR (to_jsonb(after_row)-ARRAY['lease_until','updated_at'])
    IS DISTINCT FROM (to_jsonb(before_row)-ARRAY['lease_until','updated_at'])
 OR after_row.updated_at>=before_row.lease_until THEN RAISE EXCEPTION 'renewal/full postimage mismatch'; END IF;
 SELECT * INTO STRICT h FROM modkit_events.publication_history
  WHERE event_id=id ORDER BY history_id DESC LIMIT 1;
 IF (SELECT count(*) FROM modkit_events.publication_history WHERE event_id=id)<>old_count+1
 OR h.history_id<=0 OR h.status<>'renew_publication' OR h.intent_id IS DISTINCT FROM after_row.intent_id
 OR h.operation_id IS NOT NULL OR h.receipt IS NOT NULL OR h.evidence<>''::bytea OR h.binding<>''::bytea
 OR h.recorded_at IS DISTINCT FROM after_row.updated_at THEN RAISE EXCEPTION 'renewal history mismatch'; END IF;
 IF (pg_temp.snapshot()-ARRAY['outbox','publication_history','publication_history_history_id_seq'])
 IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']) THEN
  RAISE EXCEPTION 'renewal unrelated writes'; END IF;
 -- Public reader compatibility is checked in a subsequent command, not used by E23 postwrite.
 IF (SELECT count(*) FROM modkit_events.e29(id,h.history_id-1,1))<>1 THEN RAISE EXCEPTION 'history reader mismatch'; END IF;
END $test$;

-- Lawful public E02 -> E22 -> E23 with the valid NUL identifier.
SAVEPOINT public_chain;
DO $test$
DECLARE replay bytea:=convert_to('{"event_id":"\u0000","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
 item record;
BEGIN
 PERFORM * FROM modkit_events.e02(decode('00','hex'),1,modkit_events._event_replay_frame(replay),replay);
 SELECT * INTO STRICT item FROM modkit_events.e22(1,30,NULL,1) WHERE record_type='item';
 PERFORM pg_temp.check_renew(item.event_id,60,60000000);
END $test$;
ROLLBACK TO SAVEPOINT public_chain;

-- Each edge uses max(old lease, final clock+exact represented binary64 duration).
-- Tiny values retain the live old lease; larger values exercise extension.
SAVEPOINT lease_cases;
DO $test$
DECLARE duration float8; expected_us bigint; name text; n int:=0; pub bool;
BEGIN
 FOREACH pub IN ARRAY ARRAY[FALSE,TRUE] LOOP
  FOR duration,expected_us IN SELECT * FROM (VALUES
   ('5e-324'::float8,1::bigint),('0.000001'::float8,1::bigint),
   ('0.1'::float8,100001::bigint),('1.0000000000000002'::float8,1000001::bigint),
   ('3600'::float8,3600000000::bigint)) v(s,u) LOOP
   n:=n+1; name:='lease-'||n; PERFORM pg_temp.seed(name);
   UPDATE modkit_events.outbox SET state=CASE WHEN pub THEN 'publishing' ELSE 'claimed' END,
    token='00000000-0000-0000-0000-000000000000',ownership_revision=9223372036854775807,
    lease_until=clock_timestamp()+interval '1 second',intent_id=CASE WHEN pub THEN gen_random_uuid() END,
    receipt=decode('00ff','hex'),outcome_evidence=decode('ff00','hex')
    WHERE event_id=convert_to(name,'UTF8');
   PERFORM pg_temp.check_renew(convert_to(name,'UTF8'),duration,expected_us);
  END LOOP;
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT lease_cases;

-- Invalid arguments precede storage; each rejected call preserves all rows and sequence state.
SAVEPOINT rejection_cases;
SELECT pg_temp.seed('owned');
UPDATE modkit_events.outbox SET state='claimed',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=7,lease_until=clock_timestamp()+interval '30 seconds' WHERE event_id=convert_to('owned','UTF8');
DO $test$
DECLARE id bytea; t uuid; rev bigint; seconds float8; n int;
BEGIN
 FOR n IN 1..17 LOOP
  id:=convert_to('owned','UTF8');t:='00000000-0000-0000-0000-000000000000';rev:=7;seconds:=30;
  CASE n
   WHEN 1 THEN id:=NULL; WHEN 2 THEN id:=''::bytea; WHEN 3 THEN id:=convert_to('   ','UTF8');
   WHEN 4 THEN id:=decode('ff','hex'); WHEN 5 THEN id:=convert_to(repeat('a',257),'UTF8');
   WHEN 6 THEN t:=NULL; WHEN 7 THEN rev:=NULL; WHEN 8 THEN rev:=0; WHEN 9 THEN rev:=-1;
   WHEN 10 THEN seconds:=NULL; WHEN 11 THEN seconds:=0; WHEN 12 THEN seconds:=-1;
   WHEN 13 THEN seconds:='NaN'; WHEN 14 THEN seconds:='Infinity'; WHEN 15 THEN seconds:='-Infinity';
   WHEN 16 THEN seconds:=3600.0000000000005; WHEN 17 THEN seconds:='-0';
  END CASE;
  PERFORM pg_temp.expect_error(id,t,rev,seconds,'PZ006');
 END LOOP;
 PERFORM pg_temp.expect_error(convert_to('missing','UTF8'),t,rev,30,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000001',7,30,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',8,30,'PZ003');
END $test$;

-- All lawful nonowned states lose the fence first; expiry never reclaims.
DO $test$
DECLARE code text;
BEGIN
 FOREACH code IN ARRAY ARRAY['pending','published','rejected','held'] LOOP
  UPDATE modkit_events.outbox SET state=code,token=NULL,lease_until=NULL,
   intent_id=CASE WHEN code='pending' THEN NULL ELSE gen_random_uuid() END WHERE event_id=convert_to('owned','UTF8');
  PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',7,30,'PZ003');
 END LOOP;
 FOREACH code IN ARRAY ARRAY['claimed','publishing'] LOOP
  UPDATE modkit_events.outbox SET state=code,token='00000000-0000-0000-0000-000000000000',
   lease_until='2020-01-01Z',intent_id=CASE WHEN code='claimed' THEN NULL ELSE gen_random_uuid() END
   WHERE event_id=convert_to('owned','UTF8');
  PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',7,30,'PZ003');
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT rejection_cases;

-- Persisted semantic corruption: valid exact fence must not bypass E28.
SAVEPOINT corruption_cases;
SELECT pg_temp.seed('corrupt');
UPDATE modkit_events.outbox SET state='claimed',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=7,lease_until=clock_timestamp()+interval '30 seconds' WHERE event_id=convert_to('corrupt','UTF8');
DO $test$
DECLARE saved modkit_events.outbox%ROWTYPE; n int; constraint_name text;
BEGIN
 SELECT * INTO STRICT saved FROM modkit_events.outbox WHERE event_id=convert_to('corrupt','UTF8');
 FOR n IN 1..3 LOOP
  UPDATE modkit_events.outbox SET replay_input=CASE WHEN n=1 THEN convert_to('{}','UTF8') ELSE saved.replay_input END,
   lease_until=CASE WHEN n=2 THEN 'infinity'::timestamptz ELSE saved.lease_until END,
   updated_at=CASE WHEN n=3 THEN 'infinity'::timestamptz ELSE saved.updated_at END
   WHERE event_id=saved.event_id;
  PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,30,'PZ012');
 END LOOP;
 UPDATE modkit_events.outbox SET replay_input=saved.replay_input,lease_until=saved.lease_until,updated_at=saved.updated_at
  WHERE event_id=saved.event_id;
 -- Owner-only malformed state fixture; public APIs cannot create this exact-token shape.
 SELECT conname INTO STRICT constraint_name FROM pg_constraint
  WHERE conrelid='modkit_events.outbox'::regclass AND contype='c'
   AND pg_get_constraintdef(oid) LIKE '%token IS NOT NULL%';
 EXECUTE format('ALTER TABLE modkit_events.outbox DROP CONSTRAINT %I',constraint_name);
 UPDATE modkit_events.outbox SET state='pending' WHERE event_id=saved.event_id;
 PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,30,'PZ004');
END $test$;
ROLLBACK TO SAVEPOINT corruption_cases;
SELECT 'PUBLICATION_RENEWAL_RUNTIME_PASS';
