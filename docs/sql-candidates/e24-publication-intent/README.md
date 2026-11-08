# E24 publication intent

E24 changes a live, exactly fenced claimed outbox row to publishing with the caller's stable intent UUID. It retains ownership token, revision, lease and event material and appends one publication_intent history. Maximum int8 revision is rejected to reserve settlement/recovery headroom. The caller must confirm its transaction commit before starting external publication I/O; E24 does not commit or call a provider.

Repeating E24 after the row becomes publishing, including with the same intent, is invalid transition PZ004. Reusing an intent across different events is rejected by the existing UNIQUE constraint as raw SQLSTATE 23505, an untranslated database failure rather than a domain identity diagnosis or proof of safe retry. Reconcile uncertain transaction outcomes using stored state.

## Verification
Source guards cover exact ABI/security, input ordering, blocking digest fence, one E28 preimage validator, revision/time checks, full retained postimage and history. Real behavior is covered by the separate bounded SQL fixture after independent source/fixture review. Source guards passed 11 tests after red/green coverage, and the available E24 base lane passed 260 tests and 272 subtests with 30 optional skips. Known unavailable optional Pydantic and separately scoped pure-transport tests were excluded.

The fixture covers public E02/E22/E24 with valid U+0000; zero UUIDs, maximum revision with successor headroom, retained receipt/evidence; unchanged other outbox rows and prior history; repeated calls and cross-event duplicate intent; invalid arguments, stale and expired fences, exhausted revision, nonowned states and semantic preimage corruption. Every rejected call checks all relevant rows and sequence state. No E10 execution is needed.

No concurrent schedule, runtime exact-expiry-equality assertion, physical I/O, native-driver, full publication lifecycle or complete migration/package qualification is claimed. Production manifests/grants/readiness stay unchanged. Package remains NOT_READY.

A second validated database clock after UPDATE rejects an expired lease before history insertion if the unique intent index had to wait. The original transition timestamp remains in the row/history. This does not promise commit-time lease liveness. The two-session unique-index rollback schedule remains unexecuted; this guard is independently source-reviewed.

## Recorded outcome
Source guards: 10 missing-E24 failures then 10 passes. Review found the implicit unique-index wait boundary; its added regression guard failed, then all 11 passed after adding a validated post-update clock before history. The initial focused publication/contracts lane passed 157 tests and 251 subtests. The final available E24 base lane passed 260 tests and 272 subtests with 30 optional skips, excluding unavailable optional Pydantic and separately scoped pure-transport tests. Focused configured Ruff and formatting passed. All 328907 baseline SQL bytes remain unchanged.

Independent exact source, fixture and runner review closed direct and indirect no-E10 paths. One fresh offline PostgreSQL 18.1 attempt passed in 1.26 seconds. Both outer transactions rolled back; schema/roles/prepared transactions/other-client aftermath was 0|0|0|0. Independent actual-result review accepted these receipts and the bounded container configuration. The single fast-stop waiter returned 137 while PostgreSQL itself exited cleanly with code 0 and no OOM. This was reconciled without retry. After independent stopped-state review and a fresh exact-target check, only that new target was removed; ID and name absence checks passed.

The bounded runtime covers public E02/E22/E24 and subsequent E28/E29 observations, full retained postimage/history, zero UUIDs, max-int8-minus-one success and max-int8 rejection, repeated same/different intent, native cross-event unique failure, invalid inputs, stale/expired/nonowned fences, semantic corruption, runtime EXECUTE/private-table privileges and isolation precedence. Whole rejected footprints include sequences. It does not execute the two-session unique-wait rollback schedule or an exact clock-equality schedule. The source-reviewed second clock catches the implicit-wait boundary; no commit-time liveness guarantee is claimed.

Remaining authored operations: E11,E12,E13,E25,E26,E27,E31,E32,E33. E25 publication settlement is a natural next bounded slice after tracing outcome/fence/revision/history contracts. Full package remains NOT_READY.
