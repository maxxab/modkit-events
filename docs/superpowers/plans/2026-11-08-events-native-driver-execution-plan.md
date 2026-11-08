# Native E14/E28 Execution Implementation Plan

**Goal:** Execute fixed E14/E28 through the canonical managed gate on the caller root.
**Architecture:** Optional public psycopg issuer, existing paid envelopes and fixed binary codec. Conservatively hold uncertain work without replay or recovery.
**Tech Stack:** Python 3.12, pinned psycopg 3.3.8/libpq 180006, existing PostgreSQL 18.1 disposable image.
**Spec:** ../specs/2026-11-08-events-native-driver-execution-design.md

## Global Constraints

No driver/DB run before independent exact code/profile/fixture acceptance. No E10 dependency, private wait override, extra controller, automatic transaction/finalization, new dependency, public publication or protected live-checkout edits. Local verification does not authorize publication or whole-product readiness.

## Review Focus

- Returned exception while original driver is ACTIVE must keep running and held.
- Rejected result after real execution is unknown, never a retry.
- Empty E28 observation is a populated result, not an unset slot.
- Raw decoder normalization must not replace retained parameter identities.
- Cleanup, logger and ledger failures must preserve exact received primary metadata and no diagnostics leakage.

### Task 1: Implement the issuer

Files: src/modkit_events/persistence/native_execution.py; tests/test_native_execution.py.
Interfaces: prepare(execution, statement, parameters, *, execution_ledger) -> preparation; execute(ticket, result, *, execution_ledger) -> None.
- [x] Independent design review and correction.
- [x] Write source tests that fail for missing prepare/execute. Cover reservation-before-freeze, retained binding identity, exact metadata/cap/cardinality, complete row/coupling and no success on setter failure.
- [x] Run focused RED with saved argv/status/output.
- [x] Implement the public RawCursor path and fixed validation, using existing capture/construction/gate helpers.
- [x] Test failure precedence, transaction/connection/profile rejection, held-running exclusion, callback/privacy and completion races.
- [x] Run focused GREEN and Ruff, then freeze exact source for independent review.

### Task 2: Qualify real bounded observations

Files: tests/native/test_native_observation_integration.py; external private fixture driver and evidence.
- [x] Prepare fresh isolated no-E10 fixture, exact driver/image/SQL/source pins, graph, resource scope and cleanup. Independently review before execution.
- [x] Verify E14 XID same-root business writes, E28 present/absent binding and caller rollback/commit only.
- [x] Verify supported interruption, failed cancel warning, timeout closure and secondary logger/cleanup failure with nonsecret sentinels where actual supported controls permit. Record unqualified cases explicitly.
- [x] Clean only owned disposable resources and independently verify runtime/aftermath.

### Task 3: Integrate and commit

- [x] Add exact product/test inventory entries and prove missing-member rejections/privacy.
- [x] Focused + available regression suite, independent final source/runtime acceptance at exact pins.
- Record the scoped feature and generated changelog in separate local commits; validate their explicit range and current changelog.
- Keep the completion record explicit about native coverage and remaining whole-product limits.

### Final pre-admission correction

- [x] Reproduce one-slot preparation exhaustion and the unreturned-envelope race before changing implementation.
- [x] Reuse one live paid construction across canonical preparation reserve/freeze/set/known cleanup; preserve public contracts and uncertain failures.
- [x] Verify one-slot success, occupied-slot rejection, concurrent pressure, invalid-input and A/AB refunds, foreign/dead/cross-thread owners, and lost reserve/set acknowledgements.
- [x] Independently accept final delta and decide any focused final-byte native observation before teardown.

Actual normal/fault coverage is bounded to the pinned supported profile. Natural cursor-close failure and materialized-payload privacy remain unqualified by the real-driver fault stage.

The final preparation delta passed a focused actual-driver E14/E28 observation with caller rollback and unchanged business state. The disposable fixture was cleaned, shut down without force, and removed. These observations cover only the selected native slice, not full migration or product readiness.
