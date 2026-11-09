# Segment4 root/guard schedules

All NOT_RUN. Source-first prospective expectations for E14/E09, under accepted modkit-pg-ab-2 and FL11-SQL-SEGMENT4-RELEASE-1 decisions D4-I1/D4-I2. No PostgreSQL/parser/compiler/driver/test execution, fixture installation or role action is authorized by these documents. The initial migration remains NOT_READY. The SQL companion supplies owner structural cases only; it is not a public admission/guard lifecycle fixture.

## Focused single-root schedules

- T14-1 and T09-1: companion SQL checks fresh unassigned root, nonassigning E09, zero rows rather than a NULL row, then E14 exact actual positive root and repeat identity. Start in a fresh caller-owned READ COMMITTED root after any separately authorized installation has finished, not in the DDL transaction that already assigned an xid.
- T09-2/3/4/5/7: companion SQL checks exact11-column positive unsatisfied row, all five NULL fields, revision0/negative, cycle0/2, attempt-1/1001, missing/other-root/satisfied guards, zero UUID, revision int8 maximum and attempt0/999/1000 valid misses, full unchanged guard/work tuples and absent attempt/history insertion. Strict-result checks fail on zero/multiple positive rows; assertions use null-safe comparison. Another-root fixture uses deliberately synthetic owner data and proves only the root predicate, not a committed public guard.
- T14-2/T09-6: caller starts a fresh root and captures E14. Before/inside/after SAVEPOINT and ROLLBACK TO SAVEPOINT, E14 must remain equal to that actual top-level xid. An inserted inner unsatisfied owner guard is visible to E09 before rollback and absent afterward; a pre-existing outer guard remains visible. Repeat calls in the same prepared statement must observe current own changes, not a cached row. These require new complete fixtures rather than reusing the companion's fixed IDs in a conflicting root.
- T14-3: independently create caller-owned REPEATABLE READ, SERIALIZABLE and reported READ UNCOMMITTED roots. Before calling either function, record nonassigning xid status. E14 and E09 must each raise PZ005, including E09 with otherwise malformed Fence; PZ005 is isolation-first. At an authorized recoverable savepoint boundary, verify no assigning accessor ran. The caller owns failed-transaction cleanup. Do not pretend an error by itself proves history rolled back.
- T09-5 positive endpoints still owed: independent owner fixtures with revision1/max-int8 and attempt1/999/1000, zero UUID work/token and cycle1 must return full matching tuples. Work parent constraints must be met; these are structural guard observation fixtures, not proof such epochs were produced legitimately. Attempt0 remains a valid input with no possible stored guard. Never alter accepted Fence bounds to make an endpoint pass.
- T14-4: actual installed function metadata must show E14's no-argument TABLE(root_xid xid8) and E09's exact five-argument identity/ordered eleven columns, not unnamed scalars, overloads or caller xid authority. Wrong SQL types/overflow and prohibited server contexts retain native errors, not invented PZ categories.

## Producer/transaction schedules requiring later source

G4-L1: use valid public admission/dispatch and E08, not owner DML. E08 GuardRow root must equal E14 in the same caller root; E09 returns the same unsatisfied guard. E10 success makes E09 return no row. Protected completion observation must validate the complete stored witness. E08/E10 and related producers are absent in this wave.

G4-L2: T1 arms; T2 renewal/cancellation/expired recovery commits under its rightful locks. T1 E09 may still return its matching unsatisfied guard without live-work locking/revalidation; this is evidence of a guard, not permission to complete. E10 must use its later locked final fence and reject a stale/expired state. Verify actual lock compatibility/timeouts separately; ordinary SELECT still takes table-access locks and no wall-time bound is promised here.

G4-L3: after outer arm and associated writes, failed completion inside an inner savepoint is rolled back/swallowed. E09 must show the restored unsatisfied outer guard and eventual commit must reject PZ001. If guard and every associated write were wholly within a rolled-back savepoint, E09 is absent and unrelated outer work may commit. A write before arm is unsupported. Refer to guard_constraint_schedules.md; no result in this file closes its unrun schedules.

G4-L4: a new caller root cannot obtain a prior root's guard via E09, even with identical Fence values. Satisfied committed guards are never returned. E09 accepts no root or guard ID parameter. Repeat with two actual distinct backends/roots once valid producers exist. A synthetic owner root test is not a substitute.

## Security/consumer schedules requiring later qualification

G4-P1: exact authorized runtime E09/E14 EXECUTE succeeds; PUBLIC/operator/reconciler calls fail under the unchanged installation allowlist. Direct guard SELECT/DML and private helper EXECUTE fail. Complete grants_runtime and effective actual-object ACL inventory are still absent. Do not add temporary broad grants as a shortcut.

G4-P2: before first function compilation on fresh backends, malicious pg_temp built-in-name domains/functions/search_path must not influence parameter/result/local types, casts, root/isolation built-ins or relation selection, or execute attacker code under the owner. E14 must be INVOKER; E09 DEFINER must use the existing trusted schema owner with fixed pg_catalog,pg_temp path. Actual authorized server adversarial fixtures are required.

G4-P3: inspect every actual function/overload and exact ACL, resolving NULL proacl with built-in object ACL semantics. Verify exactly owner+intended grantees, no PUBLIC/unexpected named EXECUTE/nonowner grant option; inspect membership separately. Two explicit source revocations do not prove the final installed matrix. Final ACL assertion/receipt/manifest are later gates.

G4-A1: separately owned D5 transports use only their existing frozen calls and approved allowlists. Preserve root identity, exact result shape, already-open caller ownership, exclusivity and sticky uncertainty. Do not add E09 to a staging allowlist merely because its general catalog entry exists. No driver/candidate code was imported or exercised here.

## Coverage debt and interpretation

These are future oracles, not observed passes. SQL companion covers representative structural cases; positive upper-endpoint/zero-UUID guards, savepoint/isolation, installed metadata, least privilege, cross-root and public producer schedules remain unexecuted and partly unauthored as executable fixtures. Existing segment3 owed coverage remains entirely NOT_RUN and unchanged, including22/11/7 domains, typed E27/E31/E32 union arms, immutable-field cases and full typed-repeat/history/evidence observations.

Neither root identity, no current guard, an ended transaction nor a new connection proves historical rollback or external replay safety. Functions do not own transaction cleanup or distinguish an explicit caller BEGIN from autocommit. E09 is not a live final fence; complete-last and application authority remain caller protocol. D4-I1 and D4-I2 are precise new implementation interpretations requiring independent source/security/QA challenge, not recovered historical behavior or runtime acceptance.
