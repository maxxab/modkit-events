# E30 bounded work listing candidate

Status: BOUNDED SQL VERIFIED; NOT_READY for package integration or release. This directory is inert design/source material, not an installed migration or startup hook. It is intentionally outside the package and existing artifact allowlist. Only the bounded database checks described below are qualified. No E10, native transport, deployment or package-readiness qualification is claimed.

## Source baseline and integration

This review candidate does not modify the existing Events SQL or import its uncommitted baseline. It is kept outside package installation paths so it cannot run automatically.

Integration baseline: src/modkit_events/persistence/sql/0001_initial.sql, 290583 bytes, SHA-256 6cf0c7d1fb6baaccf98b5aaf0e3ed15c55c12941c4e73d45d083d948ec9a5534. Integrate only after reviewing the complete migration and preserving concurrent changes. The baseline is not included in this candidate commit.

## Design and contract

Use ordinary ascending keyset pagination on (created_at, work_id), not OFFSET or a new pagination framework. E30 retains its catalog ABI: namespace, nullable after_created_at, nullable after_work_id, limit. Both cursor fields must be absent or present; limit is 1 through 256 and namespace is the existing bounded UTF-8 byte identity. Timestamp cursors must be finite and representable by the canonical timestamp contract. Only READ COMMITTED is supported.

First-page and continuation queries are separate so the cursor is a direct index condition, not a nullable OR filter. Each materialized page selects at most limit IDs from the matching namespace before invoking the existing integrity-first E15 reader. E30 and E15 are STABLE and see the same statement snapshot. Return all 56 catalog Work columns in strict ascending tuple order; malformed selected work fails the whole statement instead of being skipped. No row locks, clock, mutation, exception swallowing or private integrity-validator copy.

The full (namespace, created_at, work_id) B-tree supports E30. Inbox work may legally use namespace jobs. W03 must therefore select job rows before LIMIT, not filter E30 output afterward. A separate partial B-tree on the same keys for kind COLLATE pg_catalog."C" = 'job' COLLATE pg_catalog."C" supports that Workers query without changing E30 or existing namespaces. W03 remains separately owned by Workers.

## Manual trace and plan

Reviewed catalog.E30, input bindings, output namespace/order coupling, E15 composition checks, existing indexes, E03 namespace admission, and the Workers W03 constraint. Existing E30 is missing and no created_at listing index exists. The first source tests must fail for that missing candidate, then the minimal SQL should make them pass. These are source checks, not PostgreSQL parsing or runtime proof.

1. Add focused ABI, guard, index, bounded-query and no-mutation source tests; record expected missing-candidate failure.
2. Add the inert SQL delta, without changing the baseline or packaging.
3. Run source checks, relevant catalog/listing decoder checks and permitted package tests; independently review the current candidate.
4. Commit only this candidate directory after independent acceptance and preserve all unrelated work. Baseline integration and remaining runtime qualification stay separate.

## Bounded PostgreSQL verification

The exact baseline and this SQL compiled on a fresh offline PostgreSQL 18.1 fixture. test_runtime.sql passed in 7.61 seconds inside one READ COMMITTED rollback transaction:

- 260 tied-timestamp inbox rows: empty, first, 256-item, continuation, missing-cursor-row and end pages; namespace isolation and complete E15 row equality.
- A valid synthetic inbox row in namespace jobs remains visible to generic E30. A selected Work row without its required inbox half fails with PZ012 instead of being skipped.
- Twelve invalid namespace, limit and cursor inputs fail with PZ006. All fixture rows and sequences remain unchanged by the reader checks.
- Default function EXECUTE is denied. An explicit function-only operator grant permits E30 while direct private-table access stays denied.
- EXPLAIN ANALYZE for the first-page, cursor-page and job-filter discovery SELECTs uses the intended Index Only Scan without a Sort or Seq Scan. The fixture does not force planner settings.

A separate REPEATABLE READ rollback test, test_isolation.sql, confirmed PZ005 rejection. Both runs explicitly verified that rollback removed the schema and fixture roles. A final check found no test schema, fixture roles or other clients; the disposable container was stopped and removed. Independent saved-evidence review accepted these bounded outcomes without replaying the database work.

The first run stopped before E30 behavior checks because the test snapshot helper attempted to treat a sequence as a composite row. Its known failed return and clean rollback were verified, then only that helper was corrected to read explicit sequence fields. Product SQL did not change.

### Remaining qualification limits

The EXPLAIN results cover discovery SELECTs, not the complete E30 function. The partial-index scenario contains inbox work in namespace jobs but no actual job rows; it does not qualify W03's mixed-job listing. All main page rows use one timestamp, so timestamp-dominant ordering across different timestamps and concurrent insert/delete behavior remain untested. Synthetic structural inbox fixtures do not establish public admission or broader lifecycle correctness. Native transport, integrated installation/grants, production migration and package readiness remain separate gates. No E10 call, manifest or version change occurred.

## Source verification

The ten missing-candidate tests failed before SQL implementation, then all ten passed. The private checkout base suite passed 187 tests and 266 subtests, with 30 optional Redis skips. The full suite was attempted but could not collect tests/test_contracts_pydantic.py because Pydantic is unavailable; the reported base result explicitly excludes that module. No dependency was installed. Raw outputs are preserved in the task evidence directory outside this Git checkout. See verification.json for the exact scope and current review status.

Run the focused source checks from this checkout with:

    python -m pytest docs/sql-candidates/e30-work-listing/test_source.py -q

Independent source review accepted the exact SQL candidate without correctness findings. Its focused verification passed 12 tests (the ten SQL source guards and two existing E30 decoding/bounded-demand checks), with 69 tests deselected.

The Python checks protect the source contract; the separate SQL fixtures provide only the bounded runtime coverage listed above. The candidate is not included in the wheel or source-distribution packaging paths. No package version, migration manifest, runtime grant, readiness result or public API has changed.
