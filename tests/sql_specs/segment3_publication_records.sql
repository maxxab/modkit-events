-- NOT_RUN. Owner-only structural fixture, caller-owned disposable transaction.
DO $test$
DECLARE e pg_catalog.bytea := 'segment3_event'::pg_catalog.bytea;
    o pg_catalog.uuid := '30000000-0000-0000-0000-000000000005'::pg_catalog.uuid;
    d pg_catalog.uuid := '30000000-0000-0000-0000-000000000006'::pg_catalog.uuid;
    r pg_catalog.record; accepted pg_catalog.bool; h pg_catalog.int8;
BEGIN
    INSERT INTO modkit_events.outbox(event_id,canonical_version,envelope_evidence,replay_input,state,ownership_revision,created_at,updated_at)
      VALUES(e,1,'x'::pg_catalog.bytea,'x'::pg_catalog.bytea,'pending',0,'2030-01-01 00:00:00+00','2030-01-01 00:00:00+00');
    INSERT INTO modkit_events.mutation_operations(operation_id,operation_kind,event_id,expected_revision,requested_outcome,requested_receipt,evidence,binding,resulting_revision,recorded_at)
      VALUES(o,'repair_publication',e,2,'published',''::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,3,'2030-01-01 00:00:00+00');
    FOR r IN SELECT * FROM (VALUES
      ('enqueue',NULL::pg_catalog.uuid,NULL::pg_catalog.uuid,NULL::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,TRUE),
      ('renew_publication',NULL,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,TRUE),
      ('renew_publication',d,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,TRUE),
      ('publication_confirmed',d,NULL,NULL,'audit'::pg_catalog.bytea,''::pg_catalog.bytea,TRUE),
      ('repair_published',d,o,''::pg_catalog.bytea,'audit'::pg_catalog.bytea,'bind'::pg_catalog.bytea,TRUE),
      ('enqueue',d,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('publication_intent',NULL,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('publication_confirmed',d,o,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('repair_rejected',d,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('claim_publication',NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('recover_publication_intent',d,NULL,NULL,'audit'::pg_catalog.bytea,''::pg_catalog.bytea,FALSE),
      ('renew_publication',d,NULL,NULL,''::pg_catalog.bytea,'bind'::pg_catalog.bytea,FALSE),
      ('not_a_protocol_code',NULL,NULL,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,FALSE)
    ) AS cases(status,intent,operation,receipt,evidence,binding,valid) LOOP
      accepted := TRUE;
      BEGIN
        INSERT INTO modkit_events.publication_history(event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
          VALUES(e,r.intent,r.operation,r.status,r.receipt,r.evidence,r.binding,'2030-01-01 00:00:00+00') RETURNING history_id INTO h;
      EXCEPTION WHEN check_violation THEN accepted := FALSE; END;
      IF accepted IS DISTINCT FROM r.valid THEN RAISE EXCEPTION 'publication code/nullable arm'; END IF;
    END LOOP;
    accepted := TRUE;
    BEGIN DELETE FROM modkit_events.publication_history WHERE event_id=e;
    EXCEPTION WHEN SQLSTATE 'PZ012' THEN accepted := FALSE; END;
    IF accepted IS DISTINCT FROM FALSE THEN RAISE EXCEPTION 'publication history deleted'; END IF;
END
$test$;
-- Neither these table shapes nor the operation row prove an actual provider
-- confirmation or a current held outbox. Future E27 owns those obligations.
