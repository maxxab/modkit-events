# E32 uncertain-settlement candidate

Independent source review, focused pure controls and bounded SQL-native acceptance passed.
Postrun reviewer recheck and independent documentation closure are pending.
Managed native E32 transport/controller integration and full product remain NOT_READY.

See ../../superpowers/plans/2026-11-09-events-uncertain-settlement.md for the contract,
exact source/evidence hashes, observed coverage and limits.

A live exact running/dispatched fence becomes held with an uncertain attempt; capacity and
dispatch identity remain. Exact validated historical operation receipts repeat without
mutation. record_time is shared by receipt/work/history, never final fence/commit/durability
time. Fresh authority_time after arbitration governs every new winner; expiry rolls back
the entire call including the provisional receipt. Root inequalities prove neither historical
rollback nor provider no-effect. UNKNOWN success must be observed/reconciled, never overwritten.

One67.105-second native packet passed with55 recorded case/assertion labels, not55 unique
requirements. Jobs/inbox COMMIT/ROLLBACK, full footprints, repeat/conflict/error cases,
actual guarded success preservation, unsatisfied-guard COMMIT rejection, same-work
serialization and global-ID conflict passed. Delayed-live and delayed-expired unique INSERT
winners were observed with real blocker/clock evidence; deadline took precedence over lease.
Finite-deadline historical repeat preserved the original receipt and complete footprint.
E12/E13 precedence was serial, not a concurrent race.

Exact container4a6c8384e472a6ec6e6366fe6807e9dfa6e1ea4d47dd0794a9d53f93f7a4b372
was gracefully stopped, removed without force and verified absent. No owned resource remains.
No fixture replay occurred. SQL471491 bytes and its accepted448641-byte prefix are unchanged.

Evidence root: /home/faris/modkit-local-20261106/events-uncertain-settlement-20261109.
Acceptance report: qa-v1/independent-native-acceptance-v1.md
(SHA256 b46aa6212b157dcebb97fe1f2604d4ab68ffe3de9a6f49f63b09814f330dc7f2).
Runtime pins: qa-v1/native-evidence-pins-v1.json
(SHA256 ddc7309a99530004b01b888f9c9ffdef30f2914957b23a94120eb0b368cfd0be).
The31 authored and31 independent source checks overlap; six pinned-base G2 checks are
separate pure evidence. They are not a substitute for the bounded native result.

Max-revision/corrupt-union injection remains source-only. B1/full rollback/no-effect proof,
managed UNKNOWN transport injection, native E32 issuer, E31 resolution, exact clock equality,
broad drivers/platforms, migration/production grants/install/release and product gates remain
unqualified. Only these two docs changed for closure; no SQL/tests/native Python/Workers edit,
index operation or runtime rerun was performed by this update.
