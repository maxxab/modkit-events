
-- Inert fixture: caller owns a fresh disposable READ COMMITTED transaction.
-- Direct structural seeds avoid E02/E10 and make no lifecycle/publication claim.
INSERT INTO modkit_events.outbox
(event_id,canonical_version,envelope_evidence,replay_input,state,ownership_revision,created_at,updated_at)
SELECT id,1,'x'::bytea,'x'::bytea,'pending',0,'2026-01-01Z','2026-01-01Z'
FROM (VALUES ('publication-main'::bytea),('publication-other'::bytea),
             (convert_to(repeat('é',128),'UTF8'))) AS ids(id);

INSERT INTO modkit_events.publication_history
(history_id,event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
OVERRIDING SYSTEM VALUE
SELECT n*2,'publication-main'::bytea,
       CASE WHEN code NOT IN ('enqueue','claim_publication','recover_publication_preintent')
                      AND n%12<>3 THEN '00000000-0000-0000-0000-000000000000'::uuid END,
       CASE WHEN code IN ('repair_published','repair_rejected')
            THEN '00000000-0000-0000-0000-000000000000'::uuid END,
       code,
       CASE WHEN code IN ('publication_confirmed','publication_rejected','publication_uncertain','repair_published','repair_rejected')
                      AND n%2=0 THEN decode(repeat('ab',4096),'hex') END,
       CASE WHEN code IN ('publication_confirmed','publication_rejected','publication_uncertain','repair_published','repair_rejected')
            THEN 'evidence'::bytea ELSE ''::bytea END,
       CASE WHEN code IN ('repair_published','repair_rejected') THEN 'binding'::bytea ELSE ''::bytea END,
       '2026-01-01Z'::timestamptz + n*interval '1 microsecond'
FROM generate_series(1,260) AS generated(n)
CROSS JOIN LATERAL (
 SELECT (ARRAY['enqueue','claim_publication','renew_publication','renew_publication',
               'publication_intent','publication_confirmed','publication_rejected',
               'publication_uncertain','recover_publication_preintent',
               'recover_publication_intent','repair_published','repair_rejected'])[((n-1)%12)+1] AS code
) AS statuses;
INSERT INTO modkit_events.publication_history
(history_id,event_id,status,evidence,binding,recorded_at) OVERRIDING SYSTEM VALUE VALUES
(1,'publication-other','enqueue','','','2026-01-01Z'),
(700,convert_to(repeat('é',128),'UTF8'),'enqueue','','','2026-01-01Z');

CREATE TEMP TABLE publication_before AS SELECT
    (SELECT jsonb_agg(to_jsonb(h) ORDER BY h.history_id) FROM modkit_events.publication_history h) AS rows,
    (SELECT jsonb_agg(to_jsonb(o) ORDER BY o.event_digest) FROM modkit_events.outbox o) AS parents,
    (SELECT jsonb_build_array(s.last_value,s.log_cnt,s.is_called) FROM modkit_events.publication_history_history_id_seq s) AS sequence_state;

DO $pages$
DECLARE ids bigint[]; rejected bool; query text; rejection_count int:=0;
BEGIN
 SELECT array_agg(r.history_id ORDER BY r.history_id) INTO ids FROM modkit_events.e29('publication-main',0,256) r;
 IF ids IS DISTINCT FROM ARRAY(SELECT n*2::bigint FROM generate_series(1,256) g(n)) THEN
   RAISE EXCEPTION 'maximum page mismatch'; END IF;
 SELECT array_agg(r.history_id ORDER BY r.history_id) INTO ids FROM modkit_events.e29('publication-main',512,256) r;
 IF ids IS DISTINCT FROM ARRAY[514,516,518,520]::bigint[] THEN RAISE EXCEPTION 'continuation mismatch'; END IF;
 IF (SELECT history_id FROM modkit_events.e29('publication-main',0,1))<>2
    OR (SELECT history_id FROM modkit_events.e29('publication-main',3,1))<>4
    OR EXISTS(SELECT 1 FROM modkit_events.e29('publication-main',520,256))
    OR EXISTS(SELECT 1 FROM modkit_events.e29('publication-main',9223372036854775807,1))
    OR EXISTS(SELECT 1 FROM modkit_events.e29('missing',0,256))
    OR EXISTS(SELECT 1 FROM modkit_events.e29(decode('00','hex'),0,1))
    OR (SELECT history_id FROM modkit_events.e29('publication-other',0,256))<>1
    OR (SELECT history_id FROM modkit_events.e29(convert_to(repeat('é',128),'UTF8'),0,1))<>700
 THEN RAISE EXCEPTION 'keyset/event boundary mismatch'; END IF;
 IF EXISTS(
   (SELECT * FROM modkit_events.e29('publication-main',0,256)
    EXCEPT SELECT history_id,event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at
     FROM modkit_events.publication_history WHERE event_id='publication-main' AND history_id<=512)
   UNION ALL
   (SELECT history_id,event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at
     FROM modkit_events.publication_history WHERE event_id='publication-main' AND history_id<=512
    EXCEPT SELECT * FROM modkit_events.e29('publication-main',0,256))
 ) THEN RAISE EXCEPTION 'full projection mismatch'; END IF;
 FOREACH query IN ARRAY ARRAY[
   'SELECT * FROM modkit_events.e29(NULL,0,1)',
   'SELECT * FROM modkit_events.e29(''''::bytea,0,1)',
   'SELECT * FROM modkit_events.e29('' ''::bytea,0,1)',
   'SELECT * FROM modkit_events.e29(decode(''ff'',''hex''),0,1)',
   'SELECT * FROM modkit_events.e29(decode(''c080'',''hex''),0,1)',
   'SELECT * FROM modkit_events.e29(convert_to(repeat(''é'',129),''UTF8''),0,1)',
   'SELECT * FROM modkit_events.e29(''publication-main'',NULL,1)',
   'SELECT * FROM modkit_events.e29(''publication-main'',-1,1)',
   'SELECT * FROM modkit_events.e29(''publication-main'',0,NULL)',
   'SELECT * FROM modkit_events.e29(''publication-main'',0,0)',
   'SELECT * FROM modkit_events.e29(''publication-main'',0,-1)',
   'SELECT * FROM modkit_events.e29(''publication-main'',0,257)'
 ] LOOP
   rejected:=FALSE;
   BEGIN EXECUTE query; EXCEPTION WHEN SQLSTATE 'PZ006' THEN rejected:=TRUE; END;
   IF NOT rejected THEN RAISE EXCEPTION 'invalid argument accepted: %',query; END IF;
   rejection_count:=rejection_count+1;
 END LOOP;
 IF rejection_count<>12 THEN RAISE EXCEPTION 'invalid-input count'; END IF;
 IF EXISTS(
   SELECT 1 FROM publication_before b
   WHERE b.rows IS DISTINCT FROM (SELECT jsonb_agg(to_jsonb(h) ORDER BY h.history_id) FROM modkit_events.publication_history h)
      OR b.parents IS DISTINCT FROM (SELECT jsonb_agg(to_jsonb(o) ORDER BY o.event_digest) FROM modkit_events.outbox o)
      OR b.sequence_state IS DISTINCT FROM (SELECT jsonb_build_array(s.last_value,s.log_cnt,s.is_called) FROM modkit_events.publication_history_history_id_seq s)
 ) THEN RAISE EXCEPTION 'reader mutated storage'; END IF;
END
$pages$;

-- Deliberate damaged-storage simulation, confined to this rollback transaction.
ALTER TABLE modkit_events.publication_history
 DROP CONSTRAINT publication_code_shape,
 DROP CONSTRAINT publication_binding_origin,
 DROP CONSTRAINT publication_evidence_origin,
 DROP CONSTRAINT publication_history_time_supported,
 DROP CONSTRAINT publication_history_receipt_check,
 DROP CONSTRAINT publication_history_evidence_check,
 DROP CONSTRAINT publication_history_binding_check,
 ALTER COLUMN status DROP NOT NULL,
 ALTER COLUMN evidence DROP NOT NULL,
 ALTER COLUMN binding DROP NOT NULL,
 ALTER COLUMN recorded_at DROP NOT NULL;

DO $corruption$
DECLARE bad modkit_events.publication_history%ROWTYPE; rejected bool; scenario int;
BEGIN
 FOR scenario IN 1..19 LOOP
   SELECT * INTO bad FROM modkit_events.publication_history WHERE history_id=2;
   bad.history_id:=900;
   CASE scenario
     WHEN 1 THEN bad.status:='unknown';
     WHEN 2 THEN bad.status:=NULL;
     WHEN 3 THEN bad.intent_id:='00000000-0000-0000-0000-000000000000';
     WHEN 4 THEN bad.operation_id:='00000000-0000-0000-0000-000000000000';
     WHEN 5 THEN bad.receipt:=''::bytea;
     WHEN 6 THEN bad.evidence:='x'::bytea;
     WHEN 7 THEN bad.binding:='x'::bytea;
     WHEN 8 THEN bad.recorded_at:='infinity';
     WHEN 9 THEN bad.recorded_at:=NULL;
     WHEN 10 THEN bad.evidence:=NULL;
     WHEN 11 THEN bad.binding:=NULL;
     WHEN 12 THEN bad.status:='publication_confirmed'; bad.intent_id:='00000000-0000-0000-0000-000000000000';
                  bad.evidence:=decode(repeat('ab',1048577),'hex');
     WHEN 13 THEN bad.status:='publication_confirmed'; bad.intent_id:='00000000-0000-0000-0000-000000000000';
                  bad.receipt:=decode(repeat('ab',4097),'hex');
     WHEN 14 THEN bad.status:='publication_confirmed';
     WHEN 15 THEN bad.status:='repair_published'; bad.intent_id:='00000000-0000-0000-0000-000000000000';
     WHEN 16 THEN bad.status:='renew_publication'; bad.operation_id:='00000000-0000-0000-0000-000000000000';
     WHEN 17 THEN bad.status:='renew_publication'; bad.receipt:=''::bytea;
     WHEN 18 THEN bad.status:='repair_rejected'; bad.intent_id:='00000000-0000-0000-0000-000000000000';
                  bad.operation_id:='00000000-0000-0000-0000-000000000000';
                  bad.binding:=decode(repeat('ab',1048577),'hex');
     WHEN 19 THEN bad.status:='ENQUEUE';
   END CASE;
   BEGIN
     INSERT INTO modkit_events.publication_history
     (history_id,event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
     OVERRIDING SYSTEM VALUE VALUES
     (bad.history_id,bad.event_id,bad.intent_id,bad.operation_id,bad.status,bad.receipt,bad.evidence,bad.binding,bad.recorded_at);
     IF (SELECT count(*) FROM modkit_events.e29('publication-main',0,256))<>256 THEN
       RAISE EXCEPTION 'later corruption affected bounded page'; END IF;
     rejected:=FALSE;
     BEGIN PERFORM * FROM modkit_events.e29('publication-main',512,256);
       EXCEPTION WHEN SQLSTATE 'PZ012' THEN rejected:=TRUE; END;
     IF NOT rejected THEN RAISE EXCEPTION 'selected corruption accepted: %',scenario; END IF;
     RAISE EXCEPTION USING ERRCODE='PZ099',MESSAGE='rollback one poison row';
   EXCEPTION WHEN SQLSTATE 'PZ099' THEN NULL;
   END;
 END LOOP;
END
$corruption$;

-- Actual hash collisions are not simulated. Tampered stored digest tests PZ012
-- before the otherwise different-full-ID conflict; the PZ002 branch is source-only.
ALTER TABLE modkit_events.publication_history ALTER COLUMN event_digest DROP EXPRESSION;
INSERT INTO modkit_events.publication_history
(history_id,event_id,event_digest,status,evidence,binding,recorded_at) OVERRIDING SYSTEM VALUE
VALUES(900,'publication-other',sha256('publication-main'::bytea),'enqueue','','','2026-01-01Z');
DO $digest$
DECLARE rejected bool:=FALSE;
BEGIN
 IF (SELECT count(*) FROM modkit_events.e29('publication-main',0,256))<>256 THEN
   RAISE EXCEPTION 'later alias affected bounded page'; END IF;
 BEGIN PERFORM * FROM modkit_events.e29('publication-main',512,256);
   EXCEPTION WHEN SQLSTATE 'PZ012' THEN rejected:=TRUE; END;
 IF NOT rejected THEN RAISE EXCEPTION 'malformed stored digest was not rejected first'; END IF;
END
$digest$;
SELECT 'PUBLICATION_HISTORY_RUNTIME_PASS';
