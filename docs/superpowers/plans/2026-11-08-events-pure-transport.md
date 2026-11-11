# Events pure transport prerequisite implementation plan

**Goal:** Bring the already reviewed pure E14/E28 SQL plans and binary row decoder into the private Events checkout as a bounded prerequisite to the common execution adapter.
**Architecture:** Preserve the exact V28/V30 module and tests. Reuse the existing canonical statement identities, raw validators and typed column decoder. Do not add a controller, runtime adapter, driver dependency, public export or Workers import.
**Tech stack:** Python 3.12, standard library, existing pytest and Ruff.
**Spec:** Existing common-native design; independently accepted V28/V30 pure source; original milestone B transaction rules. Native execution remains held.

## Scope and manual trace

Owner: /root/advance_events_next/implement_common_execution_seam. Initial private HEAD 81970b01314bcbe904296f1764b54c49b83fc1c8, branch wip/reviewed-standalone-20261107. Start date 2026-11-08 UTC. Observed compactions 0; only explicit notices are reliable. E24 owns SQL and the Git index until it explicitly releases them.

The accepted packet is /home/faris/modkit-local-20261106/foundation/continuation-v3/dot-events-review-20261107. Import only pure-binary-transport-v30/after-native_codec.py, its after-test_native_binary_transport.py, and pure-sql-descriptor-v28/after-test_native_sql_descriptor.py. The protected live checkout remains read-only. Seven existing production dependency files match the V30 acceptance pins byte for byte.

Trace before checks:
1. Canonical E14/E28 identity and raw statement shape are validated before descriptor selection. All other descriptors reject, including W01-W05. Fixed immutable descriptors retain explicit SQL, casts, canonical column identities, physical metadata, payload caps and a two-row cardinality sentinel.
2. The row helper consumes already copied exact bytes/None in an exact tuple. cap_ok must be the single true byte. Complete type/nullability/width/cap preflight precedes any scalar conversion.
3. Network integer/UUID, strict UTF-8 and bounded integer-microsecond UTC conversions produce the canonical tuple, then existing raw column validation checks it. Unexpected exceptions propagate unchanged. No public sanitizer substitutes a different primary.
4. Complete Outbox/request coupling, driver-result metadata/cardinality before copying, pre-copy SQL cap execution, transaction/resource ownership, cleanup and physical allocation/drop are outside this helper. No SQL or driver call occurs.

This is useful shared preparation but does not provide the Workers B-Store runtime seam. Workers needs actual same-root admission and complete typed results for W01-W05, with W04 expected_submission comparison-only, no separate W05 reconstruction reads, and explicit failure/uncertainty handling. Events must remain independently installable.

## Files and steps

- [x] Verify the independent V28/V30 receipts, exact frozen file hashes and seven existing dependency hashes.
- [x] Copy only the descriptor test first; observe its missing-module assertion fail.
- [x] Add exact accepted native_codec.py and binary transport test; run both focused test files.
- [x] Coordinate explicit package/support inventory additions with the E24 owner; released baseline e95e5f8dc303728e9475ba72511d8e78775f22d0.
- [x] Independently review the pure source and design direction, including original acceptance limitations; final inventory integration remains pending.
- [x] Run applicable contract, artifact, standalone and available base tests with the existing optional Pydantic exclusion. Report skipped optional tests separately.
Final integration gate: independently review the final inventory additions and documentation, stage exact feature paths, create a local Conventional Commit and generated CHANGELOG-only follow-up, then validate range and changelog. Final commit/clean-tree receipts are recorded externally in NEXT-HANDOFF.md and final-result.json after these operations.

New paths: src/modkit_events/persistence/native_codec.py, tests/test_native_sql_descriptor.py, tests/test_native_binary_transport.py, and this plan. Shared inventory changes are scripts/artifact_policy.py and tests/test_artifact_policy.py only after ownership coordination. Evidence is external under /home/faris/modkit-local-20261106/events-pure-transport-20261108.

## Native lifecycle decision and next steps

Origin review found that the universal no-driver-cleanup promise came from an internally selected lifecycle design, not a direct user requirement in the original product plan. The standard supported psycopg lifecycle is selected as the next design direction, preserving adapter-owned no-hidden begin/commit/rollback/swap, sticky uncertainty, received-primary identity, explicit caller transaction control and no refund while work runs.

The precise source trace, distinction between driver emergency close and a Modkit receipt, diagnostic-privacy requirements, consumer contract and future tests are in ../specs/2026-11-08-events-native-execution-design.md. That design still needs independent review before native implementation. This pure port neither changes driver behavior nor qualifies a controller, native operation, W01-W05 support, ORM recipe or runtime.

## Review focus and acceptance limits

Review exact provenance, canonical identity rejection, late malformed cells before conversion, strict binary bounds and preserved primary errors. Reuse accepted source evidence without relabeling old executions as current results. No new SQL body, actual native transport, installed artifact, platform matrix or production readiness is proved by pure tests. Full package remains NOT_READY.

## Current author evidence

Descriptor-first RED: 61 expected missing-module failures. Exact frozen module/test port: 341 focused tests pass. Combined codec, persistence contracts and standalone checks: 415 pass. Ruff check and format check pass for all three Python files. Exact dependency and copied-source hashes plus full command/stdout/stderr receipts are retained in the external evidence directory. Available private base suite: 601 passed and 272 subtests passed, with 30 optional skips and the known unavailable optional Pydantic test excluded. Final artifact inventory RED rejects both wheel and sdist fixtures as unreviewed members. After three explicit entries in each independent inventory, affected artifact/codec/standalone checks pass 384 tests and 255 subtests. Final independent integration review and local commit receipts are recorded separately.

Independent review accepts bounded pure source and the internal native-design direction separately. It independently ran 341 focused tests and Ruff lint/format successfully, verified the copied source and all seven dependency pins, and preserved actual native/driver/privacy/accounting/runtime gates. Receipt: /home/faris/modkit-local-20261106/events-pure-transport-20261108/independent-review.md.

No SQL bytes changed in this feature. E24 ownership release was explicit. The port retains three exact reviewed source/test files; documentation records a design direction, never an implemented native executor or Workers readiness.
