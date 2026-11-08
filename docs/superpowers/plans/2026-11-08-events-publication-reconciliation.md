# E27 Publication Reconciliation Implementation Plan

**Goal:** Resolve held publication as published or rejected with an immutable, exactly repeatable operation record.
**Architecture:** Reuse the existing outbox mutex and E28 full preimage validator. Reserve the global operation UUID with INSERT ON CONFLICT DO NOTHING, validate the stored complete request, and let only the insertion winner change outbox/history.
**Tech Stack:** PostgreSQL PL/pgSQL and Python source-contract tests.
**Spec:** Existing catalog E27, pure bindings, RepairObservation, mutation_operations typed union and publication transitions, within the original persistence/reconciliation milestones.

## Scope and constraints
Append only to src/modkit_events/persistence/sql/0001_initial.sql. Add tests/test_publication_reconciliation_sql.py and docs/sql-candidates/e27-publication-reconciliation/README.md. This plan is the fourth owned path. The two artifact inventories received only the exact new E27 test entry after explicit ownership transfer. No common controller/codec/bindings or grant/manifest change is included; Git index and CHANGELOG remain separately gated integration resources.
Preserve the 352460-byte preceding SQL and 321406-byte W05 prefixes. Require caller-owned READ COMMITTED and fixed SECURITY DEFINER search path, with PUBLIC EXECUTE revoked. No provider I/O, automatic retry or transaction control.

## Manual trace and selected behavior
Seven inputs return the existing nine-field RepairObservation. Validate all inputs before relation access: UTF-8 event ID<=256 bytes, nonnegative expected revision, UUID, exact published/rejected status, nullable receipt<=4096, nonnull evidence/binding<=1048576.
Digest-only blocking lock and fresh snapshot precede E28 complete identity/replay validation. Missing target is PZ003; corruption is PZ012; coherent full-ID collision is PZ002.
Read the registry before checking current revision or state. Validate complete repair union, irrelevant nulls, digest, bounded bytes, timestamp and numeric successor. Compare every submitted field exactly, including nullable receipt and byte-exact status. A conflicting known operation kind/request is PZ002; malformed repair/unknown kind is PZ012.
A valid exact repeat returns the original observation without clock, history or row mutation, even after revision/state changed. Current outbox structural integrity is still checked. Registry absence requires current revision (PZ003), held state (PZ004) and nonexhausted revision (PZ004).
Reserve the operation before updating outbox. A unique conflict may wait; the loser reads a fresh command snapshot and compares the persisted request. Only insertion winner mutates. Preserve full event/replay/intent/creation, set status/revision+1/receipt/evidence/time, validate the whole RETURNING row, append one complete repair history using the same timestamp, and return the retained registry row.
The immutable operation is the original result authority; no unbounded history scan or new history index. It does not prove an external effect. E27 can mutate if an earlier operation was absent, so it is not a read-only uncertainty probe. Caller-held multiaction locks may deadlock; native failures propagate without retry.

## Review focus
- Concurrent same-event repeat and different-event shared operation UUID.
- Original observation/timestamp, exact request identity, null versus empty receipt.
- Corrupt preimage/operation before success and overflow without partial writes.
- Complete immutable material preservation and one atomic operation/history transition.
- No direct/indirect E10, external publication, grant activation or new transport readiness.

## Steps
- [x] Trace authoritative requirements, catalog, pure bindings, readers/writers, tables and triggers.
- [x] Obtain independent design challenge before dependent tests/implementation.
- [x] Write fourteen source guards and observe all fail because E27 is missing.
- [x] Append E27; fourteen source guards pass.
- [x] Run affected pure/source checks and inspect actual changed bytes.
- [x] Independently review source plus fresh isolated fixture/runner and no-E10 graph.
- [x] Execute only accepted fresh sequential runtime; independent QA and exact cleanup acceptance.
- [ ] Update final evidence and obtain independent current-byte acceptance.
- [ ] Commit locally after explicit index release; separate coordinator-generated changelog.

## Verified outcomes and remaining limits
The focused source selection passed126 tests. Separate independent review passed20 E27/G2 checks and found no blocking source issue. Source guards do not substitute for runtime evidence.

The available source suite passed755 tests plus286 subtests, with60 optional skips. Full collection encountered the existing missing optional Pydantic dependency; excluding only tests/test_contracts_pydantic.py produced that result. Exact test inventory additions passed37 artifact-policy tests plus265 subtests after an observed unreviewed-member RED. No dependency was installed or fail-closed inventory requirement removed.

Separate independent QA accepted the exact source/fixture/runner and no-E10 graph, then one fresh isolated PostgreSQL18.1 sequential attempt passed. Both outcomes, original nine-field observations, exact-repeat no-write behavior, all request-field conflicts, null/empty/max bytes, max-minus-one/max revisions, malformed storage, full postimages/history, default denial/explicit fixture grants, isolation precedence and rollback were exercised. Both outer transactions rolled back, with schema/roles/prepared transactions/other clients at0|0|0|0.

Cleanup independently confirmed actual container exit0, no OOM/error and clean shutdown despite pg_ctl waiter137, without retry. Exact nonforce removal and ID/name absence passed. Live Events WIP remained identical across158 protected files. Final outcome-document/inventory acceptance and committed-byte closure remain separate integration receipts.

Concurrency is NOT_RUN. In particular, same-event repeat and cross-event operation-ID unique waits are source-reviewed, not runtime-qualified. No E10, lawful E31/E32 producer, provider proof/durability, broader native/ORM/Workers, full migration/grant/install or release qualification follows.

Full package remains NOT_READY. This is the28th authored operation of34, not28 qualified operations. E11/E12/E13/E31/E32/E33, original A-O and final ERP retirement gates remain open.
