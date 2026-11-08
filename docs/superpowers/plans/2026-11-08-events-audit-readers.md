# Events audit readers implementation plan

**Goal:** Implement catalog-defined E19, E20 and E21 so callers can page retained Work history, delivery receipts and dispatch attempts.
**Architecture:** Three ordinary STABLE PL/pgSQL readers, existing indexed keysets, no new helper framework or schema. Each validates arguments before a bounded SELECT, checks selected record integrity, and returns the exact catalog columns.
**Spec:** Existing catalog.py E19/E20/E21, bindings.py cursor constraints, rows.py observation validation and the original A–O milestone B persistence requirement.

## Decisions and limits
The user delegated routine implementation choices and requested conventional approaches. Use the existing private checkout/branch, not a new branch/worktree. Operations ERP's session-owned repository pattern is reference only. No native runtime, E10 invocation, live WIP mutation, grants/manifest/version, publication or readiness changes. PostgreSQL execution is a separate bounded step, never inferred from source checks.
Direct SELECT without checks would expose malformed retained records; calling E15 would unnecessarily couple historical pages to current Work state and add queries. Select and validate the page in one STABLE cursor instead.

## Manual trace before testing
1. Canonical requests bind work_id UUID, nonnegative after_id or (after_cycle, after_attempt), and limit 1..256. UUID zero remains legal. Cursor values need not name existing rows.
2. READ COMMITTED is checked before arguments or relation access. Invalid inputs raise PZ005/PZ006 in that order.
3. Existing indexes (work_id, history_id) and attempts primary key (work_id, cycle, attempt) support strict ascending keysets and LIMIT, without OFFSET, nullable-OR filters or extra parent reads.
4. Each row is checked after selection, not filtered out. Selected malformed records raise PZ012 and fail the statement. Timestamps use the existing finite canonical helper. Storage-local semantic constraints match Python observations.
5. Missing Work/history returns an empty page. No claim of current Work consistency, completion proof, absolute physical IO bound or transaction outcome follows from audit rows.
6. Explicit output projection preserves catalog ABI. SECURITY DEFINER has a pinned search_path and PUBLIC EXECUTE is revoked. Readers do not lock, mutate, catch errors, execute dynamic SQL or call E10.

## One implementation task
- [x] Write source guards for missing functions, exact ABI, guard order, stable/security properties, indexed bounded queries and integrity rejection. Run them RED.
- [x] Append the three SQL functions to the package migration, leaving the complete baseline prefix unchanged. Include the new test in both artifact inventories.
- [x] Run source checks, relevant decoder contracts and the available base test lane. Existing unavailable Pydantic remains an explicit collection limitation.
- [x] Independent review and QA of the actual diff; fix concrete findings. Any PostgreSQL execution uses a new disposable fixture, never old V65.
- [ ] Commit the narrow reviewed delta, regenerate deterministic changelog and validate commit range. No push/release.

## Review focus
- Strict continuation at missing/high cursor values without duplicated rows.
- Selected malformed rows fail, while corruption beyond LIMIT does not force an unbounded scan.
- Finite timestamp range, reason domains and evidence caps match observations.
- STABLE statement snapshot and exact PUBLIC revokes without table/role permission changes.
- Untouched historical baseline and live WIP; no false runtime or release claim.

## Verified outcome
Source review found no product issue. Two pre-execution fixture defects were corrected before the first runtime attempt. Source RED12/one pass became GREEN13; focused134+247subtests and base210+268subtests passed, with30 optional skips and unavailable Pydantic excluded. A fresh PostgreSQL18.1 rollback-only run passed pagination, full-row, invalid-input, corruption, no-audit-write, isolation and bounded ACL checks. Independent saved-evidence review accepted the result; exact disposable target was reconciled after clean shutdown and removed. Live Events WIP remains unchanged. Broader native/concurrency/complete migration/release qualification stays open.
