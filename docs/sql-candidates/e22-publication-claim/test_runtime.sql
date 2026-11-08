-- Fresh E22 fixture, within caller READ COMMITTED transaction. No E10.
-- Snapshot explicit sequence scalars: sequences have no composite row type.
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
CREATE FUNCTION pg_temp.page(l int,s float8,a bytea,b int) RETURNS jsonb LANGUAGE sql AS $test$
 SELECT jsonb_agg(to_jsonb(t)-'ordinality' ORDER BY ordinality)
 FROM modkit_events.e22(l,s,a,b) WITH ORDINALITY t
$test$;

-- Empty scans retain the supplied cursor and report actual end.
DO $test$
DECLARE page jsonb; before_state jsonb:=pg_temp.snapshot(); cursor bytea:=decode(repeat('ab',32),'hex');
BEGIN
 page:=pg_temp.page(1,30,NULL,1);
 IF jsonb_array_length(page)<>1 OR page->0->>'record_type'<>'header'
 OR (page->0->>'visited')::int<>0 OR page->0->'next_cursor'<>'null'::jsonb
 OR (page->0->>'pass_exhausted')::bool IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'empty header'; END IF;
 IF (page->0)-ARRAY['record_type','visited','next_cursor','pass_exhausted']
 <>jsonb_build_object('event_id',NULL,'canonical_version',NULL,'envelope_evidence',NULL,'replay_input',NULL,
 'state',NULL,'token',NULL,'ownership_revision',NULL,'lease_until',NULL,'intent_id',NULL,'receipt',NULL,
 'outcome_evidence',NULL,'created_at',NULL,'updated_at',NULL) THEN RAISE EXCEPTION 'header payload not null'; END IF;
 page:=pg_temp.page(256,3600,cursor,4096);
 IF (page->0->>'next_cursor')::bytea<>cursor OR (page->0->>'visited')::int<>0
 OR NOT (page->0->>'pass_exhausted')::bool THEN RAISE EXCEPTION 'empty continuation'; END IF;
 IF pg_temp.snapshot()<>before_state THEN RAISE EXCEPTION 'empty scan wrote'; END IF;
END $test$;


SAVEPOINT nul_identifier;
DO $test$
DECLARE replay bytea:=convert_to('{"event_id":"\u0000","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8'); page jsonb;
BEGIN
 PERFORM * FROM modkit_events.e02(decode('00','hex'),1,modkit_events._event_replay_frame(replay),replay);
 page:=pg_temp.page(1,30,NULL,1);
 IF jsonb_array_length(page)<>2 OR (page->1->>'event_id')::bytea<>decode('00','hex') THEN RAISE EXCEPTION 'valid NUL identifier'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT nul_identifier;

-- Exact binary64 durations. Each scenario rolls back rows, not sequence values.
SAVEPOINT lease_cases;
DO $test$
DECLARE duration float8; expected_us bigint; page jsonb; before_row modkit_events.outbox%ROWTYPE;
 claimed modkit_events.outbox%ROWTYPE; h modkit_events.publication_history%ROWTYPE;
 before_state jsonb; id text; n int:=0;
BEGIN
 FOR duration,expected_us IN SELECT * FROM (VALUES
  ('5e-324'::float8,1::bigint),('0.000001'::float8,1::bigint),
  ('0.1'::float8,100001::bigint),('1.0000000000000002'::float8,1000001::bigint),
  ('3600'::float8,3600000000::bigint)) v(s,u) LOOP
  n:=n+1; id:='lease-'||n; PERFORM pg_temp.seed(id);
  SELECT * INTO STRICT before_row FROM modkit_events.outbox WHERE event_id=convert_to(id,'UTF8');
  before_state:=pg_temp.snapshot();
  page:=pg_temp.page(1,duration,NULL,4096);
  IF jsonb_array_length(page)<>2 OR page->1->>'record_type'<>'item'
  OR page->1->'visited'<>'null'::jsonb OR page->1->'next_cursor'<>'null'::jsonb
  OR page->1->'pass_exhausted'<>'null'::jsonb OR (page->0->>'pass_exhausted')::bool THEN
   RAISE EXCEPTION 'lease page shape'; END IF;
  SELECT * INTO STRICT claimed FROM modkit_events.outbox WHERE event_id=before_row.event_id;
  IF claimed.state<>'claimed' OR claimed.token IS NULL OR claimed.ownership_revision<>1
  OR claimed.lease_until-claimed.updated_at<>expected_us*interval '1 microsecond'
  OR (to_jsonb(claimed)-ARRAY['state','token','ownership_revision','lease_until','updated_at'])
    IS DISTINCT FROM (to_jsonb(before_row)-ARRAY['state','token','ownership_revision','lease_until','updated_at'])
  OR ((page->1)-ARRAY['record_type','visited','next_cursor','pass_exhausted'])
    IS DISTINCT FROM (to_jsonb(claimed)-'event_digest') THEN RAISE EXCEPTION 'lease/full postimage'; END IF;
  SELECT * INTO STRICT h FROM modkit_events.publication_history WHERE event_id=before_row.event_id AND status='claim_publication';
  IF h.history_id<=0 OR h.intent_id IS NOT NULL OR h.operation_id IS NOT NULL OR h.receipt IS NOT NULL
  OR h.evidence<>''::bytea OR h.binding<>''::bytea OR h.recorded_at<>claimed.updated_at THEN
   RAISE EXCEPTION 'claim history'; END IF;
  IF (pg_temp.snapshot()-ARRAY['outbox','publication_history','publication_history_history_id_seq'])
    IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']) THEN
   RAISE EXCEPTION 'claim unrelated writes'; END IF;
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT lease_cases;

-- Raw ordered scans count terminal, expired-owned and exhausted-revision rows.
SAVEPOINT page_cases;
SELECT pg_temp.seed('page-'||i) FROM generate_series(1,8) i;
CREATE TEMP TABLE ordered AS SELECT row_number() OVER(ORDER BY event_digest) n,event_id,event_digest FROM modkit_events.outbox;
UPDATE modkit_events.outbox o SET
 state=CASE k.n WHEN 1 THEN 'published' WHEN 2 THEN 'claimed' WHEN 3 THEN 'publishing' WHEN 4 THEN 'held' WHEN 5 THEN 'rejected' ELSE 'pending' END,
 token=CASE WHEN k.n IN(2,3) THEN '00000000-0000-0000-0000-000000000000'::uuid END,
 lease_until=CASE WHEN k.n IN(2,3) THEN '2020-01-01Z'::timestamptz END,
 intent_id=CASE WHEN k.n IN(1,3,4,5) THEN gen_random_uuid() END,
 ownership_revision=CASE WHEN k.n=6 THEN 9223372036854775806 WHEN k.n=7 THEN 5 ELSE 1 END,
 receipt=CASE WHEN k.n=7 THEN '\x00'::bytea END,
 outcome_evidence=CASE WHEN k.n=7 THEN '\xff'::bytea END
 FROM ordered k WHERE o.event_digest=k.event_digest;
DO $test$
DECLARE page jsonb; cursor bytea; expected_id bytea; before_state jsonb; candidate modkit_events.outbox%ROWTYPE;
BEGIN
 SELECT * INTO STRICT candidate FROM modkit_events.outbox WHERE event_id=(SELECT event_id FROM ordered WHERE n=7);
 page:=pg_temp.page(1,30,NULL,8);
 SELECT event_digest,event_id INTO cursor,expected_id FROM ordered WHERE n=7;
 IF jsonb_array_length(page)<>2 OR (page->0->>'visited')::int<>7
 OR (page->0->>'next_cursor')::bytea<>cursor OR (page->0->>'pass_exhausted')::bool
 OR (page->1->>'event_id')::bytea<>expected_id OR (page->1->>'ownership_revision')::bigint<>6
 OR (page->1->>'receipt')::bytea<>candidate.receipt
 OR (page->1->>'outcome_evidence')::bytea<>candidate.outcome_evidence THEN RAISE EXCEPTION 'first ordered page'; END IF;
 page:=pg_temp.page(2,30,cursor,8);
 SELECT event_digest,event_id INTO cursor,expected_id FROM ordered WHERE n=8;
 IF jsonb_array_length(page)<>2 OR (page->0->>'visited')::int<>1
 OR (page->0->>'next_cursor')::bytea<>cursor OR NOT (page->0->>'pass_exhausted')::bool
 OR (page->1->>'event_id')::bytea<>expected_id THEN RAISE EXCEPTION 'continuation page'; END IF;
 before_state:=pg_temp.snapshot();
 page:=pg_temp.page(2,30,NULL,8);
 IF jsonb_array_length(page)<>1 OR (page->0->>'visited')::int<>8
 OR (page->0->>'pass_exhausted')::bool THEN RAISE EXCEPTION 'budget exhausted scan'; END IF;
 page:=pg_temp.page(2,30,cursor,8);
 IF jsonb_array_length(page)<>1 OR (page->0->>'visited')::int<>0
 OR NOT (page->0->>'pass_exhausted')::bool OR (page->0->>'next_cursor')::bytea<>cursor THEN RAISE EXCEPTION 'end scan'; END IF;
 IF pg_temp.snapshot()<>before_state THEN RAISE EXCEPTION 'no-eligible scan wrote or reclaimed'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT page_cases;

-- Invalid inputs fail before relations/time/history sequence allocations.
SELECT pg_temp.seed('invalid-input');
DO $test$
DECLARE l int; s float8; a bytea; b int; before_state jsonb:=pg_temp.snapshot();
BEGIN
 FOR l,s,a,b IN SELECT * FROM (VALUES
 (NULL::int,30::float8,NULL::bytea,1),(0,30,NULL,1),(257,30,NULL,4096),
 (1,NULL,NULL,1),(1,0,NULL,1),(1,-1,NULL,1),(1,'NaN',NULL,1),(1,'Infinity',NULL,1),
 (1,3600.0001,NULL,1),(1,30,''::bytea,1),(1,30,decode(repeat('ab',31),'hex'),1),
 (1,30,decode(repeat('ab',33),'hex'),1),(1,30,NULL,NULL),(1,30,NULL,0),
 (1,30,NULL,4097),(2,30,NULL,1)) v(l,s,a,b) LOOP
  BEGIN
   PERFORM * FROM modkit_events.e22(l,s,a,b);
   RAISE EXCEPTION 'invalid arguments accepted';
  EXCEPTION WHEN SQLSTATE 'PZ006' THEN NULL; END;
  IF pg_temp.snapshot()<>before_state THEN RAISE EXCEPTION 'invalid arguments changed footprint'; END IF;
 END LOOP;
END $test$;

-- Corruption on the first pending candidate fails before any claim allocation.
DO $test$
DECLARE original modkit_events.outbox%ROWTYPE; before_state jsonb; k int;
BEGIN
 SELECT * INTO STRICT original FROM modkit_events.outbox;
 FOR k IN 1..3 LOOP
  UPDATE modkit_events.outbox SET replay_input=CASE WHEN k=1 THEN 'x'::bytea ELSE original.replay_input END,
   envelope_evidence=CASE WHEN k=2 THEN 'x'::bytea ELSE original.envelope_evidence END,
   updated_at=CASE WHEN k=3 THEN 'infinity'::timestamptz ELSE original.updated_at END;
  before_state:=pg_temp.snapshot();
  BEGIN
   PERFORM * FROM modkit_events.e22(1,30,NULL,1);
   RAISE EXCEPTION 'corrupt pending row accepted';
  EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL; END;
  IF pg_temp.snapshot()<>before_state THEN RAISE EXCEPTION 'first corruption allocated/wrote'; END IF;
 END LOOP;
 UPDATE modkit_events.outbox SET replay_input=original.replay_input,envelope_evidence=original.envelope_evidence,updated_at=original.updated_at;
END $test$;


-- Invalid stored identifier is owner-injected corruption, not caller PZ006.
-- Relax only the identifier CHECK in this rollback-bounded fixture.
SAVEPOINT invalid_stored_id;
DO $test$
DECLARE constraint_name text;
BEGIN
 SELECT conname INTO STRICT constraint_name FROM pg_constraint
 WHERE conrelid='modkit_events.outbox'::regclass AND contype='c'
 AND pg_get_constraintdef(oid) LIKE '%_utf8_valid(event_id%';
 EXECUTE format('ALTER TABLE modkit_events.outbox DROP CONSTRAINT %I',constraint_name);
END $test$;
INSERT INTO modkit_events.outbox(event_id,canonical_version,envelope_evidence,replay_input,state,ownership_revision,created_at,updated_at)
 VALUES(decode('c080','hex'),1,'x'::bytea,'x'::bytea,'pending',0,clock_timestamp(),clock_timestamp());
DO $test$
DECLARE before_state jsonb;
BEGIN
 -- The test scans only this row by marking the valid row nonpending.
 UPDATE modkit_events.outbox SET state='claimed',token=gen_random_uuid(),ownership_revision=1,lease_until=clock_timestamp()
 WHERE event_id=convert_to('invalid-input','UTF8');
 before_state:=pg_temp.snapshot();
 BEGIN
  PERFORM * FROM modkit_events.e22(1,30,NULL,4096);
  RAISE EXCEPTION 'malformed stored identifier accepted';
 EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL; END;
 IF pg_temp.snapshot()<>before_state THEN RAISE EXCEPTION 'malformed identifier changed footprint'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT invalid_stored_id;

-- Late corruption rolls back transactional claims/history, but sequence gaps
-- legitimately survive. Do not confuse no persisted mutation with no attempt.
SAVEPOINT late_corruption;
SELECT pg_temp.seed('late-corruption');
UPDATE modkit_events.outbox SET replay_input='x'::bytea
 WHERE event_digest=(SELECT event_digest FROM modkit_events.outbox ORDER BY event_digest DESC LIMIT 1);
DO $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); after_state jsonb; old_sequence bigint;
BEGIN
 SELECT last_value INTO old_sequence FROM modkit_events.publication_history_history_id_seq;
 BEGIN
  PERFORM * FROM modkit_events.e22(2,30,NULL,2);
  RAISE EXCEPTION 'late corruption accepted';
 EXCEPTION WHEN SQLSTATE 'PZ012' THEN NULL; END;
 after_state:=pg_temp.snapshot();
 IF (after_state-'publication_history_history_id_seq')<>(before_state-'publication_history_history_id_seq')
 OR (SELECT last_value FROM modkit_events.publication_history_history_id_seq)<=old_sequence THEN
  RAISE EXCEPTION 'late failure rollback or legal sequence gap differs'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT late_corruption;

-- Upper item bound and short final page, with no terminal-state filtering.
SAVEPOINT upper_bound;
SELECT pg_temp.seed('upper-'||i) FROM generate_series(1,257) i;
DO $test$
DECLARE page jsonb; cursor bytea;
BEGIN
 page:=pg_temp.page(256,30,NULL,4096);
 cursor:=(page->0->>'next_cursor')::bytea;
 IF jsonb_array_length(page)<>257 OR (page->0->>'visited')::int<>256
 OR (page->0->>'pass_exhausted')::bool THEN RAISE EXCEPTION 'upper item bound'; END IF;
 page:=pg_temp.page(256,30,cursor,4096);
 IF jsonb_array_length(page)<>3 OR (page->0->>'visited')::int<>2
 OR NOT (page->0->>'pass_exhausted')::bool THEN RAISE EXCEPTION 'upper continuation'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT upper_bound;
SELECT 'PUBLICATION_CLAIM_RUNTIME_PASS';
