-- E24 bounded fixture in a caller-owned READ COMMITTED transaction.
-- E02/E22/E24/E28/E29 and immutable helpers only. No E10.
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

CREATE FUNCTION pg_temp.expect_error(id bytea,t uuid,r bigint,intent uuid,expected text)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); actual text;
BEGIN
 BEGIN
  PERFORM * FROM modkit_events.e24(id,t,r,intent);
  RAISE EXCEPTION 'publication intent unexpectedly accepted';
 EXCEPTION WHEN OTHERS THEN
  GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
  IF actual IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'expected %, got %',expected,actual;
  END IF;
 END;
 IF pg_temp.snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'rejected intent wrote'; END IF;
END $test$;

CREATE FUNCTION pg_temp.check_intent(id bytea,intent uuid)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_row modkit_events.outbox%ROWTYPE; after_row modkit_events.outbox%ROWTYPE;
 h modkit_events.publication_history%ROWTYPE; returned bool; before_state jsonb; after_state jsonb;
 other_before jsonb; other_after jsonb; history_before jsonb;
BEGIN
 SELECT * INTO STRICT before_row FROM modkit_events.outbox WHERE event_id=id;
 before_state:=pg_temp.snapshot();
 SELECT ok INTO STRICT returned FROM modkit_events.e24(id,before_row.token,before_row.ownership_revision,intent);
 SELECT * INTO STRICT after_row FROM modkit_events.outbox WHERE event_id=id;
 after_state:=pg_temp.snapshot();
 IF returned IS DISTINCT FROM TRUE OR after_row.state<>'publishing'
 OR after_row.intent_id IS DISTINCT FROM intent
 OR (to_jsonb(after_row)-ARRAY['state','intent_id','updated_at'])
    IS DISTINCT FROM (to_jsonb(before_row)-ARRAY['state','intent_id','updated_at'])
 OR after_row.updated_at>=before_row.lease_until
 OR after_row.updated_at<before_row.updated_at THEN RAISE EXCEPTION 'intent/full postimage mismatch'; END IF;
 SELECT * INTO STRICT h FROM modkit_events.publication_history
  WHERE event_id=id ORDER BY history_id DESC LIMIT 1;
 IF jsonb_array_length(after_state->'publication_history')<>jsonb_array_length(before_state->'publication_history')+1
 OR h.history_id<=0 OR h.status<>'publication_intent' OR h.intent_id IS DISTINCT FROM intent
 OR h.operation_id IS NOT NULL OR h.receipt IS NOT NULL OR h.evidence<>''::bytea OR h.binding<>''::bytea
 OR h.recorded_at IS DISTINCT FROM after_row.updated_at THEN RAISE EXCEPTION 'intent history mismatch'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO history_before
  FROM jsonb_array_elements(after_state->'publication_history')
  WHERE (value->>'history_id')::bigint<>h.history_id;
 IF history_before IS DISTINCT FROM before_state->'publication_history' THEN RAISE EXCEPTION 'prior history changed'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO other_before
  FROM jsonb_array_elements(before_state->'outbox')
  WHERE value->>'event_id'<>to_jsonb(before_row)->>'event_id';
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO other_after
  FROM jsonb_array_elements(after_state->'outbox')
  WHERE value->>'event_id'<>to_jsonb(before_row)->>'event_id';
 IF other_after IS DISTINCT FROM other_before THEN RAISE EXCEPTION 'other outbox row changed'; END IF;
 IF (after_state-ARRAY['outbox','publication_history','publication_history_history_id_seq'])
 IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']) THEN
  RAISE EXCEPTION 'intent unrelated writes'; END IF;
 -- Subsequent command observations; E24 itself does not use a postwrite STABLE reader.
 IF (SELECT state FROM modkit_events.e28(id)) IS DISTINCT FROM 'publishing'
 OR (SELECT count(*) FROM modkit_events.e29(id,h.history_id-1,1))<>1 THEN
  RAISE EXCEPTION 'public reader mismatch'; END IF;
END $test$;

-- Lawful public E02 -> E22 -> E24 with a valid NUL identifier.
SAVEPOINT public_chain;
DO $test$
DECLARE replay bytea:=convert_to('{"event_id":"\u0000","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
 item record;
BEGIN
 PERFORM * FROM modkit_events.e02(decode('00','hex'),1,modkit_events._event_replay_frame(replay),replay);
 SELECT * INTO STRICT item FROM modkit_events.e22(1,30,NULL,1) WHERE record_type='item';
 PERFORM pg_temp.check_intent(item.event_id,'00000000-0000-0000-0000-000000000000');
END $test$;
ROLLBACK TO SAVEPOINT public_chain;

-- Caller-supplied zero intent/token and highest revision with successor headroom.
SAVEPOINT intent_cases;
SELECT pg_temp.seed('other');
SELECT pg_temp.seed('owned');
UPDATE modkit_events.outbox SET state='claimed',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=9223372036854775806,lease_until=clock_timestamp()+interval '30 seconds',
 receipt=decode('00ff','hex'),outcome_evidence=decode('ff00','hex')
 WHERE event_id=convert_to('owned','UTF8');
SELECT pg_temp.check_intent(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000');
-- Neither same-intent nor different-intent repeat is an allowed new transition.
SELECT pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',
 9223372036854775806,'00000000-0000-0000-0000-000000000000','PZ004');
SELECT pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',
 9223372036854775806,'00000000-0000-0000-0000-000000000001','PZ004');
-- Global uniqueness is the existing native constraint, not a translated domain error.
UPDATE modkit_events.outbox SET state='claimed',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=1,lease_until=clock_timestamp()+interval '30 seconds'
 WHERE event_id=convert_to('other','UTF8');
SELECT pg_temp.expect_error(convert_to('other','UTF8'),'00000000-0000-0000-0000-000000000000',
 1,'00000000-0000-0000-0000-000000000000','23505');
ROLLBACK TO SAVEPOINT intent_cases;

SAVEPOINT rejection_cases;
SELECT pg_temp.seed('owned');
UPDATE modkit_events.outbox SET state='claimed',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=7,lease_until=clock_timestamp()+interval '30 seconds' WHERE event_id=convert_to('owned','UTF8');
DO $test$
DECLARE id bytea; t uuid; rev bigint; intent uuid; n int;
BEGIN
 FOR n IN 1..10 LOOP
  id:=convert_to('owned','UTF8');t:='00000000-0000-0000-0000-000000000000';rev:=7;
  intent:='00000000-0000-0000-0000-000000000000';
  CASE n
   WHEN 1 THEN id:=NULL; WHEN 2 THEN id:=''::bytea; WHEN 3 THEN id:=convert_to('   ','UTF8');
   WHEN 4 THEN id:=decode('ff','hex'); WHEN 5 THEN id:=convert_to(repeat('a',257),'UTF8');
   WHEN 6 THEN t:=NULL; WHEN 7 THEN rev:=NULL; WHEN 8 THEN rev:=0; WHEN 9 THEN rev:=-1;
   WHEN 10 THEN intent:=NULL;
  END CASE;
  PERFORM pg_temp.expect_error(id,t,rev,intent,'PZ006');
 END LOOP;
 intent:='00000000-0000-0000-0000-000000000000';
 PERFORM pg_temp.expect_error(convert_to('missing','UTF8'),t,rev,intent,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000001',7,intent,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',8,intent,'PZ003');
 UPDATE modkit_events.outbox SET ownership_revision=9223372036854775807 WHERE event_id=convert_to('owned','UTF8');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),t,9223372036854775807,intent,'PZ004');
 UPDATE modkit_events.outbox SET ownership_revision=7,lease_until='2020-01-01Z' WHERE event_id=convert_to('owned','UTF8');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),t,7,intent,'PZ003');
END $test$;
-- Lawful nonowned states fail the fence first, never silently reclaimed.
DO $test$
DECLARE code text;
BEGIN
 FOREACH code IN ARRAY ARRAY['pending','published','rejected','held'] LOOP
  UPDATE modkit_events.outbox SET state=code,token=NULL,lease_until=NULL,
   intent_id=CASE WHEN code='pending' THEN NULL ELSE gen_random_uuid() END WHERE event_id=convert_to('owned','UTF8');
  PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000000',7,
   '00000000-0000-0000-0000-000000000000','PZ003');
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT rejection_cases;

-- Owner-only malformed fixtures cannot be generated by public operations.
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
  PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,
   '00000000-0000-0000-0000-000000000000','PZ012');
 END LOOP;
 UPDATE modkit_events.outbox SET replay_input=saved.replay_input,lease_until=saved.lease_until,updated_at=saved.updated_at
  WHERE event_id=saved.event_id;
 SELECT conname INTO STRICT constraint_name FROM pg_constraint
  WHERE conrelid='modkit_events.outbox'::regclass AND contype='c'
   AND pg_get_constraintdef(oid) LIKE '%token IS NOT NULL%';
 EXECUTE format('ALTER TABLE modkit_events.outbox DROP CONSTRAINT %I',constraint_name);
 UPDATE modkit_events.outbox SET state='pending' WHERE event_id=saved.event_id;
 PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,
  '00000000-0000-0000-0000-000000000000','PZ004');
END $test$;
ROLLBACK TO SAVEPOINT corruption_cases;
SELECT 'PUBLICATION_INTENT_RUNTIME_PASS';
