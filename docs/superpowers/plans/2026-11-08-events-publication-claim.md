# E22 bounded publication claim

Owner: implement_publication_claim under advance_events_next, ownership v1. Independent review: /root/advance_events_next/review_publication_claim. Dot platform-managed settings. Zero observed compactions; supported-notice tracking.

## Scope and manual affected-flow trace
Existing catalog E22 has four arguments (limit int4, lease_seconds float8, scan_after nullable bytea32, discovery_budget int4) and a 17-column header/item scan ABI. Bindings require limit 1..256, budget 1..4096 and budget>=limit, finite positive lease<=3600. Header reports visited raw identities, last visited digest, true exhaustion only after a query observes end before either bound. Items are strictly digest ordered, at most limit, and claimed OutboxRow observations. Preserve the original A–O plan and NOT_READY boundary.

E02 reserves immutable full event identity and pending revision0, then enqueue history. Cooperative outbox writers preserve identity/replay/creation and use the same outbox row mutex. E28 is the existing complete snapshot validator: digest identity, canonical envelope/replay, state/ownership/intent/time/byte shape. E29 validates append-only history; claim_publication has no intent/operation/receipt and empty generated evidence/binding. E26 alone reclaims expired owned rows. No external publication or commit certainty follows from E22.

## Minimal design
Reuse E04's conventional bounded loop: scan all outbox identities by digest PK (NULL cursor first, then strict keyset), count each raw identity before eligibility/lock checks, skip nonpending states, take FOR NO KEY UPDATE SKIP LOCKED on the digest. If a candidate vanishes, fail PZ012 under cooperative no-delete semantics. Retain and compare full identity after locking. One fresh E28 observation validates the complete preimage before mutation; no postwrite STABLE reader.

Quantize positive binary64 seconds to ceiling integer microseconds using the existing E04 exact algorithm. No helper refactor or floating multiply approximation. Skip exhausted revision>=int8max-1 as E04 does, preserving a successor. After all locks/validation sample database time, ensure supported nonempty lease, allocate UUID and successor revision. Update only state/token/revision/lease/updated_at, compare exact retained postimage, append exactly one claim_publication history. Buffer retained rows and return header first. Native errors propagate; no retry or transaction control.

Alternatives: one bulk SKIP LOCKED query obscures visited locked/ineligible identities and cursor semantics; duplicating E28 validation risks contract drift. Existing E04 loop plus E28 is the smallest normal fit. This is the implementer's choice under delegated routine engineering authority.

## No-E10 closure and tests
E22 -> E28 -> immutable byte/replay/time helpers. outbox UPDATE has no triggers; publication_history INSERT has checks/FK and no INSERT trigger; immutable history trigger is UPDATE/DELETE only. No work/finalization_guard/attempt writes. Defining E10 in a disposable migration does not execute it. Independent source and exact fixture review must close this graph before any database check.

Write source ABI/security/bounds/ordering/lock/lease/history/projection tests first, record meaningful missing-E22 RED, append implementation and explicit test inventory, run focused source checks. Preserve prior accepted tests; later full base checks use existing venv and documented optional Pydantic exclusion/Redis skips.
Prepare a small SQL fixture for actual paging, valid public enqueue-to-claim, invalid-input no-write rejection, corrupt selected preimage, expiry nonreclamation, upper bounds and revision exhaustion; separate controlled two-session lock skip/claim exclusion. Fresh offline PostgreSQL18.1 only after independent fixture/no-E10 acceptance. Never replay old runners or consumed targets. Keep all failure evidence, reconcile before cleanup/retry.
Review final delta, then local feature commit and generated CHANGELOG.md-only commit on existing branch; validate range/changelog/clean tree and live-byte preservation.

## Boundaries
No E10 runtime, native driver, existing shared service, network/pull/install/build, ERP, Worker dependency, production manifest/grants, version/readiness/push/tag/publication changes. Physical IO plans, all concurrency schedules, native/lifecycle/full release qualification stay unclaimed. Evidence directory is outside product checkout; full package NOT_READY.

## Current outcome
E22 source completed after meaningful missing-function RED. Independent E22-R1 corrected stored-ID PZ006/PZ012 classification via a narrow pre-E28 guard and its own RED/GREEN regression. Final focused123+249 subtests and base239+270 subtests passed,30 optional skips with known optional Pydantic exclusion. Existing SQL prefix remains byte-identical.

Fresh offline runtime attempt1 stopped on a fixture-only JSON operator-precedence error. Read-only rollback was0|0|0|0; exact target exited0/noOOM with clean shutdown and was removed after independent reconciliation. Consumed evidence remains unchanged.
Attempt2 passed the complete bounded fixture, ACL/isolation and real two-session contention schedule in15.34s. One holder claimed/locked first digest while contender skipped it and committed the second; both committed and no duplicate claim occurred. Independent runtime-result acceptance passed. The exact v2 fixture was removed, zero-aftermath confirmed, and its container cleanly stopped/removed after exited0/noOOM/shutdown-log reconciliation. Both consumed targets are absent. Live HEAD/index/status/tracked/untracked hashes match the before snapshot. Final docs/source acceptance and local feature+changelog-only commits, commit-range/changelog verification and clean-tree closure remain integration steps, recorded only after their receipts exist.

There are23 authored Events operations once this slice is committed, not23 fully qualified operations. Remaining E11,E12,E13,E23,E24,E25,E26,E27,E31,E32,E33 and wider original A–O gates stay open. E23 publication renewal is a natural next isolated slice after tracing fence/time contracts.
