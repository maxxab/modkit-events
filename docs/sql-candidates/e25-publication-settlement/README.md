# E25 publication settlement

E25 records a supplied confirmed, rejected or uncertain outcome while the exact publishing token, revision, intent and lease are current. Confirmed becomes published, rejected becomes rejected, and uncertain becomes held. The mutation clears token/lease, increments ownership revision once, retains event/intent material, stores the supplied receipt/evidence and appends one corresponding history record.

Receipt is nullable and bounded to 4096 bytes; evidence is nonnull and bounded to 1048576 bytes. Empty bytes are valid. These bytes are opaque: callers must classify confirmation according to their required durability policy, including any broker persistence acknowledgement. SQL does not verify external delivery or authorize provider replay. Insufficient durability must be classified uncertain by the caller.

An old-fence repeat is PZ003 after release. Mismatched current intent is PZ003 after full E28 preimage validation. Claimed is not publishing and gives PZ004 with an otherwise current fence. Maximum revision is rejected before arithmetic; maximum-minus-one may settle to maximum. There is no settlement operation-ID repeat record or retry-to-pending branch. Reconcile uncertain commits with retained observations; TRUE is a staged response, not commit acknowledgement.

## Verification scope

The source guards cover exact catalog ABI/security, caller inputs, blocking digest mutex/fresh fence, one E28 preimage, intent, revision overflow, validated clocks, complete postimage and one history insertion. The separate SQL fixture covers actual sequential behavior after independent exact-source/fixture/runner review. It exercises the public E02/E22/E24/E25 valid-NUL chain, all outcomes, zero UUID, boundary receipt/evidence, full row/history preservation, old-fence repeats, invalid arguments, stale/expired/claimed/unowned fences and semantic corruption. All rejected calls compare relevant tables and sequences.

One independently reviewed bounded PostgreSQL 18.1 runtime passed; independent actual-result acceptance is recorded. No concurrent schedule, exact clock-equality execution, physical publication/durability, native driver, E10, full migration or complete package qualification is claimed. The post-update liveness check precedes history allocation but is not a commit-time guarantee. Production manifests/grants/readiness remain unchanged; full package NOT_READY.

## Recorded outcome

Source TDD: 16 expected missing-E25 failures, then 16 passes. Focused publication/contracts coverage passed 174 tests and 256 subtests. During a coordinated stable window the available base suite passed 642 tests and 277 subtests with 59 optional skips; the unavailable optional Pydantic module was excluded. This lane included separately scoped lifecycle source/tests already present at that point. Focused configured Ruff, formatting and whitespace checks passed. The first focused command had a missing test-file path and ran no tests; correcting the path produced the recorded passing run.

All 335098 baseline SQL bytes are unchanged, with one 7506-byte E25 append. Independent design, exact source/fixture/runner and direct/indirect no-E10 reviews passed before runtime. One fresh offline PostgreSQL 18.1 run passed in 5.38 seconds with empty stderr, both PASS markers once, two outer transactions rolled back and zero schema/roles/prepared-transactions/other-client aftermath. Independent actual-result review accepted the exact target configuration and results.

The single fast-stop waiter returned 137 while PostgreSQL itself exited cleanly with code 0 and no OOM. Independent review reconciled the stopped-state receipts and clean shutdown log; no retry occurred. After that acceptance and a fresh identity check, only the exact stopped target was removed. Exact ID and name absence were verified. Local committed-byte closure is recorded separately.

There are 26 authored Events operations of 34, not 26 qualified operations. Remaining E11/E12/E13/E26/E27/E31/E32/E33 and the original A-O integration and final ERP retirement gates remain open. No concurrent schedule, exact clock-equality, coherent hash-collision construction, physical publication/durability, native transport or full package/release qualification was performed. Full package NOT_READY.
