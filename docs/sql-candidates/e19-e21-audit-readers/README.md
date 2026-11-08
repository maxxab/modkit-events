# E19–E21 retained audit readers

The package migration implements Work history (E19), delivery history (E20), and dispatch-attempt pages (E21). Source review and bounded PostgreSQL checks passed. The complete migration and package remain NOT_READY for installation or release.

## Behavior

All three preserve the existing catalog interface, support READ COMMITTED only, and use strict ascending keyset cursors with limits from 1 to 256. Existing indexes are reused. Missing work/history returns an empty page. Readers do not read current Work, lock rows, mutate state, or call E10. They validate selected rows and fail the statement with PZ012 instead of silently omitting corruption. Input errors use PZ006; unsupported isolation uses PZ005.

The entire earlier migration prefix remains byte-for-byte unchanged. No production constraint, grant, manifest, dependency or package version changed.

## Source verification

Twelve source tests failed for the absent functions, then all thirteen source guards passed. The focused source/decoder/artifact/standalone lane passed 134 tests and 247 subtests, independently reproduced. The available base lane passed 210 tests and 268 subtests, with 30 optional skips. The unavailable optional Pydantic module was excluded, consistent with the baseline. The new source test passes focused lint and formatting checks.

Independent source review found no product defect. It caught two errors in the prepared fixture before execution: an ambiguous PL/pgSQL counter name and poison rows blocked by existing timestamp CHECKs. The counter was renamed, and only the three timestamp constraints are relaxed inside the disposable rollback transaction to simulate damaged storage. Product constraints remain unchanged.

## Bounded PostgreSQL verification

The exact migration and test_runtime.sql passed once on PostgreSQL18.1 in a new offline, tmpfs-only disposable container. One READ COMMITTED transaction exercised:
- 260-row first, maximum, continuation, end, missing-cursor and parent-isolation pages.
- Complete returned-row equality for E19, E20 and E21.
- Twenty invalid inputs and unchanged audit rows/sequences.
- Malformed timestamps beyond LIMIT do not affect the first page; selecting them rejects the statement.
- Default PUBLIC execute denial, explicit operator execute access, and private Work-history table denial.

A separate REPEATABLE READ transaction confirmed PZ005 takes precedence even with NULL arguments. Both transactions explicitly rolled back. Independent saved-evidence review confirmed psql exit0, empty stderr, both pass markers, two rollbacks, and zero remaining fixture schemas/roles/prepared transactions/other clients.

The exact disposable target was fast-stopped and removed. The docker exec waiter returned137 during shutdown; fresh inspection showed container exit0, no OOM and a clean PostgreSQL shutdown log. This was reconciled before removal without retrying the stop. Final target lookup was empty.

## Remaining limits

These are structural reader checks, not public admission or current lifecycle proof. No concurrent snapshot schedules, actual index execution plans/physical IO bounds, every malformed semantic field, or native-driver behavior were qualified. Private-table access denial was exercised for Work history only, not all three tables separately. Installing the full SQL source for this bounded test does not qualify all its other operations.

No E10 call, old lease, shared service change, image build, dependency download, publication or release occurred. Runtime grants, production manifest, other missing operations, complete A–O qualification and release remain open.
