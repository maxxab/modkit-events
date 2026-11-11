-- E30 and W03 listing indexes. Inert candidate, NOT_READY.
-- Apply only through the separately reviewed complete Events migration.
CREATE INDEX work_namespace_created_page ON modkit_events.work (namespace,created_at,work_id);
CREATE INDEX work_jobs_created_page ON modkit_events.work (namespace,created_at,work_id)
    WHERE kind COLLATE pg_catalog."C" = 'job' COLLATE pg_catalog."C";

CREATE FUNCTION modkit_events.e30(
    p_namespace pg_catalog.bytea,
    p_after_created_at pg_catalog.timestamptz,
    p_after_work_id pg_catalog.uuid,
    p_limit pg_catalog.int4)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256
       OR (p_after_created_at IS NULL) <> (p_after_work_id IS NULL)
       OR (p_after_created_at IS NOT NULL AND modkit_events._instant_bytes(p_after_created_at) IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid work listing arguments';
    END IF;

    -- Limit indexed IDs before full integrity validation. STABLE E15 and E30
    -- share the invoking statement snapshot; no selected row is skipped.
    -- Separate branches keep the continuation tuple directly indexable.
    IF p_after_created_at IS NULL THEN
        RETURN QUERY
        WITH page AS MATERIALIZED (
            SELECT listed.work_id,listed.created_at
              FROM modkit_events.work AS listed
             WHERE listed.namespace=p_namespace
             ORDER BY listed.created_at,listed.work_id
             LIMIT p_limit
        )
        SELECT observed.*
          FROM page
          CROSS JOIN LATERAL modkit_events.e15(page.work_id) AS observed
         ORDER BY page.created_at,page.work_id;
    ELSE
        RETURN QUERY
        WITH page AS MATERIALIZED (
            SELECT listed.work_id,listed.created_at
              FROM modkit_events.work AS listed
             WHERE listed.namespace=p_namespace
               AND (listed.created_at,listed.work_id)>(p_after_created_at,p_after_work_id)
             ORDER BY listed.created_at,listed.work_id
             LIMIT p_limit
        )
        SELECT observed.*
          FROM page
          CROSS JOIN LATERAL modkit_events.e15(page.work_id) AS observed
         ORDER BY page.created_at,page.work_id;
    END IF;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e30(pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.uuid,pg_catalog.int4) FROM PUBLIC;
