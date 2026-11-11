# E25 publication settlement implementation plan

**Goal:** Record one supplied publication outcome under the live exact publication fence and intent.
**Architecture:** Follow E23/E24's digest row mutex, fresh snapshot, E28 preimage and complete postimage checks. Release ownership, advance revision once, retain immutable event/intent material, and append one outcome history atomically.
**Tech stack:** Existing PostgreSQL SQL resource and Python source guards, then independently reviewed bounded PostgreSQL 18.1 SQL fixture.
**Spec:** Original implementation plan milestones B/D; catalog E25, PublicationFence, binding scalar domains, publication transitions, outbox and history constraints.

## Manual trace and decisions
1. Require READ COMMITTED (PZ005), then valid nonblank UTF8 event ID up to 256 bytes, nonnull token/intent, positive int8 revision, exact status confirmed/rejected/uncertain, nullable receipt up to 4096 bytes, and nonnull evidence up to 1048576 bytes (PZ006). Zero UUID and empty evidence/receipt are valid structural inputs. The ABI supplies opaque evidence, not a verifiable durability certificate; callers classify confirmed only after their required durability policy and uncertain for insufficient durability.
2. Acquire blocking digest-only outbox mutex. Read a fresh locked row. Absent or mismatched token/revision gives PZ003; not publishing gives PZ004. Validate the complete preimage once with E28 before mutation, preserving PZ012 corrupt records and PZ002 coherent identity conflicts. A mismatched intent is PZ003: it does not identify the currently owned publication attempt.
3. Reject int8 maximum revision PZ004 before arithmetic; compute old+1. The final validated database clock is sampled after blocking lock and preimage validation, and expiry at equality or later is PZ003.
4. Map confirmed to published/publication_confirmed, rejected to rejected/publication_rejected, uncertain to held/publication_uncertain. Clear token/lease; increment revision; store supplied receipt/evidence exactly; retain intent and event material; set updated_at to final time. Verify full returned row. No retry-to-pending transition exists here.
5. Retain a validated post-update clock/expiry guard before history allocation. Unlike E24, the unique intent value does not change, but this maintains the same final mutation boundary without claiming commit-time liveness. Insert one history with retained event/intent, NULL operation, supplied receipt/evidence, empty binding and the same transition timestamp. Return exactly TRUE, not commit acknowledgement.
6. Repeating E25 with the old fence fails PZ003 after ownership is released. There is no operation ID/repeat record in this ABI. Unknown commit outcomes must be reconciled; no automatic replay or external I/O is authorized.

## Approaches and constraints
Use the conventional locked row mutation and existing history table. A new registry, provider evidence parser or retry engine would invent contracts and add unnecessary complexity. Preserve every baseline SQL byte and unrelated controller changes; no Work/E04/job-material edits, E10 runtime, native transport, installation, production grants/manifests/readiness, shared service/ERP work, branch/worktree, version or publication.

## Steps and review focus
- [x] Independently challenge the settlement contract and manual trace before source implementation.
- [x] Add tests/test_publication_settlement_sql.py ABI/input/fence/preimage/revision/time/postimage/history guards and observe missing-E25 RED.
- [x] Append only E25 SQL and update both explicit artifact inventories; run GREEN and focused publication/contracts checks.
- [x] Add docs/sql-candidates/e25-publication-settlement/{README.md,test_runtime.sql}. Cover public E02/E22/E24/E25 chain, all outcomes, zero UUID, max-minus-one revision, NULL/empty/boundary byte evidence, exact history, unrelated state preservation, repeats, mismatched intent and stale/expired/nonowned/corrupt rejection footprints including sequences.
- [x] Independently review exact source, fixture, runner and direct/indirect no-E10 graph before one fresh isolated offline runtime. Preserve failure/uncertainty; no blind replay.
- [x] Run available base tests, configured focused Ruff/format, and preserve live checkout. Disclose unavailable optional Pydantic and any concurrently unfinished test scope.
- [x] Obtain independent actual-result and exact-source acceptance.

Final integration uses a scoped feature commit followed by generated CHANGELOG-only commit, explicit range/changelog validation and exact committed-byte comparison; receipts are retained separately.

## Verification boundary
Source guards are not runtime proof. Bounded sequential runtime does not qualify concurrency, exact clock equality, physical publication/durability, native drivers, E10, full migration or release. This would be 26 authored of 34 operations, not fully qualified operations; E11/E12/E13/E26/E27/E31/E32/E33 and original A-O/final ERP retirement remain open. Full package NOT_READY.

## Recorded outcome

Source TDD: 16 expected missing-E25 failures, then 16 passes. Focused publication/contracts coverage passed 174 tests and 256 subtests. During a coordinated stable window the available base suite passed 642 tests and 277 subtests with 59 optional skips; the unavailable optional Pydantic module was excluded. This lane included separately scoped lifecycle source/tests already present at that point. Focused configured Ruff, formatting and whitespace checks passed. The first focused command had a missing test-file path and ran no tests; correcting the path produced the recorded passing run.

All 335098 baseline SQL bytes are unchanged, with one 7506-byte E25 append. Independent design, exact source/fixture/runner and direct/indirect no-E10 reviews passed before runtime. One fresh offline PostgreSQL 18.1 run passed in 5.38 seconds with empty stderr, both PASS markers once, two outer transactions rolled back and zero schema/roles/prepared-transactions/other-client aftermath. Independent actual-result review accepted the exact target configuration and results.

The single fast-stop waiter returned 137 while PostgreSQL itself exited cleanly with code 0 and no OOM. Independent review reconciled the stopped-state receipts and clean shutdown log; no retry occurred. After that acceptance and a fresh identity check, only the exact stopped target was removed. Exact ID and name absence were verified. Local committed-byte closure is recorded separately.

There are 26 authored Events operations of 34, not 26 qualified operations. Remaining E11/E12/E13/E26/E27/E31/E32/E33 and the original A-O integration and final ERP retirement gates remain open. No concurrent schedule, exact clock-equality, coherent hash-collision construction, physical publication/durability, native transport or full package/release qualification was performed. Full package NOT_READY.
