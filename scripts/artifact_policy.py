"""Reviewed Events distribution inventory and privacy policy (stdlib only).

This is the Events 0.2 base distribution inventory. Optional driver and service
qualification remain separate release gates.
New distributable members or profiles require a deliberate policy review.
"""

import re
from email.message import Message

# A frozen reviewed inventory, never derived from the checkout at validation time.
PACKAGE_MEMBERS = frozenset(
    """
modkit_events/__init__.py
modkit_events/_failure_reporting.py
modkit_events/adapters/__init__.py
modkit_events/adapters/pydantic.py
modkit_events/adapters/redis.py
modkit_events/adapters/sqlalchemy.py
modkit_events/claims.py
modkit_events/codec.py
modkit_events/consumer.py
modkit_events/contracts.py
modkit_events/delivery.py
modkit_events/dispatch.py
modkit_events/models.py
modkit_events/outbox.py
modkit_events/persistence/__init__.py
modkit_events/persistence/_resource_io.py
modkit_events/persistence/bindings.py
modkit_events/persistence/catalog.py
modkit_events/persistence/errors.py
modkit_events/persistence/ledger.py
modkit_events/persistence/managed_lifecycle.py
modkit_events/persistence/migrations.py
modkit_events/persistence/models.py
modkit_events/persistence/native_codec.py
modkit_events/persistence/native_execution.py
modkit_events/persistence/native_profile.py
modkit_events/persistence/native_sync.py
modkit_events/persistence/observations.py
modkit_events/persistence/resource_lifecycle.py
modkit_events/persistence/resource_registry.py
modkit_events/persistence/rows.py
modkit_events/persistence/scope.py
modkit_events/persistence/sql/0001_initial.sql
modkit_events/persistence/sql/__init__.py
modkit_events/persistence/transitions.py
modkit_events/protocols.py
modkit_events/py.typed
modkit_events/retry.py
modkit_events/subscriptions.py
modkit_events/persistence/sql/grants_runtime.sql
modkit_events/persistence/sql/manifest.json
modkit_events/batch_publication.py
modkit_events/persistence/recovery_profile.py
modkit_events/persistence/sql/owner_receipt.sql
""".split()
)

SDIST_SUPPORT = frozenset(
    """
examples/sample_app.py
scripts/check_installation.py
scripts/check_postgres.py
scripts/check_wheel.py
scripts/release_verify.py
tests/sql_specs/binary_scope_vectors.sql
tests/sql_specs/canonical_j_vectors.sql
tests/sql_specs/chunk_frame_boundary_vectors.sql
tests/sql_specs/core_record_invariants.md
tests/sql_specs/decimal_binary64_vectors.sql
tests/sql_specs/dependent_records.md
tests/sql_specs/event_envelope_vectors.sql
tests/sql_specs/guard_constraint_schedules.md
tests/sql_specs/installation_profile_cases.md
tests/sql_specs/intent_literal_vectors.sql
tests/sql_specs/intent_projection_vectors.md
tests/sql_specs/json_replay_vectors.sql
tests/sql_specs/json_string_vectors.sql
tests/sql_specs/numeric_exact_boundary_vectors.sql
tests/sql_specs/opaque_evidence_bounds.md
tests/sql_specs/optional_instant_vectors.sql
tests/sql_specs/protected_material_vectors.sql
tests/sql_specs/segment10_event_readers.sql
tests/sql_specs/segment10_event_readers_schedules.md
tests/sql_specs/segment11_subscription_registration.sql
tests/sql_specs/segment11_subscription_registration_schedules.md
tests/sql_specs/segment12_inbox_admission.sql
tests/sql_specs/segment12_inbox_admission_schedules.md
tests/sql_specs/segment13_outbox_reader.sql
tests/sql_specs/segment14_outbox_enqueue.sql
tests/sql_specs/segment2_correction_stress.sql
tests/sql_specs/segment2_witness_index.sql
tests/sql_specs/segment3_attempt_history.sql
tests/sql_specs/segment3_operation_records.sql
tests/sql_specs/segment3_publication_records.sql
tests/sql_specs/segment3_record_oracles.md
tests/sql_specs/segment4_root_guard.sql
tests/sql_specs/segment4_root_guard_schedules.md
tests/sql_specs/segment5_arm_guard.sql
tests/sql_specs/segment5_arm_guard_schedules.md
tests/sql_specs/segment6_subtype_storage.sql
tests/sql_specs/segment6_subtype_storage_schedules.md
tests/sql_specs/segment7_complete_guard.sql
tests/sql_specs/segment7_complete_guard_schedules.md
tests/sql_specs/segment8_work_reader.sql
tests/sql_specs/segment9_readers.sql
tests/sql_specs/segment9_readers_schedules.md
tests/test_artifact_policy.py
tests/test_legacy_failure_reporting.py
tests/test_resource_cleanup_failure.py
tests/test_artifacts.py
tests/test_catalog_contract.py
tests/test_consumer.py
tests/test_contracts.py
tests/test_contracts_compatibility.py
tests/test_contracts_delivery.py
tests/test_contracts_exports.py
tests/test_contracts_pydantic.py
tests/test_contracts_subscriptions.py
tests/test_core.py
tests/test_isolation.py
tests/test_managed_lifecycle.py
tests/test_managed_statement_lifecycle.py
tests/test_managed_workers_lifecycle.py
tests/test_native_binary_transport.py
tests/test_native_execution.py
tests/test_native_workers_codec.py
tests/test_native_workers_execution.py
tests/test_native_workers_profile.py
tests/native/test_native_observation_integration.py
tests/test_native_sql_descriptor.py
tests/test_outbox.py
tests/test_persistence_boundaries.py
tests/test_json_replay_materialization.py
tests/test_persistence_contracts.py
tests/typecheck_persistence_boundaries.py
tests/test_redis.py
tests/test_redis_boundaries.py
tests/test_resource_lifecycle.py
tests/test_scope_storage.py
tests/test_sqlalchemy.py
tests/test_standalone_package.py
tests/test_work_listing_sql.py
tests/test_audit_readers_sql.py
tests/test_publication_history_sql.py
tests/test_publication_claim_sql.py
tests/test_publication_renewal_sql.py
tests/test_publication_intent_sql.py
tests/test_publication_settlement_sql.py
tests/test_publication_recovery_sql.py
tests/test_publication_reconciliation_sql.py
scripts/artifact_policy.py
pyproject.toml
README.md
LICENSE
CHANGELOG.md
requirements-dev.txt
.gitignore
PKG-INFO
tests/_installation_artifact_helpers.py
tests/native/test_e13_recovery_integration.py
tests/native/test_e31_resolution_sql_integration.py
tests/native/test_native_renewal_integration.py
tests/test_batch_publication.py
tests/test_e31_held_resolution_sql.py
tests/test_e32_uncertain_settlement_sql.py
tests/test_fenced_failure_sql.py
tests/test_installation_grants_contract.py
tests/test_postgres_ci.py
tests/test_native_acquisition_sql.py
tests/test_native_execution_completion_codec.py
tests/test_native_execution_completion_contract.py
tests/test_native_execution_completion_issuer.py
tests/test_native_failure_codec.py
tests/test_native_failure_contract.py
tests/test_native_failure_issuer.py
tests/test_native_failure_lifecycle.py
tests/test_native_readiness_codec.py
tests/test_native_readiness_contract.py
tests/test_native_readiness_issuer.py
tests/test_native_readiness_lifecycle.py
tests/test_native_readiness_sql.py
tests/test_native_recovery_codec.py
tests/test_native_recovery_contract.py
tests/test_native_recovery_issuer.py
tests/test_native_recovery_lifecycle.py
tests/test_native_recovery_preflight.py
tests/test_native_recovery_profile.py
tests/recovery_test_support.py
tests/test_recovery_platform_gate.py
tests/test_native_renewal_codec.py
tests/test_native_renewal_contract.py
tests/test_native_renewal_issuer.py
tests/test_native_resolution_codec.py
tests/test_native_resolution_contract.py
tests/test_native_resolution_integration.py
tests/test_native_resolution_issuer.py
tests/test_native_resolution_lifecycle.py
tests/test_native_uncertainty_codec.py
tests/test_native_uncertainty_contract.py
tests/test_native_uncertainty_issuer.py
tests/test_native_uncertainty_lifecycle.py
tests/test_owner_receipt_resource.py
tests/test_packaged_migrations.py
tests/test_work_cancellation_sql.py
tests/test_work_recovery_sql.py
""".split()
)

# Every supported runtime leaf is required; only backend incidental ignore rules are optional.
REQUIRED_PACKAGE = PACKAGE_MEMBERS

DEPENDENCIES = frozenset(
    {
        ("pydantic", "", ("<3", ">=2.14"), "pydantic"),
        ("redis", "", ("<9", ">=8.1"), "redis"),
        ("sqlalchemy", "asyncio", ("<3", ">=2.1.6"), "sqlalchemy"),
    }
)


def require(condition: object, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def audit_metadata(metadata: Message) -> None:
    extras = metadata.get_all("Provides-Extra", [])
    require(
        len(extras) == 3 and set(extras) == {"pydantic", "redis", "sqlalchemy"},
        "unexpected dependency extras",
    )
    dependencies = []
    for value in metadata.get_all("Requires-Dist", []):
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)(?:\[([a-z]+)\])?\s*([^;]+);\s*"
            r"extra\s*==\s*['\"]([a-z]+)['\"]",
            value.strip(),
        )
        if match is None:
            raise ValueError("unexpected dependency requirement")
        name, extra, bounds, marker = match.groups()
        dependencies.append(
            (
                name.lower().replace("_", "-"),
                extra or "",
                tuple(sorted(x.strip() for x in bounds.split(","))),
                marker,
            )
        )
    require(
        len(dependencies) == 3 and frozenset(dependencies) == DEPENDENCIES,
        "unexpected dependency contract",
    )


def audit_content(name: str, content: bytes) -> None:
    # Construct marker literals in pieces: this checker is itself public source.
    host = rb"(?:/" + rb"home/|/" + rb"workspace/|/" + rb"Users/|[A-Za-z]:[\\/]Users[\\/])"
    require(re.search(host, content, re.I) is None, "private host reference: " + name)
    require(b"modkit" + b"-local-" not in content, "private evidence reference: " + name)
    application = b"operations" + b"_erp"
    # Permit only the exact, existing negative import-blocker line. All other
    # lines and markers remain scanned, including content in this test file.
    sentinel = (
        b"        if fullname.split('.')[0] in {'redis', 'sqlalchemy', 'operations"
        b"_erp', 'modkit_diagnostics'}:"
    )
    for line in content.splitlines():
        if name == "tests/test_isolation.py" and line == sentinel:
            continue
        require(application not in line, "private application reference: " + name)


def audit_members(
    files: dict[str, bytes], directories: list[str], *, wheel: bool, version: str, metadata: Message
) -> None:
    if wheel:
        info = "modkit_events-" + version + ".dist-info/"
        metadata_members = {
            info + name for name in ("METADATA", "WHEEL", "RECORD", "licenses/LICENSE")
        }
        allowed = set(PACKAGE_MEMBERS) | metadata_members
        required = set(REQUIRED_PACKAGE) | metadata_members
        normalized = files
    else:
        root = "modkit_events-" + version + "/"
        require(all(name.startswith(root) for name in files), "unexpected sdist member root")
        normalized = {name[len(root) :]: value for name, value in files.items()}
        allowed = {"src/" + name for name in PACKAGE_MEMBERS} | SDIST_SUPPORT
        required = {"src/" + name for name in REQUIRED_PACKAGE} | (SDIST_SUPPORT - {".gitignore"})
        directories = [
            name[len(root) :] if name.startswith(root) else name
            for name in directories
            if name != root.rstrip("/")
        ]
    require(set(normalized) <= allowed, "unreviewed artifact member")
    require(required <= set(normalized), "missing required artifact member/resource")
    ancestors = {
        "/".join(name.split("/")[:i]) for name in allowed for i in range(1, len(name.split("/")))
    }
    require(
        all(name.rstrip("/") in ancestors for name in directories),
        "unreviewed artifact directory member",
    )
    audit_metadata(metadata)
    for name, content in normalized.items():
        audit_content(name, content)
