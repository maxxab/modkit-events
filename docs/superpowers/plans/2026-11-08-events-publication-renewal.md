# E23 publication renewal implementation plan

**Goal:** Implement the existing E23 exact publication-fence renewal contract, without recovery or unrelated changes.
**Architecture:** Reuse the outbox row mutex and one E28 preimage validator. Apply E05's exact binary64 lease quantization and nonshortening renewal, retaining the complete postimage.
**Tech stack:** Existing PostgreSQL SQL resource and Python source tests; fresh isolated PostgreSQL 18.1 fixture only after independent no-E10 review.
**Spec:** Original MODKIT-IMPLEMENTATION-PLAN.md milestone D, current catalog E23, PublicationFence bindings, transitions.py, E05/E22/E28/E29.


## Scope, manual trace and design
1. E23 accepts event_id bytea, token uuid, ownership_revision int8 and lease_seconds float8, returning exactly one lease_until timestamptz. Reject unsupported isolation PZ005 first, then invalid UTF-8/nonblank/256-byte ID, NULL token, nonpositive revision and nonfinite/nonpositive/>3600 lease PZ006 before storage.
2. Quantize the represented positive binary64 duration to ceiling microseconds, byte-identically to E05/E22. Lock the digest identity FOR NO KEY UPDATE, with no full-ID filter or SKIP LOCKED; absent row is stale PZ003. A new command snapshot after blocking acquisition checks token/revision PZ003 and claimed|publishing state PZ004.
3. One materialized E28(p_event_id) validates the entire preimage under the mutex. Caller ID was already validated; stored corruption remains PZ012 and coherent different-ID digest aliases PZ002. Compare retained raw rows and exact state bytes. No postwrite STABLE reader. Initial identity-as-stale shortcut was rejected during independent design challenge.
4. Sample database time only after lock and integrity checks. Expiry equality or later is PZ003. Candidate lease is max(old lease, now + quantized duration), checked for supported time/nonempty interval. Outbox has no deadline. No successor revision is needed, even at int8max. E26 alone owns expired-lease reclamation.
5. UPDATE only lease_until and updated_at, verify complete retained postimage; retain token, revision, state, optional intent, immutable event material and optional receipt/evidence. Append exactly one renew_publication history with retained optional intent, NULL operation/receipt, empty evidence/binding and the same final time. Return the retained lease. Caller owns transaction outcome.

## Constraints and review focus
Existing 321406 SQL bytes, Work/E04/job-material, Workers files, live WIP and original A–O/ERP retirement scope remain unchanged. W05 acknowledged its frozen Events 60eac7a snapshot. No branch/worktree, native transport, E10 execution, shared service, ERP, dependency install/pull/build/network, production grants/manifest/readiness, version or publication.
Tests target both eligible states and nonshortening lease; exact token/revision/expiry and ineligible-state precedence; invalid input and malformed preimage full rejection footprints including sequences; exact binary64 edges; full postimage/history and no unrelated writes. Coherent SHA collisions remain source-only without hash mocking. Concurrency, physical IO and full lifecycle qualification remain unclaimed unless separately executed.

## Implementation steps
- [x] Add tests/test_publication_renewal_sql.py for exact ABI/security, input order, digest lock/fresh fence, one E28, exact quantization, retained update and history. Run source RED and save evidence.
- [x] Append minimal E23 only to src/modkit_events/persistence/sql/0001_initial.sql; update explicit authored inventory; run source GREEN and focused contracts.
- [x] Add docs/sql-candidates/e23-publication-renewal/{README.md,test_runtime.sql}. Independent actual source/fixture/runner review must explicitly close no-direct/indirect-E10 graph before any DB test.
- [x] Run one fresh offline PostgreSQL 18.1 bounded fixture using the existing pinned image, no binds/network/install and no old target replay. Retain uncertain/failed results; reconcile before cleanup/retry. Independently review runtime and exact newly owned target aftermath, clean stop and removal.
- [x] Run available base suite with known optional Pydantic exclusion and report optional skips honestly; verify unchanged live bytes.

Final integration gate: independently review the exact seven feature files, commit them locally, generate CHANGELOG.md and commit it alone. The final range, changelog and clean-tree receipts are recorded in the scoped final-result.json and NEXT-HANDOFF.md after those operations.

## Verification boundary
Source tests are source guards, not runtime proof. E23 makes 24 authored bodies of 34, not 24 fully qualified operations. Package remains NOT_READY. Verification receipts are retained outside the product checkout.


## Recorded outcome
Independent E23-D1 design correction preserved E28 integrity/collision ordering. Source tests: 10 RED failures, then 10 GREEN passes; initial focused 147 tests and 249 subtests passed. Available base: 249 tests and 271 subtests, 30 optional skips with known unavailable optional Pydantic exclusion. After standard formatting and explicit artifact inventory changes, 47 tests and 250 subtests passed; focused Ruff lint/format and diff whitespace passed. Existing SQL prefix is byte-identical.

Independent source/fixture/runner/no-E10 review accepted. Fresh offline PostgreSQL 18.1 first attempt passed in 1.30 seconds; both transactions rolled back, aftermath 0|0|0|0 independently accepted. The exact target's single stop returned waiter 137, reconciled with actual exit 0/noOOM/clean shutdown; no stop retry. Independent review accepted the stopped-state receipts. A fresh exact-ID check preceded removal of only the stopped new target; ID and name absence checks passed. Final local feature/changelog-only commit receipts are retained separately after verification.

The runtime covers legitimate public renewal, both eligible states and intent shapes, max-int8 ownership revision and zero UUID, five nonshortening lease vectors, full retained postimage/history, 17 invalid arguments, stale/nonowned/expired fences, three semantic corruptions and owner-injected invalid-state precedence. Tiny durations retain the old lease; no one-microsecond extension is claimed. Equality, two-session waiting schedules, coherent collision and physical IO remain source-only or unexecuted.

Remaining authored operations: E11,E12,E13,E24,E25,E26,E27,E31,E32,E33. E24 publication intent is a natural next bounded slice after its catalog/fence/intent/history trace. Original A–O and final ERP retirement remain open; full package NOT_READY.
