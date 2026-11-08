-- Run after the exact baseline plus e30.sql inside a caller-owned
-- REPEATABLE READ rollback transaction on an isolated test database.
DO $isolation$
BEGIN
    BEGIN
        PERFORM * FROM modkit_events.e30('absent'::bytea,NULL,NULL,1);
        RAISE EXCEPTION 'E30 accepted unsupported transaction isolation';
    EXCEPTION WHEN SQLSTATE 'PZ005' THEN NULL; END;
    RAISE NOTICE 'E30_ISOLATION_PASS: REPEATABLE READ rejected with PZ005';
END
$isolation$;
