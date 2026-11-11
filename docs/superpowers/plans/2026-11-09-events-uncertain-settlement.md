# E32 durable uncertain settlement

Independent source review, focused pure controls and the bounded E32 SQL-native packet passed.
Postrun reviewer recheck and documentation closure are pending. Managed native E32 transport
and full product readiness remain unqualified; full product NOT_READY.

## Contract and ownership

The existing E32 catalog ABI is unchanged: a complete Fence, positive failed_business_root,
operation_id, reason, evidence and binding return one thirteen-field SettlementObservation.
The supplied business root is structural context, never proof of rollback, failure or provider no-effect.

A new operation requires coherent running work, its current dispatched attempt, a live exact
fence and a distinct settlement root. It changes work to held, clears token/lease and advances
revision once. The attempt becomes uncertain with exact evidence. Dispatch pointer/count,
available_at, immutable fields and inbox capacity remain unchanged. Exactly one immutable
operation receipt and hold_uncertain history row are recorded. There is no failure, retry,
terminal resolution or guard satisfaction.

An exact recorded request returns the validated original receipt before current fence/state/time
eligibility. It neither reapplies changes nor grants effect replay. Changed request fields or
another valid operation kind under the same global ID conflict with PZ002. Corrupt receipt
fields fail PZ012. All typed-union fields, including irrelevant null fields, are checked.

## Locks, clocks and errors

Protected E15 discovery precedes parent (inbox), work and current-attempt NO KEY UPDATE locks.
A fresh single-statement E15/preimage observation follows those locks. Existing receipt handling
precedes new-operation eligibility. New-operation stale fence is PZ003; nonrunning work or
structurally unsuitable roots/revision exhaustion are PZ004. Positive parent count is checked
only after exact running classification, preserving E11's terminal-count-zero correction.
Malformed arguments are PZ006 and unsupported isolation is PZ005.

record_time is sampled after coherent locked preimages, before the immutable operation INSERT.
The receipt, work.updated_at and history.recorded_at share that value unchanged. This is
historical recording time, NOT final fence, commit or durability time.

A separate fresh authority_time after global-ID arbitration checks EVERY insertion winner,
including one delayed by a conflicting transaction that rolls back. Deadline PZ009 precedes
expired lease/cancellation PZ003. An expiry error rolls back the whole call, including its
provisional receipt. No SQL exception handler hides the error or retries the statement.
Exact historical repeats bypass these current authority checks.

The bounded loop performs no retry: either it validates the initial receipt, or attempts one
INSERT and validates the resulting winner/loser receipt on its second pass. Complete mutation,
history and fresh E15 poststate comparisons guard the output. Inbox parent is checked unchanged.

## Transaction and UNKNOWN boundary

The caller owns the transaction. A returned receipt stages settlement; only acknowledged COMMIT
permits durable reporting. Unknown COMMIT requires fresh observation/reconciliation or an exact
same-operation receipt observation, not a new operation ID or business-effect replay.

If E10 has committed, current succeeded state and spent fence prevent E32 overwriting success.
If E32 wins first, E10 cannot pass its final fence. E32 never modifies finalization_guards:
same-business-root settlement is rejected, and an unsatisfied guard in the settlement root
still prevents that root's COMMIT. E12/E13 winners likewise defeat a new E32 and retain their
own uncertainty/cancellation evidence. E31 is still needed to resolve held work.

## Accepted bounded evidence and remaining gates

Evidence directory: /home/faris/modkit-local-20261106/events-uncertain-settlement-20261109.
The SQL remains471491 bytes, SHA256
34ee692ce56bf4268239991e7366aeada393547c4fda7b7263b02c4fa3dae83e.
Its accepted448641-byte prefix is unchanged. Only the two documentation paths changed
after native acceptance; SQL and tests remain frozen.

Observed source TDD:30 missing-body failures/1 prefix pass, then31 authored source/ABI
checks passed. The separate31 independent checks overlap these and must not be added as
unique coverage. Six existing G2 controls passed against pinned accepted-base Python.
Initial test-path setup failed collection before the genuine RED; Ruff/whitespace passed.
The original author environment lacked pglast/pg_query; that limitation was not SQL execution
evidence. Independent source review SHA256
2af3388d4580341a8a76e71144e84f61a2b9f3ee0609b08aabdb690cc1012dae.

The separately reviewed, prevalidated SQL-native packet ran once in67.105 seconds:
wrapper exit0, native runner exit0, empty runner stderr and PASS marker.
There were55 recorded case/assertion labels, not55 unique requirements.
Accepted report: qa-v1/independent-native-acceptance-v1.md, SHA256
b46aa6212b157dcebb97fe1f2604d4ab68ffe3de9a6f49f63b09814f330dc7f2.
Runtime pins: qa-v1/native-evidence-pins-v1.json, SHA256
ddc7309a99530004b01b888f9c9ffdef30f2914957b23a94120eb0b368cfd0be.

Passed bounded coverage includes literal13-column values/OIDs, PUBLIC EXECUTE absence,
lawful inbox and W01 job hold COMMIT/ROLLBACK, exact receipts, full work/attempt/history/
capacity/payload/business footprints, repeats/conflicts and selected domain/root/fence/state
errors. Immediate, lease-expired, E12-held cancellation and finite-deadline-expired repeats
preserved the original receipt and complete footprint. Max-revision and corrupt-union
injection remain source-only, not native-qualified.

Actual E08/business/E10 committed success was preserved against E32. E32-first stale E11
and staged guard-backed E10 were rejected. A separate unsatisfied E08 guard produced PZ001
on COMMIT and restored tables/business while retaining expected nontransactional sequence
allocation. E12/E13 precedence was tested serially, not as a concurrent cancellation/recovery
race. Same-work lock serialization produced one receipt/history and identical repeat;
a committed other-work operation-ID conflict produced PZ002.

Actual unique-lock arbitration was observed with explicit timing margins and blocker identity:
- Delayed-live winner: record_time preceded blocker rollback release and matched work/history;
  after fresh authority validation, COMMIT produced the exact target-only delta.
- Delayed-expired winner: blocker rollback occurred after lease expiry; target returned PZ003,
  no target receipt remained, and durable rows/business were unchanged.
- Deadline plus lease crossing: release after both boundaries returned PZ009 unchanged.
- Finite-deadline historical repeat: database time was observed beyond the immutable deadline;
  the original receipt and rows/business/sequences remained exact.

These are observed lock/clock results, not sleep-only or exact-clock-equality claims.
The rejected delayed-expiry stdout record_time field is the blocker's fallback receipt time,
not a returned target timestamp. No target receipt was returned in that rejection.

Exact container4a6c8384e472a6ec6e6366fe6807e9dfa6e1ea4d47dd0794a9d53f93f7a4b372
was gracefully stopped using SIGTERM, observed exit0/stopped, removed without force and
verified absent by exact ID. No packet-owned resource remains. Startup readiness polling
was not a test replay. Raw lifecycle receipts and expected negative-test database logs are
retained; native runner stderr was empty. No consumed fixture or unchanged tests were rerun
for this documentation-only update.

Managed native E32 issuer/controller/B1 proof, provider truth or no-effect proof, UNKNOWN
wire/COMMIT injection, E31 resolution, exact-clock equality, max-revision/corrupt-union runtime
injection, broad drivers/platforms, production grants, migration/install/release and original
A-O/ERP gates remain unqualified. The SQL result does not close native durable uncertainty
or full product readiness. Postrun reviewer recheck and independent documentation acceptance
are recorded separately; this text does not claim them complete.
