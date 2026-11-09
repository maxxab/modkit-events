# Native E33 schema receipt check

Status: independently accepted source with bounded standalone E33 native
qualification. Full Worker startup/integration and product readiness remain
**NOT_READY**. This is not a complete installation or release manifest.

## Authority and profiles

The existing E33 contract has one required_profile TEXT parameter and six
SchemaStatus columns: component, version, migration_digest, catalog_contract_id,
scope_format_id, intent_format_id. The events profile returns exactly events;
workers returns exactly events then workers. An installed workers receipt does
not invalidate the events-only check.

Application/deployment configuration supplies pinned ReadinessExpectation with
existing SchemaStatus values. Each uses the explicit component, positive int4
version and independently obtained 32-byte migration_digest, with identifiers
modkit-pg-ab-2 / MKSC-1 / MKPF-1. No automatic digest generation or installed-version
default is provided. Matching receipts do not prove runtime permissions,
migrations, dependencies or product completeness.

The appended e33 function only reads schema_versions. It does not write receipts,
install schema/grants, lock work, commit, or repair failures. The initial SQL
remains NOT READY TO APPLY. Production manifest digests, installation receipts
and least-privilege grants remain release work.

## Native call and paid lifetime

Construct ReadinessExpectation(components=(events_status, workers_status)), or a
one-item events tuple, with the existing keyword-only constructors. All six named
SchemaStatus fields remain required.

The caller owns an active explicit managed root, execution handle and ledger:

    from modkit_events.persistence import managed_lifecycle as managed
    from modkit_events.persistence import native_execution as native

    preparation = native.prepare_readiness(
        execution, "workers", pinned_expectation, execution_ledger=ledger
    )
    ticket = managed.admit(root, preparation, execution_ledger=ledger)
    result = managed.reserve_result(
        ticket, native.READINESS_RESULT_CAPACITY, execution_ledger=ledger
    )
    native.execute(ticket, result, execution_ledger=ledger)
    statuses = managed.read_result(result, execution_ledger=ledger)
    # Exact tuple[SchemaStatus, ...], equal to pinned expectations.
    # First drop every borrowed result alias, including any extracted records.
    statuses = None
    managed.release_result(result, execution_ledger=ledger)
    managed.release_ticket(ticket, execution_ledger=ledger)
    managed.release_preparation(preparation, execution_ledger=ledger)
    # Only now explicitly finalize the root via the existing managed protocol.
    # After acknowledged finalization, perform lawful root/checkout disposal.

prepare_readiness(execution, required_profile, expectation, /, *,
execution_ledger, capacity=4096) reserves A before request/context construction.
READINESS_RESULT_CAPACITY is 16384 bytes. A and B account for every retained
object/scalar occurrence, including aliased digests/identifiers. Constants are
supported-profile convenience reservations; actual graph validation still applies.
Generic native.prepare remains compatible.

On the successful path, first drop all borrowed result aliases and release
B/result, then ticket, then A/preparation. Only after these releases may the caller
explicitly finalize the root through the existing managed protocol. Follow
acknowledged finalization with lawful root and checkout disposal, and execution
cleanup when its lifetime ends. This successful-path sequence is not permission
to release HELD resources or assume an uncertain operation ended.

No helper finalizes the root or detaches returned statuses from paid B lifetime.
Reuse only healthy fixed checkouts; never replace an uncertain checkout/ledger
to bypass domain stop.

## Failure and startup consumption

Workers completes the gate before W05 or handler admission. Both profiles reject
missing/extra/duplicate/reversed selected components. Malformed binary metadata,
fields or cardinality yield INVALID_OBSERVATION; well-formed wrong
version/digest/format identifiers yield SCHEMA_MISMATCH. Invalid caller
expectations reject locally before issue with detached errors. Pure
decode_event_rows retains existing semantics.

After issue, mismatch, metadata failure, close failure or unknown physical outcome
can retain HELD resources/uncertainty and may stop the domain. Blocking startup
does not prove clean disposal. A partially started worker retains uncertain
obligations, never reports clean stop without proof, and never claims after a
failed gate. No automatic retry, startup DDL or implicit commit.

An undersized native result publication can report CAPACITY_EXCEEDED with
unconfirmed=False while the actual ledger is uncertain, the domain stopped and
the ticket HELD, with no published result. The exception flag alone does not
establish a clean ledger, rollback, safe retry or refundable backing. Actual
lifecycle state and retained obligations remain authoritative.

## Transport and bounds

Fixed binary transport prepends cap_ok BOOL to six canonical columns. TEXT travels
as bounded UTF-8 BYTEA: component 7 bytes, each identifier 256 bytes; digest 32 bytes,
version four-byte int4. Maximum admitted cell payload: 812 bytes per row.
Third-row sentinel rejects before copying. Final SQL ordering is explicit;
variable outputs are suppressed on cap failure.

The issuer validates field names/OIDs/formats/widths, status/command/rowcount,
exact row count 1/2, no extra result set, cap_ok and semantic bounds before
publication. Raw gates preserve exact types and identities without constructor
recursion/coercion hooks.

## Verification boundary

Independent source review and bounded standalone E33 native QA cover eight
completed cases across three reviewed attempts: original two successes,
continuation five negatives and final one undersized-result case. This is not a
single clean eight-case run; the original failed harness attempts remain part of
the evidence.

Actual READ ONLY events/workers profiles returned exact statuses and order, with
no implicit finalization, successful caller-acknowledged rollback/commit on the
same physical checkout, and clean managed disposal on successful paths. Missing
events/workers receipts, digest mismatches for both profiles and an events
version mismatch failed closed with retained HELD obligations. The undersized
workers result confirmed the error-flag/lifecycle distinction described above.
The exact isolated fixture was subsequently confirmed absent after reviewed
graceful cleanup; physical disposal did not refund logical HELD obligations or
prove an original managed rollback.

Pure checks additionally cover raw entry, binary metadata/order/cardinality
forgeries, A/B exact/one-byte-short/alias accounting and constructor bounds.
Impossible-table variants remain structural evidence, not actual table-state
qualification. Test-only receipts do not certify production migration digests,
installation receipts or grants.

Full Worker startup, partial-startup cleanup, claims and registered-handler
integration remain separate qualifications. Standalone E33 evidence does not
establish those outcomes or full product readiness.
