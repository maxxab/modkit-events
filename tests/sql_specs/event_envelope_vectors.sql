-- BEFORE dedicated event envelope helper. NOT_RUN; no SQL authorization.
DO $test$
DECLARE result pg_catalog.bytea; expected pg_catalog.bytea;
BEGIN
    result := modkit_events._event_replay_frame(pg_catalog.convert_to('{"event_id":"a","name":"b","schema_version":1,"payload":{},"metadata":{}}','UTF8'));
    expected := pg_catalog.decode(
      '4d4b504601000000000000000e6576656e742d656e76656c6f706500000005' ||
      '000000000000000161' || '000000000000000162' || '000000000000000131' ||
      '00000000000000056f00000000' || '00000000000000056f00000000','hex');
    IF result IS DISTINCT FROM expected THEN RAISE EXCEPTION 'event frame differs'; END IF;
    IF modkit_events._event_replay_frame(pg_catalog.convert_to('{"event_id":"a","name":"b","schema_version":1.0,"payload":{},"metadata":{}}','UTF8')) IS NOT NULL THEN
        RAISE EXCEPTION 'floating schema version accepted';
    END IF;
    IF modkit_events._event_replay_frame(pg_catalog.convert_to('{"event_id":"a","name":"b","schema_version":1,"payload":{}}','UTF8')) IS NOT NULL THEN
        RAISE EXCEPTION 'omitted managed metadata accepted';
    END IF;
END
$test$;
