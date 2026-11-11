# Canonical Controller Backing Implementation Plan

**Goal:** Integrate the accepted controller and add paid typed backing with explicit running/held release invariants.
**Architecture:** Extend the existing managed_lifecycle records and gate. Reuse raw E14/E28 request/result validators and retain legacy bytes controls.
**Tech Stack:** Python 3.12, existing pytest and Ruff, standard library only.
**Spec:** ../specs/2026-11-08-events-controller-backing-design.md

## Constraints and manual trace

No native driver/database run, SQL change, new runtime authority, install, service, ERP edit, publication, branch or worktree. Follow the earlier native design's actual product invariants. The manual source trace follows configure -> X -> P/C -> R -> A -> OP -> B -> completion/release. The initial gaps were bytes-only backing and missing running protection. Task 2 closes those gaps within the existing controller.

## Task 1: Integrate accepted dependency closure

- [x] Verify five frozen production modules, two tests, and existing dependency hashes.
- [x] Copy tests first and observe the missing-controller failure.
- [x] Copy exact accepted modules and run lifecycle source tests: 25 passed, 29 optional native skips.
- [x] Independently check integration and combine with the coherent extension below.

Files: persistence/ledger.py, resource_registry.py, resource_lifecycle.py, managed_lifecycle.py, native_sync.py; tests/test_resource_lifecycle.py and tests/test_managed_lifecycle.py.

## Task 2: Typed backing and operation lifecycle

- [x] Review the bounded design independently before implementation.
- [x] Add tests/test_managed_statement_lifecycle.py using existing process-isolated structural fixtures, with larger explicit backing capacities.
- [x] Observe RED for exact typed FrozenRequest, complete typed E14/E28 result backing and one-byte capacity overflow.
- [x] Extend the existing setters, finite graph size checks, selected result stamp and populated marker.
- [x] Observe RED for start/completion/hold, wrong identity and running release barriers.
- [x] Add _start_operation(ticket, result, ledger), _hold_operation(ticket, ledger), _complete_operation(ticket, ledger, known=...), and read_result(result, execution_ledger=...); preserve held charges and received unexpected exceptions.
- [x] Run focused GREEN and review normal, absent, malformed, interrupted, late-completion and release paths.

## Task 3: Verify and close

- [x] Coordinate both inventories for the one new test path after exclusive ownership release.
- [x] Run focused lifecycle/codec/contracts and relevant artifact/standalone checks.
- [x] Run available base suite, reporting known optional Pydantic absence and all native skips.
- [x] Run Ruff lint/format and exact diff checks.
- [x] Obtain fresh independent exact-source code and QA review.
Local closure uses an explicitly scoped reviewed feature commit followed by a generated CHANGELOG-only commit, both with per-command Codex author identity. Exact committed-byte equality, commit scope/author/range, deterministic changelog and final ownership state are recorded after those commits rather than asserted in advance here.

## Review focus

1. All typed payload bytes and containers remain charged, rather than serialized placeholders.
2. None is a populated optional result and cannot evade completion checks.
3. Cancellation does not clear running; late success cannot undo HELD/UNKNOWN.
4. Wrong/stale ticket, result or ledger cannot publish or release another operation.
5. Complete Outbox replay/canonical/request validation happens before exposure, and unexpected exceptions retain construction charge.

## Verified source scope

- Final author lifecycle/artifact checks: 84 tests and 257 subtests passed; 29 optional native tests skipped.
- Final independent lifecycle/codec/artifact checks: 428 tests and 257 subtests passed; 29 optional native tests skipped. Nine additional independent edge/concurrency cases passed.
- Ten-file Ruff lint/format, content privacy, required-member omission rejection and private-document exclusion checks passed.
- Final available base: 678 tests and 278 subtests passed, with 59 optional skips and the known unavailable optional Pydantic module excluded. This run included a concurrent uncommitted E26 source append and fourteen source tests, not independent E26 acceptance or runtime qualification.

Independent review found that public UUID constructor fields can retain mutable is_safe data or an int subclass. Two new regressions first reproduced those invalid graphs. Exact bounded UUID integer storage and canonical SafeUUID singleton preflight now precede sizing/raw validation; the finding is independently closed. Request graph identity, exact UTC fields, full graph capacity, cancellation/late completion, primary exception metadata, and held-release exclusions are covered by source checks.

Bounded controller source is accepted. Actual E14/E28 statement execution, driver metadata/pre-copy bounds and interruption/privacy qualification remain unimplemented or unqualified. No Workers W01-W05, installed-artifact runtime or whole-product readiness claim follows from this work.
