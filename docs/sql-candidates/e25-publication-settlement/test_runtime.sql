-- E25 bounded fixture in a caller-owned READ COMMITTED transaction.
-- E02/E22/E24/E25/E28/E29 and immutable helpers only. No E10.
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

CREATE FUNCTION pg_temp.expect_error(id bytea,t uuid,r bigint,intent uuid,status text,receipt bytea,evidence bytea,expected text)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); actual text;
BEGIN
 BEGIN
  PERFORM * FROM modkit_events.e25(id,t,r,intent,status,receipt,evidence);
  RAISE EXCEPTION 'publication settlement unexpectedly accepted';
 EXCEPTION WHEN OTHERS THEN
  GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
  IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'expected %, got %',expected,actual; END IF;
 END;
 IF pg_temp.snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'rejected settlement wrote'; END IF;
END $test$;

CREATE FUNCTION pg_temp.check_settlement(id bytea,status text,receipt bytea,evidence bytea,want_state text,want_history text)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_row modkit_events.outbox%ROWTYPE; after_row modkit_events.outbox%ROWTYPE;
 h modkit_events.publication_history%ROWTYPE; returned bool; before_state jsonb; after_state jsonb;
 other_before jsonb; other_after jsonb; history_before jsonb; observed jsonb;
BEGIN
 SELECT * INTO STRICT before_row FROM modkit_events.outbox WHERE event_id=id;
 before_state:=pg_temp.snapshot();
 SELECT ok INTO STRICT returned FROM modkit_events.e25(id,before_row.token,before_row.ownership_revision,
  before_row.intent_id,status,receipt,evidence);
 SELECT * INTO STRICT after_row FROM modkit_events.outbox WHERE event_id=id;
 after_state:=pg_temp.snapshot();
 IF returned IS DISTINCT FROM TRUE OR after_row.state IS DISTINCT FROM want_state
 OR after_row.token IS NOT NULL OR after_row.lease_until IS NOT NULL
 OR after_row.ownership_revision IS DISTINCT FROM before_row.ownership_revision+1
 OR after_row.receipt IS DISTINCT FROM receipt OR after_row.outcome_evidence IS DISTINCT FROM evidence
 OR (to_jsonb(after_row)-ARRAY['state','token','lease_until','ownership_revision','receipt','outcome_evidence','updated_at'])
    IS DISTINCT FROM (to_jsonb(before_row)-ARRAY['state','token','lease_until','ownership_revision','receipt','outcome_evidence','updated_at'])
 OR after_row.updated_at>=before_row.lease_until
 OR after_row.updated_at<before_row.updated_at THEN RAISE EXCEPTION 'settlement/full postimage mismatch'; END IF;
 SELECT * INTO STRICT h FROM modkit_events.publication_history WHERE event_id=id ORDER BY history_id DESC LIMIT 1;
 IF jsonb_array_length(after_state->'publication_history')<>jsonb_array_length(before_state->'publication_history')+1
 OR h.history_id<=0 OR h.status IS DISTINCT FROM want_history OR h.intent_id IS DISTINCT FROM before_row.intent_id
 OR h.operation_id IS NOT NULL OR h.receipt IS DISTINCT FROM receipt OR h.evidence IS DISTINCT FROM evidence
 OR h.binding<>''::bytea OR h.recorded_at IS DISTINCT FROM after_row.updated_at THEN
  RAISE EXCEPTION 'settlement history mismatch'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO history_before
  FROM jsonb_array_elements(after_state->'publication_history') WHERE (value->>'history_id')::bigint<>h.history_id;
 IF history_before IS DISTINCT FROM before_state->'publication_history' THEN RAISE EXCEPTION 'prior history changed'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO other_before
  FROM jsonb_array_elements(before_state->'outbox') WHERE value->>'event_id'<>to_jsonb(before_row)->>'event_id';
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO other_after
  FROM jsonb_array_elements(after_state->'outbox') WHERE value->>'event_id'<>to_jsonb(before_row)->>'event_id';
 IF other_after IS DISTINCT FROM other_before THEN RAISE EXCEPTION 'other outbox row changed'; END IF;
 IF (after_state-ARRAY['outbox','publication_history','publication_history_history_id_seq'])
 IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']) THEN
  RAISE EXCEPTION 'settlement unrelated writes'; END IF;
 SELECT to_jsonb(o) INTO STRICT observed FROM modkit_events.e28(id) o;
 IF observed IS DISTINCT FROM to_jsonb(after_row)-'event_digest' THEN RAISE EXCEPTION 'public outbox reader mismatch'; END IF;
 SELECT to_jsonb(o) INTO STRICT observed FROM modkit_events.e29(id,h.history_id-1,1) o;
 IF observed IS DISTINCT FROM to_jsonb(h)-'event_digest' THEN RAISE EXCEPTION 'public history reader mismatch'; END IF;
 -- Same and changed outcomes cannot replay a released fence.
 PERFORM pg_temp.expect_error(id,before_row.token,before_row.ownership_revision,before_row.intent_id,status,receipt,evidence,'PZ003');
 PERFORM pg_temp.expect_error(id,before_row.token,before_row.ownership_revision,before_row.intent_id,
  CASE WHEN status='confirmed' THEN 'rejected' ELSE 'confirmed' END,receipt,evidence,'PZ003');
END $test$;

-- Lawful public chain with valid U+0000 and zero intent; no external I/O occurs.
SAVEPOINT public_chain;
DO $test$
DECLARE replay bytea:=convert_to('{"event_id":"\u0000","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8'); item record;
BEGIN
 PERFORM * FROM modkit_events.e02(decode('00','hex'),1,modkit_events._event_replay_frame(replay),replay);
 SELECT * INTO STRICT item FROM modkit_events.e22(1,30,NULL,1) WHERE record_type='item';
 PERFORM * FROM modkit_events.e24(item.event_id,item.token,item.ownership_revision,'00000000-0000-0000-0000-000000000000');
 PERFORM pg_temp.check_settlement(item.event_id,'confirmed',decode('00ff','hex'),decode('ff00','hex'),'published','publication_confirmed');
END $test$;
ROLLBACK TO SAVEPOINT public_chain;

-- Exact opaque-byte bounds and all status arms. Owner-only setup isolates E25.
SAVEPOINT outcome_cases;
SELECT pg_temp.seed('other');
DO $test$
DECLARE n int; mode int; id text; status text; want_state text; want_history text; receipt bytea; evidence bytea;
BEGIN
 FOR n IN 1..3 LOOP
  status:=(ARRAY['confirmed','rejected','uncertain'])[n];
  want_state:=(ARRAY['published','rejected','held'])[n];
  want_history:=(ARRAY['publication_confirmed','publication_rejected','publication_uncertain'])[n];
  FOR mode IN 1..3 LOOP
   id:='outcome-'||n||'-'||mode; PERFORM pg_temp.seed(id);
   UPDATE modkit_events.outbox SET state='publishing',token='00000000-0000-0000-0000-000000000000',
    ownership_revision=CASE WHEN n=1 AND mode=1 THEN 9223372036854775806 ELSE 7 END,
    lease_until=clock_timestamp()+interval '30 seconds',intent_id=gen_random_uuid(),
    receipt=decode('dead','hex'),outcome_evidence=decode('beef','hex') WHERE event_id=convert_to(id,'UTF8');
   receipt:=CASE mode WHEN 1 THEN NULL WHEN 2 THEN ''::bytea ELSE decode(repeat('ff',4096),'hex') END;
   evidence:=CASE mode WHEN 1 THEN ''::bytea WHEN 2 THEN decode('00ff','hex') ELSE decode(repeat('ab',1048576),'hex') END;
   PERFORM pg_temp.check_settlement(convert_to(id,'UTF8'),status,receipt,evidence,want_state,want_history);
  END LOOP;
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT outcome_cases;

SAVEPOINT rejection_cases;
SELECT pg_temp.seed('owned');
UPDATE modkit_events.outbox SET state='publishing',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=7,lease_until=clock_timestamp()+interval '30 seconds',
 intent_id='00000000-0000-0000-0000-000000000000' WHERE event_id=convert_to('owned','UTF8');
DO $test$
DECLARE id bytea; t uuid; rev bigint; intent uuid; status text; receipt bytea; evidence bytea; n int;
 z uuid:='00000000-0000-0000-0000-000000000000';
BEGIN
 FOR n IN 1..18 LOOP
  id:=convert_to('owned','UTF8'); t:=z; rev:=7; intent:=z;status:='confirmed';receipt:=NULL;evidence:=''::bytea;
  CASE n
   WHEN 1 THEN id:=NULL; WHEN 2 THEN id:=''::bytea; WHEN 3 THEN id:=convert_to('   ','UTF8');
   WHEN 4 THEN id:=decode('ff','hex'); WHEN 5 THEN id:=convert_to(repeat('a',257),'UTF8');
   WHEN 6 THEN t:=NULL; WHEN 7 THEN rev:=NULL; WHEN 8 THEN rev:=0; WHEN 9 THEN rev:=-1;
   WHEN 10 THEN intent:=NULL; WHEN 11 THEN status:=NULL; WHEN 12 THEN status:='Confirmed';
   WHEN 13 THEN status:='confirmed '; WHEN 14 THEN status:=''; WHEN 15 THEN status:='published';
   WHEN 16 THEN receipt:=decode(repeat('ab',4097),'hex'); WHEN 17 THEN evidence:=NULL;
   WHEN 18 THEN evidence:=decode(repeat('ab',1048577),'hex');
  END CASE;
  PERFORM pg_temp.expect_error(id,t,rev,intent,status,receipt,evidence,'PZ006');
 END LOOP;
 PERFORM pg_temp.expect_error(convert_to('missing','UTF8'),z,7,z,'confirmed',NULL,''::bytea,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),'00000000-0000-0000-0000-000000000001',7,z,'confirmed',NULL,''::bytea,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,8,z,'confirmed',NULL,''::bytea,'PZ003');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,7,'00000000-0000-0000-0000-000000000001','confirmed',NULL,''::bytea,'PZ003');
 UPDATE modkit_events.outbox SET ownership_revision=9223372036854775807 WHERE event_id=convert_to('owned','UTF8');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,9223372036854775807,z,'confirmed',NULL,''::bytea,'PZ004');
 UPDATE modkit_events.outbox SET ownership_revision=7,lease_until='2020-01-01Z' WHERE event_id=convert_to('owned','UTF8');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,7,z,'confirmed',NULL,''::bytea,'PZ003');
 UPDATE modkit_events.outbox SET state='claimed',intent_id=NULL,lease_until=clock_timestamp()+interval '30 seconds'
  WHERE event_id=convert_to('owned','UTF8');
 PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,7,z,'confirmed',NULL,''::bytea,'PZ004');
END $test$;
-- Lawful unowned states fail the fence first and are never silently reclaimed.
DO $test$
DECLARE code text; z uuid:='00000000-0000-0000-0000-000000000000';
BEGIN
 FOREACH code IN ARRAY ARRAY['pending','published','rejected','held'] LOOP
  UPDATE modkit_events.outbox SET state=code,token=NULL,lease_until=NULL,
   intent_id=CASE WHEN code='pending' THEN NULL ELSE z END WHERE event_id=convert_to('owned','UTF8');
  PERFORM pg_temp.expect_error(convert_to('owned','UTF8'),z,7,z,'uncertain',NULL,''::bytea,'PZ003');
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT rejection_cases;

-- Table-reachable semantic corruption must remain PZ012 before intent diagnosis.
SAVEPOINT corruption_cases;
SELECT pg_temp.seed('corrupt');
UPDATE modkit_events.outbox SET state='publishing',token='00000000-0000-0000-0000-000000000000',
 ownership_revision=7,lease_until=clock_timestamp()+interval '30 seconds',
 intent_id='00000000-0000-0000-0000-000000000000' WHERE event_id=convert_to('corrupt','UTF8');
DO $test$
DECLARE saved modkit_events.outbox%ROWTYPE; n int;
BEGIN
 SELECT * INTO STRICT saved FROM modkit_events.outbox WHERE event_id=convert_to('corrupt','UTF8');
 FOR n IN 1..3 LOOP
  UPDATE modkit_events.outbox SET replay_input=CASE WHEN n=1 THEN convert_to('{}','UTF8') ELSE saved.replay_input END,
   lease_until=CASE WHEN n=2 THEN 'infinity'::timestamptz ELSE saved.lease_until END,
   updated_at=CASE WHEN n=3 THEN 'infinity'::timestamptz ELSE saved.updated_at END WHERE event_id=saved.event_id;
  PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,saved.intent_id,'confirmed',NULL,''::bytea,'PZ012');
  PERFORM pg_temp.expect_error(saved.event_id,saved.token,saved.ownership_revision,
   '00000000-0000-0000-0000-000000000001','confirmed',NULL,''::bytea,'PZ012');
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT corruption_cases;
SELECT 'PUBLICATION_SETTLEMENT_RUNTIME_PASS';
