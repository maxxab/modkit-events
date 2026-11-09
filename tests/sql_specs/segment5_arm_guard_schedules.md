# Segment5 E08 prospective schedules

All NOT_RUN. These are future oracles, not executed passes or authority to start a database, driver, service, thread or external effect. Partial migration remains NOT_READY. Source release FL12-SQL-E08-SOURCE-RELEASE-1 permits text only. D8-1/2/3 and QA N1–N4 are required. Every fixture needs separately authorized installation/execution and an isolated fixture database; runtime role/grant setup is not included here.

## N1: fixture reachability and error stages

All post-insert PZ012/time/cancellation cases require initially DEFERRED guard constraint, a matching preliminary running Fence, and otherwise valid table-local shape. IMMEDIATE instead raises PZ001 at INSERT. Never disable a trigger/CHECK to manufacture a branch. The SQL file's owner rows are structural, with opaque placeholder intent; they do not qualify public admission, canonical input or job/inbox composition.

| Case | Constructible without disabling integrity? | Required oracle stage |
|---|---|---|
| Each NULL, revision0/-1, cycle0/2, attempt-1/1001 | Typed function arguments | PZ006 before assigning root/INSERT; PZ005 has priority if isolation wrong |
| Matching claimed count0 or positive count | Yes, token/lease present, dispatch NULL | PZ004 before INSERT, in DEFERRED and IMMEDIATE modes |
| Running count1 with request0; stale token/revision/count; absent work | Yes | PZ003 before INSERT; no narrowing of legal attempt0 |
| Missing current attempt; wrong work/ordinal/dispatch link | Yes, preserve each row's valid local keys | PZ012 after INSERT and coherent LEFT JOIN; not zero-row success |
| Attempt no longer dispatched | Insert dispatched then allowed local outcome edge | PZ012 after INSERT; no claim this owner transition is lawful public completion |
| Running NULL runnable_version or nonnull result | Yes | PZ012 after INSERT |
| Infinite/out-of-range work lease/deadline; uncapped lease | Yes, current work has no finite/cap CHECK | PZ012 before cancellation/deadline/lease errors |
| Running count0/count above max, NULL token/lease/pointer | No, existing work CHECKs | Earlier native constraint failure; defensive E08 branch not reached |
| Initial dispatched nonempty evidence | No, attempt trigger/CHECK | Earlier PZ004/constraint according to actual setup path, not E08 PZ012 |
| Nonpositive dispatch root or unsupported attempt recorded_at | No, existing attempt CHECKs; immutable identity afterward | Earlier invariant failure, not E08 PZ012 |
| Nonterminal success/guard/resolution witness leakage | Forbidden by existing witness CHECK, field by field | Earlier constraint evidence; separately constructible result leakage above |
| Work cycle2 requested as cycle1 | Work table allows cycle2, arguments require cycle1 | PZ003 mismatch; not a later cycle-integrity branch |
| Native argument cast/overflow, FK/unique/deadlock/timeout | Before call or relevant database statement | Native error is not broadly remapped to a PZ code |

Positive controls cover all eleven columns with unfiltered INTO STRICT then null-safe exact tuple equality against the stored guard, attempts1/999/1000, revision1/int8-max, zero UUID work/token, both structural kinds, absent deadline and finite capped deadline. Max-revision arm does not promise E10 can increment revision. Compare complete records, not only counts. Satisfied duplicate fixture is owner-only and must be rolled back, never accepted as a business certificate.

Additional isolated error probes: fresh REPEATABLE READ/SERIALIZABLE calls must raise PZ005 before xid assignment; fresh READ COMMITTED invalid-argument calls must raise PZ006 before assignment. Read the nonassigning accessor before/after these probes; do not pre-enroll via E14. For valid-grammar failed E08, xid assignment is allowed even when no guard persists. Missing-work and every individual stale component require own exact-category probes. Native input coercion is a separate stage.

## N2-A: incompatible-lock wait, then expiry or changed Fence

Start from committed otherwise-valid structural rows in a separately authorized fixture. Locker L retains an incompatible work lock such as FOR UPDATE without changing keys. T1's preliminary ordinary read sees the committed row; the INSERT/FK KEY SHARE must actually wait. Record backend identities, lock target, observed blocking relationship, wait-start and release order. Elapsed time alone is not proof that INSERT waited.

For lease expiry, deadline is absent; release L only after the known lease boundary, expect PZ003. For deadline expiry, set a finite capped lease and deadline; release after both, expect PZ009. For refreshed-Fence discrimination, L changes token/revision consistently and commits before releasing the wait; expect post-wait PZ003 rather than returning the preliminary row. A key deletion/change can yield a native FK error earlier and must not be mislabeled a post-read rejection. Apply N4 before fixture cleanup.

The incompatible owner lock is adversarial test machinery, never the required production renewal/cancel/recovery lock. Time equality is inspected statically here; sleeping past a boundary does not prove exact equality. A later authorized deterministic boundary method is required for an executed equality claim, with no production clock helper or system-clock changes implied.

## N2-B: compatible public progress while armed root stays open

T1 successfully E08-arms under DEFERRED mode and remains open. T2 uses a future lawful renewal/cancellation/expired-recovery function with required subscription ordering, non-key work updates and NO KEY UPDATE. T2 must finish and confirm COMMIT while T1 is still open. Capture both root identities and ordering; completion only after T1 rollback/commit is not progress proof. Bare owner UPDATE can characterize lock compatibility, but cannot qualify missing public routines.

E09 in T1 may still return its exact unsatisfied guard after T2 changes live work. E10 must later reject stale/cancelled/expired ownership and associated writes must roll back. E10 is absent and not released. A change after E08's post-wait snapshot may race its return; do not add a retained ownership lock to rule out this permitted race or claim E08 is the final fence.

## N3: committed public producer and caller business-root boundaries

Separate public qualification must retain actual E01/E03 or W01 admission, E04/W05 claim and E06 dispatch outputs, full refreshed Fence/current attempt, input equality and subtype evidence. Record confirmed caller-controlled dispatch COMMIT before any external provider I/O. No external effect is authorized or necessary for this SQL qualification. Public-name calls still in one uncommitted fixture transaction are not this evidence.

Enter the actual explicitly enrolled business root after dispatch. Record canonical E14 root, arm E08 before all associated business/outgoing writes, and compare the stored/returned root and complete GuardRow. Preserve application authority and material readiness. A synthetic root, root inequality or owner-created attempt is not a replacement. Workers jobs SQL is absent; do not create an events→workers dependency or fake subtype to bypass that gate.

## N4: fail signal before caller savepoint cleanup

For each reachable post-insert failure, set up the intended defect before a caller-owned savepoint under DEFERRED mode. Preserve an unrelated sentinel write before that savepoint. Snapshot complete work/attempt/subscription/history rows, pre-existing guard rows and sentinel. Record the actual expected error code before issuing ROLLBACK TO SAVEPOINT. Any normal return, extra/missing returned rows or unexpected earlier native/PZ001 error must fail the test. Do not always roll back first and infer rejection from guard absence.

Only after the failed-call assertion recover that savepoint. Verify no new guard for the exact work/current root; all complete snapshots and sentinel still match. Then release the savepoint if required by the caller harness. Full-root cleanup occurs last. Repeat for PZ012 malformed rows, PZ003 cancellation/lease/stale-after-wait and PZ009 deadline. The SQL fixture's exception subtransactions separately reject normal/unexpected results and compare state before outer rollback; they do not alone prove driver SAVEPOINT order.

## Remaining protocol and privilege schedules

- Under pre-existing IMMEDIATE mode, preliminary-valid arm raises PZ001 at INSERT, not the later PZ012/time check. Preliminary claimed attempt0 retains PZ004. Under DEFERRED, unsatisfied successful arm must fail SET CONSTRAINTS IMMEDIATE and outer COMMIT; exact operation failure and caller recovery must be recorded.
- Arm and associated writes inside one savepoint roll back together. Outer guard survives rollback of inner failed completion and remains unsatisfied. Successful guard unit cannot commit lawfully until E10 exists; no owner satisfaction substitute.
- Same work in two genuine active roots can arm separate unsatisfied guards if each has matching current Fence; no work-only duplicate rule. Different work in one root can arm separately; no root-only duplicate rule. Each root is exclusively borrowed and fully rolled back. No concurrent call on one connection or supplied-xid masquerade.
- Duplicate same work/root, exact or changed Fence or satisfied, raises PZ008 before stale/state checks. Compare the original full guard and all unrelated guards before/after; no duplicate-invalid rows or weakened uniqueness. Whole guarded savepoint rollback can remove a prior arm, allowing a later arm only after real caller rollback; absence is not historical rollback proof.
- Future E10 must establish final locked Fence/attempt/subtype, atomic result/history/counter/certificate and old-to-successor revision mapping. Physical COMMIT after the fence time does not resample lease/deadline. E14 after completion retains mutation=True and narrow same-root semantics, never commit health or uncertainty clearance.
- Verify exact five-type/eleven-result ABI, one overload, trusted owner, fixed pg_catalog,pg_temp, qualified compilation sites, VOLATILE/DEFINER/CALLED ON NULL INPUT and exact PUBLIC revoke. Actual runtime-only EXECUTE and operator/reconciler/PUBLIC/private-table/helper denial require full installed effective ACL/membership/default/grant-option inventory. Fresh-backend malicious pg_temp types/functions/operators and all driver profiles remain NOT_RUN.

No runtime cell, existing segment3/segment4 obligation, full public API, worker SQL, installation manifest/grant/receipt or original A–O requirement is closed by these prospective files.
