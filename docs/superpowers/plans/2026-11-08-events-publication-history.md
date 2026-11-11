# Events publication-history reader implementation plan

**Goal:** Implement the catalog-defined E29 bounded retained publication-history reader.
**Architecture:** One STABLE PL/pgSQL function with the existing (event_digest, history_id) index, exact catalog projection and selected-row validation. No parent lookup, schema redesign or new helper framework.
**Spec:** catalog.py E29, bindings.py constraints, rows.py PublicationRow validator, transitions.py publication codes, publication_history constraints, and E28 identity-conflict behavior.

## Decisions and limits
The user delegated implementation decisions and asked for clear conventional approaches. Keep the existing private branch. Append the function without changing prior SQL. Direct unvalidated SELECT would hide corruption; an E28 parent read would add unnecessary current-state coupling. Digest-only discovery followed by integrity checks and full-ID comparison preserves aliases. Coherent full-ID conflicts use E28's PZ002; damaged stored records use PZ012. Defer PZ002 until every selected row is checked so a later selected corrupt row cannot be hidden by an earlier alias.
No E10, native or shared-service work, package-version change, grants/manifest readiness claim, push or publication. Historical observations are not publication certificates.

## Affected-flow trace before tests
1. E29 binds event_id bytea, nonnegative int8 after_id and int4 limit 1..256. Event IDs must be nonblank UTF-8, at most256 bytes. READ COMMITTED is checked first, then arguments, before relation access; PZ005/PZ006 precedence matches existing readers.
2. publication_history has generated SHA-256 event_digest and an existing (event_digest, history_id) index. Select strict history_id > cursor in ascending order, at most limit rows. Missing history and high/missing cursors need no parent row and return empty.
3. Never filter full event_id before examining digest candidates. Check the selected row's positive history_id, valid full ID and stored digest, status/intent/operation/receipt shape, bounded evidence/binding, their provenance and finite supported time against PublicationRow and table constraints.
4. Publication codes are enqueue, claim_publication, renew_publication, publication_intent, publication_confirmed/rejected/uncertain, recover_publication_preintent/intent, repair_published/rejected. Renewal permits intent NULL or UUID; only repair permits operation and binding. Settlement/repair permit optional receipt and opaque evidence.
5. PZ012 is raised for selected corruption. Valid but different-full-ID digest hits use PZ002 after the entire selected page passes integrity. No real SHA-256 collision runtime fixture is practical; that branch remains source-only, without hash mocking.
6. STABLE plus a single cursor query supplies a statement snapshot. Explicit projection matches nine catalog columns. Pinned pg_catalog/pg_temp search_path, PUBLIC revoke and schema-qualified helpers preserve security. No locking, mutation, error swallowing or E10 call.
7. Relevant immutable _utf8_valid/_instant_bytes helpers are reused. Physical IO, concurrent schedules, lifecycle/admission, native drivers and full package readiness remain outside this slice.

## Implementation and acceptance
- [x] Add exact ABI, argument/security/keyset/integrity/conflict source tests and observe RED for missing E29.
- [x] Append minimal E29 and add the source test to both fixed artifact inventories.
- [x] Run focused source/decoder/artifact tests and available base lane; report optional-dependency limits.
- [x] Obtain independent source review and review of the inert E10-free SQL fixture before any fresh offline PostgreSQL18.1 execution.
- [x] Review actual runtime evidence and reconcile exact disposable cleanup. Do not replay consumed targets.
- [x] Prepare the independently reviewed source delta for local commit. Deterministic generated-file-only changelog, final clean tree and commit range will be recorded in the external closure evidence after committing.

## Review focus
Maximum and missing cursors; exact UTF-8 limits; every publication status and nullable field; selected versus beyond-page corruption; digest corruption before full-ID conflict; no current parent consistency or successful publication inference.


## Verified outcome
Source RED16 failures/one pass became GREEN17. Focused128 tests+248 subtests and available base227 tests+269 subtests passed;30 optional skips and unavailable Pydantic excluded. Independent source review and QA accepted the delta. Two fixture-only errors were diagnosed and corrected without product changes; their rollback and cleanup evidence was preserved. A fresh third PostgreSQL18.1 run passed and was independently accepted:12 invalid inputs,19 semantic corruption scenarios, malformed-digest precedence, pages/projection/read-only, ACL and isolation checks. Both transactions rolled back, and every disposable target is cleanly removed. The complete earlier SQL prefix and live WIP remain unchanged. Broader qualification and release remain NOT_READY.
