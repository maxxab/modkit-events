-- Segment6 prospective assertions, authored BEFORE production append. NOT_RUN.
-- NO permission to parse/compile/install/run these statements. Later authorized
-- executor: fresh isolated schema-owner fixture database, caller-owned explicit
-- READ COMMITTED transaction, final full ROLLBACK. No production test helpers,
-- role/default/session changes or constraint bypass. Structural rows below are
-- not public W01/E03 admissions, counter accounting or dispatch-COMMIT proof.
-- Companions retain multi-root wait, isolation, ACL and boundary obligations.

-- S6-RAW: opaque equality, STRICT/NULL, optional-normalizing, absent-only,
-- text-only material, timestamp truncation and metadata-tag-only mutants fail.
DO $test$
DECLARE
    empty_object pg_catalog.bytea := pg_catalog.decode('6f00000000','hex');
    absent_fields pg_catalog.bytea[]; present_fields pg_catalog.bytea[];
    fields pg_catalog.bytea[]; raw pg_catalog.bytea; bad pg_catalog.bytea;
    tag pg_catalog.bytea := pg_catalog.convert_to('protected-binding','UTF8');
    i pg_catalog.int4; j pg_catalog.int4; c pg_catalog.record;
    expiry_text pg_catalog.text; remaining pg_catalog.int4;
BEGIN
    absent_fields := ARRAY[
      'absent'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
      'retain'::pg_catalog.bytea,'0'::pg_catalog.bytea,'0'::pg_catalog.bytea,
      ''::pg_catalog.bytea,''::pg_catalog.bytea,empty_object]::pg_catalog.bytea[];
    present_fields := ARRAY[
      'present'::pg_catalog.bytea,modkit_events._optional_bytes(pg_catalog.decode('6300','hex')),
      modkit_events._optional_bytes('k'::pg_catalog.bytea),'0'::pg_catalog.bytea,
      'erase_after_terminal'::pg_catalog.bytea,modkit_events._optional_bytes(pg_catalog.decode('ff00','hex')),
      '0'::pg_catalog.bytea,pg_catalog.convert_to(pg_catalog.repeat('b',257),'UTF8'),
      empty_object,empty_object]::pg_catalog.bytea[];
    raw := modkit_events._make_record(tag,absent_fields);
    IF modkit_events._protected_frame_valid(raw) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'canonical absent rejected';
    END IF;
    FOR c IN SELECT value FROM (VALUES
      (NULL::pg_catalog.bytea),(''::pg_catalog.bytea),('x'::pg_catalog.bytea),
      (raw || 'x'::pg_catalog.bytea),(pg_catalog.substr(raw,1,pg_catalog.octet_length(raw)-1)),
      (pg_catalog.set_byte(raw,4,2)),(modkit_events._make_record('other'::pg_catalog.bytea,absent_fields)),
      (modkit_events._make_record(tag,absent_fields[1:9])),
      (pg_catalog.decode('4d4b504601ffffffffffffffff','hex')),
      (pg_catalog.convert_to(pg_catalog.repeat('x',1048577),'UTF8'))
    ) AS malformed(value)
    LOOP
        IF modkit_events._protected_frame_valid(c.value) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'malformed raw was not nonnull false';
        END IF;
    END LOOP;
    -- Every optional slot, absent versus malformed/present-empty.
    FOREACH i IN ARRAY ARRAY[2,3,4,6,7]::pg_catalog.int4[] LOOP
        FOR c IN SELECT value FROM (VALUES
          ('00'::pg_catalog.bytea),(pg_catalog.decode('00','hex')),('2'::pg_catalog.bytea),
          ('1'::pg_catalog.bytea),('1'::pg_catalog.bytea || pg_catalog.int8send(1::pg_catalog.int8)),
          ('1'::pg_catalog.bytea || pg_catalog.int8send(0::pg_catalog.int8) || 'x'::pg_catalog.bytea),
          (modkit_events._optional_bytes(''::pg_catalog.bytea)),
          ('1'::pg_catalog.bytea || pg_catalog.decode('ffffffffffffffff','hex'))
        ) AS malformed(value)
        LOOP
            fields := absent_fields; fields[i] := c.value;
            bad := modkit_events._make_record(tag,fields);
            IF modkit_events._protected_frame_valid(bad) IS DISTINCT FROM FALSE THEN
                RAISE EXCEPTION 'invalid optional/coupling accepted';
            END IF;
        END LOOP;
    END LOOP;
    -- Canonical present sidecar AND reference, both cleanup codes, exact UTC.
    FOR i IN 1..2 LOOP
      FOR j IN 1..2 LOOP
        FOREACH expiry_text IN ARRAY ARRAY[NULL::pg_catalog.text,
          '0001-01-01T00:00:00.000000Z','2000-02-29T12:34:56.000001Z',
          '1900-01-01T00:00:00.999999Z','9999-12-31T23:59:59.999999Z']::pg_catalog.text[] LOOP
            fields := present_fields;
            IF i=2 THEN fields[7]:=fields[6]; fields[6]:='0'::pg_catalog.bytea; END IF;
            IF j=2 THEN fields[5]:='retain'::pg_catalog.bytea; END IF;
            fields[4]:=modkit_events._optional_bytes(pg_catalog.convert_to(expiry_text,'UTF8'));
            raw:=modkit_events._make_record(tag,fields);
            IF modkit_events._protected_frame_valid(raw) IS DISTINCT FROM TRUE THEN
                RAISE EXCEPTION 'supported present material/expiry rejected';
            END IF;
        END LOOP;
      END LOOP;
    END LOOP;
    FOREACH expiry_text IN ARRAY ARRAY[
      '0000-01-01T00:00:00.000000Z','10000-01-01T00:00:00.000000Z',
      '1900-02-29T00:00:00.000000Z','2000-02-30T00:00:00.000000Z',
      '2000-13-01T00:00:00.000000Z','2000-00-01T00:00:00.000000Z',
      '2000-01-00T00:00:00.000000Z','2000-01-01T24:00:00.000000Z',
      '2000-01-01T00:60:00.000000Z','2000-01-01T00:00:60.000000Z',
      '2000-01-01t00:00:00.000000Z','2000-01-01 00:00:00.000000Z',
      '2000-01-01T00:00:00.000000z','2000-01-01T00:00:00.00000Z',
      '2000-01-01T00:00:00.0000000Z','2000-01-01T00:00:00.000000+00:00',
      '2000-01-01T00:00:00.00000xZ','infinity','']::pg_catalog.text[] LOOP
        fields:=present_fields; fields[4]:=modkit_events._optional_bytes(pg_catalog.convert_to(expiry_text,'UTF8'));
        IF modkit_events._protected_frame_valid(modkit_events._make_record(tag,fields)) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'noncanonical/invalid expiry accepted';
        END IF;
    END LOOP;
    FOR c IN SELECT * FROM (VALUES
      (1::pg_catalog.int4,'erased'::pg_catalog.bytea),(1,'PRESENT'::pg_catalog.bytea),
      (1,'present '::pg_catalog.bytea),(1,pg_catalog.decode('70726573656e7400','hex')),
      (5,'RETAIN'::pg_catalog.bytea),(5,'other'::pg_catalog.bytea),
      (2,'0'::pg_catalog.bytea),(3,'0'::pg_catalog.bytea),
      (2,modkit_events._optional_bytes(' '::pg_catalog.bytea)),
      (3,modkit_events._optional_bytes(pg_catalog.decode('ff','hex'))),
      (2,modkit_events._optional_bytes(pg_catalog.convert_to(pg_catalog.repeat('x',257),'UTF8'))),
      (6,'0'::pg_catalog.bytea),(6,modkit_events._optional_bytes(''::pg_catalog.bytea)),
      (7,modkit_events._optional_bytes('reference'::pg_catalog.bytea)),
      (8,''::pg_catalog.bytea),(9,''::pg_catalog.bytea),(10,''::pg_catalog.bytea),
      (9,'n'::pg_catalog.bytea),(10,pg_catalog.decode('6100000000','hex')),
      (9,empty_object || 'x'::pg_catalog.bytea),(10,empty_object || 'x'::pg_catalog.bytea),
      (10,pg_catalog.decode('6f00000001000000000000000161000000000000000178','hex'))
    ) AS malformed(field_no,value)
    LOOP
        fields:=present_fields; fields[c.field_no]:=c.value;
        IF modkit_events._protected_frame_valid(modkit_events._make_record(tag,fields)) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'present coupling/code/canonical defect accepted';
        END IF;
    END LOOP;
    FOR c IN SELECT * FROM (VALUES
      (1::pg_catalog.int4,'ABSENT'::pg_catalog.bytea),(5,'erase_after_terminal'::pg_catalog.bytea),
      (8,'x'::pg_catalog.bytea),(9,empty_object)
    ) AS malformed(field_no,value)
    LOOP
        fields:=absent_fields; fields[c.field_no]:=c.value;
        IF modkit_events._protected_frame_valid(modkit_events._make_record(tag,fields)) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'absent coupling defect accepted';
        END IF;
    END LOOP;
    -- Feasible helper-frame maximum, not simultaneous field maxima or intent fit.
    fields:=present_fields; raw:=modkit_events._make_record(tag,fields);
    remaining:=1048576-pg_catalog.octet_length(raw)+2; -- original opaque sidecar was2 bytes
    fields[6]:=modkit_events._optional_bytes(pg_catalog.convert_to(pg_catalog.repeat('x',remaining),'UTF8'));
    raw:=modkit_events._make_record(tag,fields);
    IF pg_catalog.octet_length(raw) IS DISTINCT FROM 1048576
       OR modkit_events._protected_frame_valid(raw) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'feasible maximum raw frame rejected';
    END IF;
END
$test$;

-- S6-COMPOSITION: canonical structural controls for BOTH kinds and all material
-- forms. Setup outside error catchers. Negative target must actually fail,
-- checked immediately, not hidden by the caller's eventual ROLLBACK.
DO $test$
DECLARE
    empty_object pg_catalog.bytea:=pg_catalog.decode('6f00000000','hex');
    t0 pg_catalog.timestamptz:='2000-01-01T00:00:00Z'::pg_catalog.timestamptz;
    scope_frame pg_catalog.bytea:=pg_catalog.decode('4d4b5343010001610000','hex');
    fields pg_catalog.bytea[]; binding pg_catalog.bytea; intent pg_catalog.bytea;
    replay pg_catalog.bytea; semantic pg_catalog.bytea; event_id pg_catalog.bytea;
    work_id_value pg_catalog.uuid; subscription_value pg_catalog.bytea;
    namespace_value pg_catalog.bytea; kind_value pg_catalog.text;
    sidecar pg_catalog.bytea; reference_value pg_catalog.bytea; codec pg_catalog.bytea;
    key_version pg_catalog.bytea; recovery pg_catalog.bytea; state_value pg_catalog.text;
    kind_no pg_catalog.int4; material_no pg_catalog.int4; got pg_catalog.text;
    stored_work modkit_events.work%ROWTYPE; before_work modkit_events.work%ROWTYPE;
    stored_job modkit_events.job_payloads%ROWTYPE; stored_inbox modkit_events.inbox%ROWTYPE;
    after_job modkit_events.job_payloads%ROWTYPE; after_inbox modkit_events.inbox%ROWTYPE;
    c pg_catalog.record;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'fixture requires caller READ COMMITTED';
    END IF;
    INSERT INTO modkit_events.subscriptions VALUES
      ('s6-parent'::pg_catalog.bytea,''::pg_catalog.bytea,'s6-group'::pg_catalog.bytea,100,0,t0);
    FOR kind_no IN 1..2 LOOP
      FOR material_no IN 0..3 LOOP
        IF kind_no=1 AND material_no=3 THEN CONTINUE; END IF;
        kind_value:=CASE WHEN kind_no=1 THEN 'job' ELSE 'inbox' END;
        subscription_value:=CASE WHEN kind_no=2 THEN 's6-parent'::pg_catalog.bytea END;
        namespace_value:=pg_catalog.convert_to(CASE WHEN kind_no=1 THEN 'jobs' ELSE 'events' END,'UTF8');
        work_id_value:=pg_catalog.gen_random_uuid();
        event_id:=pg_catalog.convert_to(work_id_value::pg_catalog.text,'UTF8');
        sidecar:=NULL;reference_value:=NULL;codec:=NULL;key_version:=NULL;
        recovery:=''::pg_catalog.bytea;state_value:='absent';
        IF material_no IN (1,2) THEN
            state_value:='present';codec:=pg_catalog.decode('6300','hex');key_version:='k'::pg_catalog.bytea;
            recovery:=empty_object;
            IF material_no=1 THEN sidecar:=pg_catalog.decode('ff00','hex');
            ELSE reference_value:=pg_catalog.decode('ff00','hex'); END IF;
        END IF;
        fields:=ARRAY[pg_catalog.convert_to(state_value,'UTF8'),modkit_events._optional_bytes(codec),
          modkit_events._optional_bytes(key_version),'0'::pg_catalog.bytea,'retain'::pg_catalog.bytea,
          modkit_events._optional_bytes(sidecar),modkit_events._optional_bytes(reference_value),
          CASE WHEN material_no IN (1,2) THEN 'binding'::pg_catalog.bytea ELSE ''::pg_catalog.bytea END,
          recovery,empty_object]::pg_catalog.bytea[];
        binding:=modkit_events._make_record('protected-binding'::pg_catalog.bytea,fields);
        IF material_no=3 THEN binding:='x'::pg_catalog.bytea; END IF;
        IF kind_no=1 THEN replay:='{}'::pg_catalog.bytea;semantic:=empty_object;
        ELSE
            replay:=pg_catalog.convert_to('{"event_id":"'||work_id_value::pg_catalog.text||'","name":"cmd","schema_version":1,"payload":{},"metadata":{}}','UTF8');
            semantic:=modkit_events._event_replay_frame(replay);
        END IF;
        intent:=modkit_events._make_record('work-intent'::pg_catalog.bytea,ARRAY[
          pg_catalog.convert_to(kind_value,'UTF8'),modkit_events._optional_bytes(subscription_value),
          namespace_value,'cmd'::pg_catalog.bytea,'1'::pg_catalog.bytea,'1'::pg_catalog.bytea,
          scope_frame,'0'::pg_catalog.bytea,semantic,binding,'application_safe'::pg_catalog.bytea,
          '3'::pg_catalog.bytea,'0'::pg_catalog.bytea,modkit_events._instant_bytes(t0)]::pg_catalog.bytea[]);
        -- In EX1 negative this MUST succeed; otherwise a stale/malformed intent
        -- would mask the missing protected-frame predicate under examination.
        IF modkit_events._intent_valid(kind_value,subscription_value,namespace_value,'cmd'::pg_catalog.bytea,
          scope_frame,NULL,1,'1'::pg_catalog.bytea,'a'::pg_catalog.bytea,NULL,NULL,
          intent,semantic,replay,binding,'application_safe',3,NULL,t0) IS DISTINCT FROM TRUE THEN
            RAISE EXCEPTION 'canonical fixture intent is invalid';
        END IF;
        INSERT INTO modkit_events.work(work_id,kind,subscription_id,namespace,command_type,
          schema_version_decimal,runnable_version,canonical_version,scope_evidence,scope_application,
          intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
          original_available_at,state,cancellation_requested,ownership_revision,available_at,
          cycle,attempt_count,created_at,updated_at)
        VALUES(work_id_value,kind_value,subscription_value,namespace_value,'cmd'::pg_catalog.bytea,
          '1'::pg_catalog.bytea,1,1,scope_frame,'a'::pg_catalog.bytea,intent,semantic,replay,binding,
          'application_safe',3,t0,'queued',FALSE,0,t0,1,0,t0,t0)
        RETURNING * INTO stored_work;
        before_work:=stored_work;
        IF kind_no=1 THEN
            -- Redundant semantic mismatch fails trigger before local CHECK.
            BEGIN
                INSERT INTO modkit_events.job_payloads VALUES(work_id_value,'a'::pg_catalog.bytea,NULL,NULL,
                  binding,'n'::pg_catalog.bytea,state_value,sidecar,reference_value,codec,key_version,
                  NULL,recovery,'retain',empty_object);
                RAISE EXCEPTION 'job semantic mismatch returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
            -- Nonredundant projection defect reaches local material/canonical CHECK.
            BEGIN
                INSERT INTO modkit_events.job_payloads VALUES(work_id_value,'a'::pg_catalog.bytea,NULL,NULL,
                  binding,semantic,state_value,sidecar,reference_value,codec,key_version,
                  NULL,recovery,'retain','n'::pg_catalog.bytea);
                RAISE EXCEPTION 'job invalid projection returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM '23514' THEN RAISE; END IF;
            END;
            INSERT INTO modkit_events.job_payloads VALUES(work_id_value,'a'::pg_catalog.bytea,NULL,NULL,
              binding,semantic,state_value,sidecar,reference_value,codec,key_version,NULL,recovery,'retain',empty_object)
            RETURNING * INTO stored_job;
            IF ROW(stored_job.job_work_id,stored_job.job_application,stored_job.job_tenant,stored_job.job_owner,
                stored_job.job_protected_binding,stored_job.job_semantic_input,stored_job.material_state,
                stored_job.protected_sidecar,stored_job.protected_reference,stored_job.protected_codec,
                stored_job.protected_key_version,stored_job.protected_expires_at,stored_job.protected_recovery_metadata,
                stored_job.protected_cleanup_policy,stored_job.projection_metadata)
              IS DISTINCT FROM ROW(work_id_value,'a'::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
                binding,semantic,state_value,sidecar,reference_value,codec,key_version,NULL::pg_catalog.timestamptz,
                recovery,'retain'::pg_catalog.text,empty_object) THEN
                RAISE EXCEPTION 'job stored15-field projection changed';
            END IF;
            BEGIN
                INSERT INTO modkit_events.job_payloads SELECT stored_job.*;
                RAISE EXCEPTION 'same-kind duplicate returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM '23505' THEN RAISE; END IF;
            END;
            BEGIN
                INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                VALUES(work_id_value,'s6-parent'::pg_catalog.bytea,event_id,semantic,replay);
                RAISE EXCEPTION 'wrong inbox kind returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
        ELSE
            IF material_no=3 THEN
                BEGIN
                    INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                    VALUES(work_id_value,subscription_value,event_id,semantic,replay);
                    RAISE EXCEPTION 'EX1 opaque matching-intent inbox returned normally';
                EXCEPTION WHEN OTHERS THEN
                    GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                    IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
                END;
                IF EXISTS(SELECT 1 FROM modkit_events.inbox AS i WHERE i.work_id=work_id_value) THEN
                    RAISE EXCEPTION 'failed inbox left subtype';
                END IF;
                SELECT w.* INTO STRICT stored_work FROM modkit_events.work AS w WHERE w.work_id=work_id_value;
                IF stored_work IS DISTINCT FROM before_work THEN RAISE EXCEPTION 'EX1 rejection changed work'; END IF;
                CONTINUE;
            END IF;
            BEGIN
                INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
                VALUES(work_id_value,subscription_value,'wrong-event'::pg_catalog.bytea,semantic,replay);
                RAISE EXCEPTION 'inbox event mismatch returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
            INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
            VALUES(work_id_value,subscription_value,event_id,semantic,replay) RETURNING * INTO stored_inbox;
            IF ROW(stored_inbox.work_id,stored_inbox.subscription_id,stored_inbox.event_id,
              stored_inbox.event_digest,stored_inbox.envelope_evidence,stored_inbox.replay_input)
              IS DISTINCT FROM ROW(work_id_value,subscription_value,event_id,pg_catalog.sha256(event_id),semantic,replay) THEN
                RAISE EXCEPTION 'inbox stored projection changed';
            END IF;
            BEGIN
                INSERT INTO modkit_events.job_payloads VALUES(work_id_value,'a'::pg_catalog.bytea,NULL,NULL,
                  binding,semantic,state_value,sidecar,reference_value,codec,key_version,NULL,recovery,'retain',empty_object);
                RAISE EXCEPTION 'wrong job kind returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
        END IF;
        -- Same-value subtype update and deletion both must fail BEFORE mutation.
        FOR c IN SELECT command FROM (VALUES
          (CASE WHEN kind_no=1 THEN 'UPDATE modkit_events.job_payloads SET job_work_id=job_work_id WHERE job_work_id=$1'
                ELSE 'UPDATE modkit_events.inbox SET work_id=work_id WHERE work_id=$1' END),
          (CASE WHEN kind_no=1 THEN 'DELETE FROM modkit_events.job_payloads WHERE job_work_id=$1'
                ELSE 'DELETE FROM modkit_events.inbox WHERE work_id=$1' END)
        ) AS commands(command)
        LOOP
            BEGIN
                EXECUTE c.command USING work_id_value;
                RAISE EXCEPTION 'subtype mutation returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
        END LOOP;
        -- Allowed lifecycle-only work update; no admission tuple assignment.
        UPDATE modkit_events.work SET updated_at=t0+'1 second'::pg_catalog.interval WHERE work_id=work_id_value;
        SELECT w.* INTO STRICT stored_work FROM modkit_events.work AS w WHERE w.work_id=work_id_value;
        before_work.updated_at:=t0+'1 second'::pg_catalog.interval;
        IF stored_work IS DISTINCT FROM before_work THEN RAISE EXCEPTION 'lifecycle update footprint changed'; END IF;
        -- Every immutable field independently: trigger must win over native
        -- NULL/CHECK/FK errors. Null optional fields are changed to nonnull.
        FOR c IN SELECT * FROM (VALUES
          ('work_id','NULL'),('kind','NULL'),('subscription_id',CASE WHEN kind_no=1 THEN '''s6-parent''::pg_catalog.bytea' ELSE 'NULL' END),
          ('namespace','NULL'),('command_type','NULL'),('schema_version_decimal','NULL'),
          ('canonical_version','NULL'),('scope_evidence','NULL'),('scope_application','NULL'),
          ('scope_tenant','''tenant''::pg_catalog.bytea'),('scope_owner','''owner''::pg_catalog.bytea'),
          ('idempotency_key','''key''::pg_catalog.bytea'),('intent_evidence','NULL'),('semantic_input','NULL'),
          ('replay_input','NULL'),('protected_binding','NULL'),('replay_policy','NULL'),('max_attempts','NULL'),
          ('deadline','''2001-01-01T00:00:00Z''::pg_catalog.timestamptz'),
          ('original_available_at','NULL'),('created_at','NULL')
        ) AS mutations(column_name,expression)
        LOOP
            BEGIN
                EXECUTE pg_catalog.format('UPDATE modkit_events.work SET %I=%s WHERE work_id=$1',c.column_name,c.expression) USING work_id_value;
                RAISE EXCEPTION 'immutable work field mutation returned normally';
            EXCEPTION WHEN OTHERS THEN
                GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
                IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
            END;
        END LOOP;
        BEGIN
            DELETE FROM modkit_events.work WHERE work_id=work_id_value;
            RAISE EXCEPTION 'work delete returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM 'PZ012' THEN RAISE; END IF;
        END;
        SELECT w.* INTO STRICT stored_work FROM modkit_events.work AS w WHERE w.work_id=work_id_value;
        IF stored_work IS DISTINCT FROM before_work THEN RAISE EXCEPTION 'rejected work mutations changed row'; END IF;
        IF kind_no=1 THEN
            SELECT j.* INTO STRICT after_job FROM modkit_events.job_payloads AS j WHERE j.job_work_id=work_id_value;
            IF after_job IS DISTINCT FROM stored_job THEN RAISE EXCEPTION 'rejected mutations changed job'; END IF;
        ELSE
            SELECT i.* INTO STRICT after_inbox FROM modkit_events.inbox AS i WHERE i.work_id=work_id_value;
            IF after_inbox IS DISTINCT FROM stored_inbox THEN RAISE EXCEPTION 'rejected mutations changed inbox'; END IF;
        END IF;
      END LOOP;
    END LOOP;
    IF (SELECT s.nonterminal_count FROM modkit_events.subscriptions AS s WHERE s.subscription_id='s6-parent'::pg_catalog.bytea) IS DISTINCT FROM 0::pg_catalog.int8 THEN
        RAISE EXCEPTION 'structural insert invented capacity accounting';
    END IF;
END
$test$;

-- S6-MISSING/NULL: no invisible-parent rescue through a later FK wait.
-- Concurrent invisible parent and wrong isolation are separate schedules.
DO $test$
DECLARE got pg_catalog.text; wid pg_catalog.uuid; n pg_catalog.int4;
BEGIN
    FOR n IN 1..2 LOOP
        wid:=CASE WHEN n=1 THEN NULL::pg_catalog.uuid ELSE pg_catalog.gen_random_uuid() END;
        BEGIN
            INSERT INTO modkit_events.job_payloads(job_work_id) VALUES(wid);
            RAISE EXCEPTION 'job missing/NULL work returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM CASE WHEN n=1 THEN '23502' ELSE 'PZ012' END THEN RAISE; END IF;
        END;
        BEGIN
            INSERT INTO modkit_events.inbox(work_id) VALUES(wid);
            RAISE EXCEPTION 'inbox missing/NULL work returned normally';
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE;
            IF got IS DISTINCT FROM CASE WHEN n=1 THEN '23502' ELSE 'PZ012' END THEN RAISE; END IF;
        END;
    END LOOP;
END
$test$;
