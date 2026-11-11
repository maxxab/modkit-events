# E12 Cooperative Cancellation Implementation Plan

> For agentic workers: use superpowers:executing-plans with the retained dedicated feature owner. Source and the separately released bounded SQL lane are accepted. The fixture is disposed. This record grants no new execution or replay authority.

**Goal:** Add the existing E12 cancellation operation without undoing or replaying dispatched effects.
**Architecture:** One append-only PL/pgSQL function using protected E15 discovery, parent-before-work-before-current-attempt locks, fresh post-lock coherent validation, checked full postimages and one history record per mutation. Existing Python catalog/bindings/decoder stay unchanged.
**Tech Stack:** PostgreSQL PL/pgSQL, existing Python>=3.12 and pytest.
**Spec:** `/home/faris/modkit-local-20261106/foundation/continuation-v3/dot-events-review-20261107/e12-cancellation-design-v54-fix1/design.md`; independent bounded acceptance at sibling `independent-e12-cancellation-design-v54-fix1-review/review.json`, SHA25696e25ed3e0a3c81f82611542a06f3d35ee8af570608ba233ad36eed2754761b9. This is an established private implementation tracker, not a published issue.

## Global constraints

- Preserve the entire original365533-byte migration prefix (SHA2560b51b172c86cc0a9a70ca290df0e612d93ea2a2165edbaa4224b4d0347b40ef9).
- Exact interface: e12(uuid,uuid nullable,int8 nullable,text)->one(state text); paired token/revision; provided revision0..INT8_MAX; reason ASCII[a-z][a-z0-9_]{0,255}.
- Caller-owned READ COMMITTED transaction; no hidden transaction boundary, retries, provider I/O, E10 call or guard repair in E12. The separate disposable fixture installation does not establish production grants/resources or authorize live changes.
- Existing error identity and state semantics remain intact. Full package NOT_READY.
- Dedicated owner owns only appended SQL, tests/test_work_cancellation_sql.py, this plan, and docs/sql-candidates/e12-work-cancellation/README.md. Parent owns index/CHANGELOG/commits; parallel native work is excluded.

## Review focus

Check orphan versus genuine absence, freshness after blocking locks, terminal/optional-fence/held-repeat precedence, retained unresolved dispatch identity, and MAX/no-op/capacity accounting. Source tests guard text structure only. Independent emitted-SQL review and the bounded runtime result are accepted; unexercised branches and schedules remain explicit below.

## Task1: Source implementation and pure checks

- [x] Reuse accepted v54-fix1 design and refresh baseline; no contract changes selected. Starting HEAD8bc7b113130a9a3157fc74dff1c01719ae820155.
- [x] Trace request freeze -> discovery -> ordered locks -> fresh E15/preimages -> integrity -> terminal no-op -> conditional fence -> held-repeat -> overflow/time -> mutation -> receipt -> returned state. Trace existing Work/attempt triggers and immutable validators; no E10 call found in these source paths.
- [x] Write focused missing-body guards first;12 RED failures all report E12 missing, not setup/import failure.
- [x] Append e12 plus exact PUBLIC revoke only. Predispatch cancellation releases inbox count once. Running becomes held with cancelled_unresolved attempt/empty evidence. Held first request retains attempt evidence. Terminal and held repeat change nothing. Actual mutations advance revision once and use one sampled database time.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 /home/faris/modkit-local-20261106/.venv/bin/python -m pytest -p no:cacheprovider tests/test_work_cancellation_sql.py tests/test_persistence_contracts.py -q` from the Events private checkout:83 passed. No SQL/runtime/native execution.
- [x] Run existing Ruff `check --no-cache tests/test_work_cancellation_sql.py`:passed; scoped git diff --check:passed.
- [x] Document bounded evidence and freeze exact source/prefix/test/document hashes for independent review in `/home/faris/modkit-local-20261106/events-cancellation-assessment-20261108/`.
- [x] Independent emitted-source review accepted unchanged source candidate v1; its acceptance carries through the bounded runtime and final disposition reviews.
- [ ] Parent-controlled integration/commit of only accepted verified work.

## Task2: Separately authorized bounded SQL qualification and disposition

- [x] Independent review checked exact signatures/casts and the 39-function helper/trigger/check/default closure for no direct or indirect E10 invocation. The typed fixture uses seven public operations. Migration definition of E10 is not invocation.
- [x] QA executed one reviewed PostgreSQL 18.1 attempt on a fresh isolated target. Full migration installation and all 21 selected qualification markers passed. The accepted source hash remains ef9c3eafac5713a2ad07c62dbde476c1d0d751897a03d0e685788a8766fc2731. No standalone parser or native transport was executed.
- [x] Lawful E01/E03 queued and blocked-schema intake cancellation and terminal stale-fence repeats passed. E04 claims enabled matching/stale token/revision and unpaired-fence cases. E06 dispatch enabled running-to-held cancellation and held repeat. E15/E19 observations passed. Complete 12-table/three-sequence footprints, immutable fields, exact history/capacity/revision deltas and bounded sampled timestamps were checked, not marker names alone.
- [x] Explicit rollback and same-session plus separate-connection aftermath showed all 12 tables empty. Sequence counters survived as expected: work history 11/called, delivery history 4/called, publication history 1/not-called. No other client backend was observed. Running/held effects were rollback-only; no provider I/O or committed dispatch is claimed.
- [x] Independent review accepted the bounded SQL result. Full migration installation proves successful parsing/installation on this target, not execution of every deferred PL/pgSQL branch, every catalog operation or all supported environments.
- [x] Preserve original disposal failure: stop returned 0, but Docker 29.1.3 emitted a deprecated --time notice before the CID on stdout. The strict receipt assertion failed, leaving subsequent postchecks/removal unrun. This is not a product SQL failure and is not rewritten as an originally successful cleanup.
- [x] Separately authorized read-only reconciliation established graceful smart shutdown. Reviewed remaining-only disposal then verified stopped/no-OOM/exit0 identity and final shutdown log, removed the exact CID without force, and verified exact ID/name absence. No repeated stop, creation or SQL. Independent final disposition review accepted closure; no live fixture remains.
- [ ] Independent final documentation review, followed by parent-controlled exact E12 integration/commit.

### Accepted evidence

Paths below are relative to `/home/faris/modkit-local-20261106/events-cancellation-assessment-20261108/`. Earlier source snapshot v1 and failed disposition receipts remain unchanged.

- `qa/runtime-result-v2.json`, SHA256 598c1998a581faa06020c478949bc0f48a6fb328e82c022ac1066838bd770000: one attempt, complete selected SQL/aftermath evidence. Its then-pending disposition status is superseded only by later closure records.
- `review/runtime-disposition-review-v1.md`, SHA256 a3f71dc33ce8d797235e2613d0fb7451ca01853fec7128549eccfe1bd2492afd: independent ACCEPTED_BOUNDED_SQL_RESULT and reviewed disposition inputs.
- `qa/disposition-result-v1.json`: original warning-induced receipt failure, retained without rewriting.
- `qa/disposition-closure-v1.json`, SHA256 c6e4895404cfc78130dcaa114a5700cfcb2410f9c1a9ea708c83150c55071ccf: remaining-only disposal and exact absence evidence.
- `review/disposition-final-review-v1.md`, SHA256 7c8af21d9abc05e37956db03e1ef4898205dbe4ebfa566f3d57285e7735031cf: independent ACCEPTED_GRACEFUL_DISPOSITION_COMPLETE.

## Deferred qualification and release limits

First-request held uncertainty needs a lawful producer; retry-waiting historical attempts and failed/expired/reconciled terminals need their producers. Succeeded terminal and guard races remain E10-gated. Job provenance, MAX/corruption, concurrency/deadlock, exact clock boundaries, native/ORM/physical roots, full compatibility matrix, production ACL/resources/manifests/E33 and all-product readiness remain separate gates. No full-suite, all-branch, native or production acceptance is claimed. Whole product remains NOT_READY; public push is held. No fixture or consumed grant may be replayed from this documentation.
