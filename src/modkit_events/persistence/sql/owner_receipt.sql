INSERT INTO modkit_events.schema_versions
(component, version, migration_digest, catalog_contract_id,
 scope_format_id, intent_format_id, applied_at)
VALUES ($1::pg_catalog.text, $2::pg_catalog.int4, $3::pg_catalog.bytea,
        $4::pg_catalog.text, $5::pg_catalog.text, $6::pg_catalog.text,
        pg_catalog.clock_timestamp());
