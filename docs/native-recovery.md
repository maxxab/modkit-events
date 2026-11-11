# Native recovery: E13

This source adds the fixed five-input E13 issuer, complete ScanPage /
WorkObservation decoding, paid preparation and mandatory retained-capacity guards.
It does not establish deployment readiness or grant namespace authority.

## Host preflight and authority

The host must hold trusted authority over the entire selected job namespace in
the exact database/schema throughout issuance and commit/rollback acknowledgement.
Per-job Scope, E33 readiness or labels do not grant authority. Post-mutation
filtering cannot supply it.

Import modkit_events.persistence.recovery_profile without importing a driver.
Call recovery_requirements(readiness=expectation) with the exact immutable
two-component events/workers expectation. It returns all 17 LifecycleLimits
minima, generic E13 M, complete R(1), representation-safe E33 M/R, fixed job
namespace/page settings and descriptive profile metadata. Explicitly call
verify_recovery_driver(requirements) before once-only registry configuration.
Neither call creates a connection, configures a registry, issues SQL or reads
live domain state. Verify all limits and caller-owned summary retention first.
No public-root export or dynamic operation registry is added.

The existing CPython 3.12.3 Linux 64-bit /30-bit integer-digit layout and its
profile ID remain unchanged. An additional qualification branch accepts only
exact CPython 3.13.5 Linux x86_64, conventional-GIL, nondebug builds with the same
checked scalar/actual product-carrier size bounds. It requires explicit build
configuration flags and an enabled runtime GIL; missing/unknown flags, disabled
GIL, other architectures/patch levels and oversized layouts refuse. Requirements
and verified receipts identify the actual selected interpreter profile.

Driver identity remains psycopg binary 3.3.8 /libpq180006. M13=761,
R1=5252364 and R256=1344536844, the full17 limits, D2 and cleanup4096 are unchanged.
Host simulated-3.13 tests prove branch logic only, not actual 3.13 compatibility.
Independent source review and an immutable actual-3.13 product qualification
packet remain gates before claiming support. Version strings/descriptive records
are not binary attestation. Issuance rechecks the profile; a verification record
is process-local description, not transferable authority.

## Serialized operation

Startup E33, each E13 page, commit/rollback acknowledgement and cleanup are serial.
No reentrant callbacks, concurrent Events observers or overlapping replacement
roots/pages are covered. Scanner observers touch independently owned scalar state.

prepare_recovery(execution, execution_ledger=ledger, capacity=M, namespace=...,
kind=..., limit=..., scan_after=..., discovery_budget=...) reserves before building
the five-tuple/context/request. Native E13 supports job/inbox, limits1..256,
discovery limit..4096 and UUID-or-None cursor. The host profile chooses
jobs/job/limit1/default discovery128. Preparation does not issue or finalize.

Admit on the original caller-owned active root, reserve one result and execute.
result_capacity(ticket, execution_ledger=ledger) provides the same R(N) kernel as
the mandatory start guard. Bypassing this convenience cannot bypass validation.
Canonical retained request, preparation minimum and complete R(N) are checked
before RUNNING/native borrow/cursor/SQL. Read via the existing managed API.
Drop all borrowed page/Work aliases before releasing result/ticket/preparation.

The fixed descriptor has 60 canonical /61 physical columns, a mandatory header,
at most N items and LIMIT N+2 overflow sentinel. SQL caps every variable cell;
the complete copied row is checked before conversion. No fetchall, projection,
truncation or dropped valid inbox branch. Full identity, protected/replay,
canonical-intent and state validation remain. E13 resolution is absent and all
16 receipt cells null. Namespace/kind, ordering, cursor progress and exhaustion
are coupled to the exact request.

Project only separately paid scalar summaries while the result remains paid.
Commit/rollback using existing native root APIs and acknowledge the exact returned
receipt before publishing committed cursor progress. Unknown outcome, failed
cleanup or escaping construction failure stops the owner. Never refund, replay,
reset the domain or replace the connection over retained uncertainty.

## Logical resource units

M is retained request/context bytes:
C(FrozenRequest)+T5+B256+U5+I9+Cur+I13+C(ReturnContext)+T0.
R(N) includes all39 Work base scalars plus resolution=None, page/tuple/header.
UUID integer storage and repeated aliases are charged by occurrence. Unicode
maxima cover equal values having different internal representations.

D=2 counts concurrent owned construction/escaping frames, not temporary bytes.
The outer issuer owns cursor/PGresult/copies/full decoder and validator products;
inner start/publication/completion helpers occupy the second slot sequentially.
Finite products include bounded replay/protected parsing, canonical encoding
and traceback-retained active phases. M/R/D are not allocator, RSS, native-buffer,
database-memory or completion-deadline guarantees. Native I/O may remain blocked.

AB=max(M13,M33), BB=max(R13,R33); counts/per-owner counts are1 except D=2.
Cleanup reserves exactly4096 logical bytes for one bundle after known root
resources drain. This is a caller-selected protocol constant, not an intrinsic
Events API minimum. Retire, prepare/reserve/pin cleanup, native close,
acknowledge physical close, release cleanup, detach and dispose run serially.
No cleanup is authorized over stopped/unknown ownership merely because slots exist.

## Qualification boundaries

The six test_native_recovery_* modules are connection-free. Their structural
PGresult/driver substitutions are not production fallbacks. The native E13
integration file is author-only opt-in source, excluded from source verification.
Independent source/profile review, QA, full item/fault/rollback/commit native
qualification and the separately owned Workers positive adapter remain required.
No SQL/schema/catalog/dependency change or live native result is claimed.
