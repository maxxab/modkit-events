# E27 publication reconciliation candidate

E27 resolves a held publication to published or rejected in the caller-owned READ COMMITTED transaction. It stores an immutable operation request and original RepairObservation. Same-operation exact repeats return that observation without another revision or history entry; conflicting fields or another operation kind fail PZ002.

All seven arguments are checked before locking. Digest-only discovery and E28 validate the complete persisted identity and replay. Missing target is PZ003, corrupt storage is PZ012, and coherent full-ID collision is PZ002. Existing valid repair records are compared before current revision/state eligibility. A new request needs held state and matching revision, with max-int8 refused. Null and empty receipts remain distinct.

Only the global operation-ID insertion winner updates outbox and appends history. A uniqueness wait is followed by a fresh persisted read. The outbox postimage, immutable record and history retain exact opaque bytes and a shared timestamp. Normal deadlocks/timeouts propagate; no internal retry is added.

This records application-supplied reconciliation, not provider proof or commit certainty. An absent original operation can still mutate, so repeating E27 is not a read-only probe and never authorizes external I/O. Existing structural outbox validation still applies to repeats.

## Verification
Fourteen source guards were observed RED on the absent E27 body and GREEN after the append. The focused E24-E27 and pure contract selection passed126 tests. Independent source review passed20 focused E27/G2 checks and accepted the complete SQL append and unchanged prefixes.

The available source suite passed755 tests plus286 subtests, with60 optional skips. The configured full collection is blocked by the unavailable optional Pydantic dependency in tests/test_contracts_pydantic.py; excluding only that module produced the available-suite result. The exact new test inventory entry was accepted after a test-first rejection; artifact policy checks passed37 tests plus265 subtests. These source checks do not establish installation or release readiness.

Separate independent QA reviewed the actual call graph, exact fixture and isolated runner before one fresh PostgreSQL18.1 attempt. The bounded sequential fixture passed both outcomes, exact original observations and repeats, all submitted-field conflicts, byte/revision bounds, invalid/corrupt records, complete row/history preservation, caller rollback and ACL/isolation behavior. Both outer transactions rolled back. Schema, fixture roles, prepared transactions and other clients ended at0|0|0|0.

The exact disposable target shut down cleanly with actual exit0 and no OOM or error. Its pg_ctl waiter137 was reconciled against the stopped state and shutdown log, without retry. Nonforce removal and exact ID/name absence were verified. The consumed runner must not be replayed. Live Events WIP remained byte-identical across158 protected files.

Concurrency is NOT_RUN, including same-event repeat and cross-event global operation-ID races. The sequential result does not qualify E10, lawful E31/E32 producers, native adapters, provider truth/durability, complete migration/grants/install, or release. Final committed-byte acceptance is recorded separately.

The preceding SQL and frozen W05 prefix remain unchanged. There are28 authored operations of34, not28 qualified operations. E11/E12/E13/E31/E32/E33 and the original A-O integration and final ERP retirement gates remain open. Full package remains NOT_READY.
