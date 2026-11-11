-- E26 bounded fixture in a caller-owned READ COMMITTED transaction.
-- Public E02/E22/E24/E26/E28/E29 plus owner-only setup; no E10.
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

CREATE FUNCTION pg_temp.expect_error(lim int,cursor_value bytea,budget int,expected text)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); actual text;
BEGIN
 BEGIN
  PERFORM * FROM modkit_events.e26(lim,cursor_value,budget);
  RAISE EXCEPTION 'publication recovery unexpectedly accepted';
 EXCEPTION WHEN OTHERS THEN
  GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
  IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'expected %, got %',expected,actual; END IF;
 END;
 IF pg_temp.snapshot() IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'rejected recovery wrote'; END IF;
END $test$;

CREATE FUNCTION pg_temp.check_recovery(lim int,cursor_value bytea,budget int,want_ids bytea[],
 want_visited int,want_cursor bytea,want_exhausted bool)
RETURNS void LANGUAGE plpgsql AS $test$
DECLARE before_state jsonb:=pg_temp.snapshot(); after_state jsonb; row_value record;
 before_row modkit_events.outbox%ROWTYPE; after_row modkit_events.outbox%ROWTYPE;
 h modkit_events.publication_history%ROWTYPE; ids bytea[]:=ARRAY[]::bytea[]; count_rows int:=0;
 old_rows jsonb; prior_history jsonb; observed jsonb;
BEGIN
 FOR row_value IN SELECT * FROM modkit_events.e26(lim,cursor_value,budget) LOOP
  count_rows:=count_rows+1;
  IF count_rows=1 THEN
   IF row_value.record_type IS DISTINCT FROM 'header' OR row_value.visited IS DISTINCT FROM want_visited
   OR row_value.next_cursor IS DISTINCT FROM want_cursor OR row_value.pass_exhausted IS DISTINCT FROM want_exhausted
   OR EXISTS(SELECT 1 FROM jsonb_each(to_jsonb(row_value)-ARRAY['record_type','visited','next_cursor','pass_exhausted'])
             WHERE value<>'null'::jsonb) THEN RAISE EXCEPTION 'recovery header mismatch'; END IF;
   CONTINUE;
  END IF;
  IF row_value.record_type IS DISTINCT FROM 'item' OR row_value.visited IS NOT NULL
  OR row_value.next_cursor IS NOT NULL OR row_value.pass_exhausted IS NOT NULL THEN
   RAISE EXCEPTION 'recovery item frame mismatch'; END IF;
  ids:=array_append(ids,row_value.event_id);
  SELECT p.* INTO STRICT before_row FROM jsonb_populate_record(NULL::modkit_events.outbox,
   (SELECT value FROM jsonb_array_elements(before_state->'outbox')
    WHERE value->>'event_id'=to_jsonb(row_value)->>'event_id')) p;
  SELECT * INTO STRICT after_row FROM modkit_events.outbox WHERE event_id=row_value.event_id;
  IF before_row.state NOT IN ('claimed','publishing') OR after_row.state IS DISTINCT FROM
    (CASE before_row.state WHEN 'claimed' THEN 'pending' ELSE 'held' END)
  OR before_row.lease_until>after_row.updated_at OR after_row.token IS NOT NULL OR after_row.lease_until IS NOT NULL
  OR after_row.ownership_revision IS DISTINCT FROM before_row.ownership_revision+1
  OR (to_jsonb(after_row)-ARRAY['state','token','lease_until','ownership_revision','updated_at'])
     IS DISTINCT FROM (to_jsonb(before_row)-ARRAY['state','token','lease_until','ownership_revision','updated_at'])
  OR (to_jsonb(row_value)-ARRAY['record_type','visited','next_cursor','pass_exhausted'])
     IS DISTINCT FROM (to_jsonb(after_row)-'event_digest') THEN RAISE EXCEPTION 'recovery full postimage mismatch'; END IF;
  SELECT * INTO STRICT h FROM modkit_events.publication_history WHERE event_id=row_value.event_id ORDER BY history_id DESC LIMIT 1;
  IF h.status IS DISTINCT FROM (CASE before_row.state WHEN 'claimed' THEN 'recover_publication_preintent' ELSE 'recover_publication_intent' END)
  OR h.intent_id IS DISTINCT FROM before_row.intent_id OR h.operation_id IS NOT NULL OR h.receipt IS NOT NULL
  OR h.evidence<>''::bytea OR h.binding<>''::bytea OR h.recorded_at IS DISTINCT FROM after_row.updated_at
  THEN RAISE EXCEPTION 'recovery history mismatch'; END IF;
  SELECT to_jsonb(o) INTO STRICT observed FROM modkit_events.e28(row_value.event_id) o;
  IF observed IS DISTINCT FROM to_jsonb(after_row)-'event_digest' THEN RAISE EXCEPTION 'outbox reader mismatch'; END IF;
  SELECT to_jsonb(o) INTO STRICT observed FROM modkit_events.e29(row_value.event_id,h.history_id-1,1) o;
  IF observed IS DISTINCT FROM to_jsonb(h)-'event_digest' THEN RAISE EXCEPTION 'history reader mismatch'; END IF;
 END LOOP;
 IF count_rows<1 OR ids IS DISTINCT FROM want_ids THEN RAISE EXCEPTION 'recovery item identities mismatch'; END IF;
 after_state:=pg_temp.snapshot();
 IF jsonb_array_length(after_state->'publication_history')<>jsonb_array_length(before_state->'publication_history')+cardinality(ids)
 THEN RAISE EXCEPTION 'recovery history count mismatch'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO prior_history
 FROM jsonb_array_elements(after_state->'publication_history')
 WHERE (value->>'history_id')::bigint<=coalesce((SELECT max((v->>'history_id')::bigint)
  FROM jsonb_array_elements(before_state->'publication_history') v),0);
 IF prior_history IS DISTINCT FROM before_state->'publication_history' THEN RAISE EXCEPTION 'prior history changed'; END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]') INTO old_rows
 FROM jsonb_array_elements(after_state->'outbox') WHERE NOT ((value->>'event_id')::bytea=ANY(ids));
 IF old_rows IS DISTINCT FROM (SELECT coalesce(jsonb_agg(value ORDER BY value::text COLLATE "C"),'[]')
 FROM jsonb_array_elements(before_state->'outbox') WHERE NOT ((value->>'event_id')::bytea=ANY(ids)))
 THEN RAISE EXCEPTION 'unselected outbox row changed'; END IF;
 IF (after_state-ARRAY['outbox','publication_history','publication_history_history_id_seq'])
 IS DISTINCT FROM (before_state-ARRAY['outbox','publication_history','publication_history_history_id_seq']) THEN
  RAISE EXCEPTION 'recovery unrelated writes'; END IF;
 IF cardinality(ids)=0 AND after_state IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'empty recovery wrote'; END IF;
END $test$;

SELECT pg_temp.check_recovery(1,NULL,1,ARRAY[]::bytea[],0,NULL,TRUE);
SELECT pg_temp.check_recovery(256,decode(repeat('ff',32),'hex'),4096,ARRAY[]::bytea[],0,decode(repeat('ff',32),'hex'),TRUE);

SAVEPOINT public_chain;
SELECT pg_temp.seed('public-preintent'),pg_temp.seed('public-intent');
DO $test$
DECLARE item record; wanted bytea[]; last_digest bytea; stale_token uuid; stale_revision bigint;
BEGIN
 FOR item IN SELECT * FROM modkit_events.e22(2,30,NULL,2) WHERE record_type='item' LOOP
  IF item.event_id=convert_to('public-intent','UTF8') THEN
   PERFORM * FROM modkit_events.e24(item.event_id,item.token,item.ownership_revision,'00000000-0000-0000-0000-000000000000');
  ELSE stale_token:=item.token;stale_revision:=item.ownership_revision; END IF;
 END LOOP;
 -- Owner setup expires lawful public claims without sleeping or clock injection.
 UPDATE modkit_events.outbox SET lease_until='2020-01-01Z';
 SELECT array_agg(event_id ORDER BY event_digest),(array_agg(event_digest ORDER BY event_digest DESC))[1] INTO wanted,last_digest FROM modkit_events.outbox;
 PERFORM pg_temp.check_recovery(2,NULL,2,wanted,2,last_digest,FALSE);
 BEGIN
  PERFORM * FROM modkit_events.e24(convert_to('public-preintent','UTF8'),stale_token,stale_revision,gen_random_uuid());
  RAISE EXCEPTION 'old claim was reusable';
 EXCEPTION WHEN SQLSTATE 'PZ003' THEN NULL; END;
 IF EXISTS(SELECT 1 FROM modkit_events.outbox WHERE event_id=convert_to('public-intent','UTF8') AND state<>'held')
 THEN RAISE EXCEPTION 'intent became retryable'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT public_chain;

SAVEPOINT matrix;
DO $test$
DECLARE n int; code text; wanted bytea[]; last_digest bytea;
BEGIN
 FOR n IN 1..10 LOOP
  PERFORM pg_temp.seed('matrix-'||n);
  code:=(ARRAY['pending','published','rejected','held','claimed','publishing','claimed','publishing','claimed','publishing'])[n];
  UPDATE modkit_events.outbox SET state=code,
   token=CASE WHEN code IN ('claimed','publishing') THEN gen_random_uuid() ELSE NULL END,
   ownership_revision=CASE WHEN n IN (9,10) THEN 9223372036854775807 WHEN n IN (7,8) THEN 9223372036854775806 ELSE 7 END,
   lease_until=CASE WHEN n IN (5,6) THEN clock_timestamp()+interval '1 hour'
                    WHEN code IN ('claimed','publishing') THEN '2020-01-01Z'::timestamptz ELSE NULL END,
   intent_id=CASE WHEN code IN ('pending','claimed') THEN NULL ELSE gen_random_uuid() END,
   receipt=decode('00ff','hex'),outcome_evidence=decode('ff00','hex')
  WHERE event_id=convert_to('matrix-'||n,'UTF8');
 END LOOP;
 SELECT array_agg(event_id ORDER BY event_digest) INTO wanted FROM modkit_events.outbox
 WHERE event_id IN (convert_to('matrix-7','UTF8'),convert_to('matrix-8','UTF8'));
 SELECT (array_agg(event_digest ORDER BY event_digest DESC))[1] INTO last_digest FROM modkit_events.outbox;
 PERFORM pg_temp.check_recovery(256,NULL,4096,wanted,10,last_digest,TRUE);
 PERFORM pg_temp.check_recovery(256,NULL,4096,ARRAY[]::bytea[],10,last_digest,TRUE);
 IF EXISTS(SELECT 1 FROM modkit_events.outbox WHERE event_id=convert_to('matrix-7','UTF8')
  AND ownership_revision<>9223372036854775807) THEN RAISE EXCEPTION 'last revision not usable'; END IF;
END $test$;
ROLLBACK TO SAVEPOINT matrix;

SAVEPOINT paging;
SELECT pg_temp.seed('page-1'),pg_temp.seed('page-2'),pg_temp.seed('page-3');
DO $test$
DECLARE ids bytea[]; cursors bytea[];
BEGIN
 SELECT array_agg(event_id ORDER BY event_digest),array_agg(event_digest ORDER BY event_digest)
 INTO ids,cursors FROM modkit_events.outbox;
 UPDATE modkit_events.outbox SET state='claimed',token=gen_random_uuid(),ownership_revision=7,lease_until='2020-01-01Z'
 WHERE event_id<>ids[1];
 PERFORM pg_temp.check_recovery(1,NULL,1,ARRAY[]::bytea[],1,cursors[1],FALSE);
 PERFORM pg_temp.check_recovery(1,cursors[1],2,ARRAY[ids[2]],1,cursors[2],FALSE);
 PERFORM pg_temp.check_recovery(1,cursors[2],1,ARRAY[ids[3]],1,cursors[3],FALSE);
 PERFORM pg_temp.check_recovery(1,cursors[3],1,ARRAY[]::bytea[],0,cursors[3],TRUE);
END $test$;
ROLLBACK TO SAVEPOINT paging;

SAVEPOINT errors;
SELECT pg_temp.seed('corrupt');
UPDATE modkit_events.outbox SET state='claimed',token=gen_random_uuid(),ownership_revision=7,lease_until='2020-01-01Z';
DO $test$
DECLARE n int; code text; lim int; cursor_value bytea; budget int; saved modkit_events.outbox%ROWTYPE;
BEGIN
 FOR n IN 1..10 LOOP
  lim:=1;cursor_value:=NULL;budget:=1;
  CASE n WHEN 1 THEN lim:=NULL;WHEN 2 THEN lim:=0;WHEN 3 THEN lim:=257;
   WHEN 4 THEN budget:=NULL;WHEN 5 THEN budget:=0;WHEN 6 THEN budget:=4097;
   WHEN 7 THEN lim:=2;WHEN 8 THEN cursor_value:=''::bytea;
   WHEN 9 THEN cursor_value:=decode(repeat('00',31),'hex');
   WHEN 10 THEN cursor_value:=decode(repeat('00',33),'hex'); END CASE;
  PERFORM pg_temp.expect_error(lim,cursor_value,budget,'PZ006');
 END LOOP;
 SELECT * INTO STRICT saved FROM modkit_events.outbox;
 FOREACH code IN ARRAY ARRAY['claimed','publishing'] LOOP
 FOR n IN 1..6 LOOP
  UPDATE modkit_events.outbox SET
   state=code,intent_id=CASE WHEN code='publishing' THEN '00000000-0000-0000-0000-000000000000'::uuid ELSE NULL END,
   replay_input=CASE WHEN n IN (1,4,5,6) THEN convert_to('{}','UTF8') ELSE saved.replay_input END,
   lease_until=CASE WHEN n=2 THEN 'infinity'::timestamptz WHEN n IN (4,6) THEN clock_timestamp()+interval '1 hour' ELSE saved.lease_until END,
   updated_at=CASE WHEN n=3 THEN 'infinity'::timestamptz ELSE saved.updated_at END,
   ownership_revision=CASE WHEN n IN (5,6) THEN 9223372036854775807 ELSE saved.ownership_revision END;
  PERFORM pg_temp.expect_error(1,NULL,1,'PZ012');
 END LOOP;
 END LOOP;
END $test$;
ROLLBACK TO SAVEPOINT errors;
SELECT 'PUBLICATION_RECOVERY_RUNTIME_PASS';
