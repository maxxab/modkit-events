# E24 publication intent implementation plan

**Goal:** Persist a stable publication intent under the current live exact fence before external I/O.
**Architecture:** Reuse the existing digest row mutex and one E28 preimage validator. Change only claimed state, intent_id and updated_at, preserving ownership and immutable event material, and append one history record.
**Tech stack:** Existing PostgreSQL SQL resource and Python source guards, followed by a separately reviewed bounded PostgreSQL 18.1 fixture.
**Spec:** Original MODKIT-IMPLEMENTATION-PLAN.md milestones B and D; current catalog E24, PublicationFence bindings and publication transition contract.

## Scope and manual trace
1. E24 accepts event_id bytea, token uuid, ownership_revision int8 and intent_id uuid, and returns exactly one ok bool. READ COMMITTED is required first (PZ005). Invalid identifier, NULL token/intent or nonpositive revision is PZ006 before storage; zero UUID remains valid.
2. Acquire a blocking digest-only outbox row mutex and use a fresh command snapshot. Missing row or token/revision mismatch is PZ003; any state except claimed is PZ004. Repeated E24 from publishing is not a second transition or an idempotent success.
3. One materialized E28(p_event_id) validates the complete preimage. Persisted corruption retains PZ012 and coherent digest identity collision PZ002. Preserve byte-exact state in retained preimage checks.
4. Like E06 dispatch, reject maximum int8 revision PZ004 to preserve successor headroom for settlement/recovery. Then sample the final database clock and reject an expired lease at equality or later PZ003.
5. Update only state to publishing, supplied intent_id and updated_at. Retain token, revision, lease, immutable event material, receipt and outcome evidence. The existing UNIQUE intent constraint rejects reuse across events with native 23505, as existing dispatch uniqueness does; do not suppress failures or add a registry.
6. Verify the whole returned postimage, insert exactly one publication_intent history with supplied intent, NULL operation/receipt, empty evidence/binding and the same final time, then return TRUE. Caller owns commit and must confirm it before I/O; this SQL never commits or calls a provider.

## Approaches and constraints
Reuse the existing outbox state machine and uniqueness constraint. A new intent registry or cross-event mutex framework adds unnecessary machinery; permissive retries would invent a transition absent from the contract. The selected conventional approach follows E06/E23 and keeps one atomic mutation.
Preserve all baseline SQL bytes and Work/E04/job-material behavior. No E10 runtime, native transport, shared services, ERP, dependency installation, new branch/worktree, production grants/readiness, version or publication. Original A-O plan, including final ERP retirement, remains open.

## Review focus and implementation steps
- [x] Add source contract guards in tests/test_publication_intent_sql.py; run them RED for missing E24.
- [x] Append E24 only to src/modkit_events/persistence/sql/0001_initial.sql, update scripts/artifact_policy.py and tests/test_artifact_policy.py explicit inventories, then run GREEN and focused contracts.
- [x] Add docs/sql-candidates/e24-publication-intent/{README.md,test_runtime.sql}. Cover public valid-NUL flow, exact full postimage/history, zero UUID, revision headroom, repeated/different intent, cross-event uniqueness, invalid input/fence/state/expiry, and corrupt persisted preimage with whole rejection footprints including sequences.
- [x] Independently review exact source/fixture/runner and close direct/indirect no-E10 paths before one fresh offline bounded runtime. Preserve all failure/uncertain receipts; no blind replay.
- [x] Run available base suite with known unavailable optional Pydantic module excluded and report skips; verify live WIP unchanged.

Final integration: independently review the exact feature artifacts, commit locally, generate CHANGELOG.md and commit it alone. Exact range, clean-scope and committed-byte receipts are retained separately after these operations.

## Verification boundary
Source guards are not runtime proof. No concurrent lock-wait, precise clock-equality, physical I/O, native-driver, E10, full lifecycle or package qualification is implied. After this slice there are 25 authored bodies of 34, not 25 qualified operations. Full package remains NOT_READY.

A second validated database clock after UPDATE rejects an expired lease before history insertion if the unique intent index had to wait. The original transition timestamp remains in the row/history. This does not promise commit-time lease liveness. The two-session unique-index rollback schedule remains unexecuted; this guard is independently source-reviewed.

## Recorded outcome
Source guards: 10 missing-E24 failures then 10 passes. Review found the implicit unique-index wait boundary; its added regression guard failed, then all 11 passed after adding a validated post-update clock before history. The initial focused publication/contracts lane passed 157 tests and 251 subtests. The final available E24 base lane passed 260 tests and 272 subtests with 30 optional skips, excluding unavailable optional Pydantic and separately scoped pure-transport tests. Focused configured Ruff and formatting passed. All 328907 baseline SQL bytes remain unchanged.

Independent exact source, fixture and runner review closed direct and indirect no-E10 paths. One fresh offline PostgreSQL 18.1 attempt passed in 1.26 seconds. Both outer transactions rolled back; schema/roles/prepared transactions/other-client aftermath was 0|0|0|0. Independent actual-result review accepted these receipts and the bounded container configuration. The single fast-stop waiter returned 137 while PostgreSQL itself exited cleanly with code 0 and no OOM. This was reconciled without retry. After independent stopped-state review and a fresh exact-target check, only that new target was removed; ID and name absence checks passed.

The bounded runtime covers public E02/E22/E24 and subsequent E28/E29 observations, full retained postimage/history, zero UUIDs, max-int8-minus-one success and max-int8 rejection, repeated same/different intent, native cross-event unique failure, invalid inputs, stale/expired/nonowned fences, semantic corruption, runtime EXECUTE/private-table privileges and isolation precedence. Whole rejected footprints include sequences. It does not execute the two-session unique-wait rollback schedule or an exact clock-equality schedule. The source-reviewed second clock catches the implicit-wait boundary; no commit-time liveness guarantee is claimed.

Remaining authored operations: E11,E12,E13,E25,E26,E27,E31,E32,E33. E25 publication settlement is a natural next bounded slice after tracing outcome/fence/revision/history contracts. Full package remains NOT_READY.
