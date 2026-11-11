# E22 bounded publication claim

E22 implements pending-to-claimed admission using the existing catalog and row contracts. Expired claimed/publishing rows remain untouched for separate E26 recovery. Digest-ordered raw discovery counts locked and ineligible identities. Reaching an item/budget bound reports pass_exhausted=false even when the last identity happened to be visited.

The implementation reuses the E04 bounded scan and exact binary64 lease algorithm, calls E28 once for full preimage integrity under the nonblocking row mutex, retains complete postimages, and appends one generated claim history per item. A narrow stored-ID guard ensures invalid persisted identifiers raise PZ012 rather than E28's caller-input PZ006. No new helper framework, schema, grants or dependency is introduced.

## Verification
Source-first checks recorded 11 missing-function failures, then green. Independent review found the stored-ID classification gap; its focused regression was red before correction and green after. Final source controls:12 passed. Focused123 tests+249 subtests; base239 tests+270 subtests,30 optional skips, known unavailable optional Pydantic module excluded. These source checks do not prove database behavior.

Fresh offline PostgreSQL18.1 attempt2 passed the reviewed SQL fixture:
- Empty/header payload and valid U+0000 public enqueue/claim.
- Five exact lease durations (smallest subnormal, one microsecond,0.1,1.0000000000000002 and3600 seconds), full returned row/history and unrelated-storage preservation.
- Pending revision increment and optional receipt/evidence preservation; terminal, expired-owned and exhausted-revision skip.
- Digest paging, item/budget/end semantics and the256-item limit.
- Sixteen invalid inputs with unchanged whole storage/sequence footprints; three malformed first preimages and owner-injected invalid stored UTF-8 ID.
- Late corruption rolls back prior transactional row/history changes while retaining the legitimate sequence gap.
- Least-privilege test role execution/private-table denial and REPEATABLE READ isolation precedence.
- One actual two-session schedule: holder claims first row and keeps the transaction open; contender observes its sleep before/after, skips that lock, claims second, and both commit. Final checks show distinct tokens and one claim history per event; repeated claim is read-only.

Attempt1 failed only on fixture JSON operator precedence. Parenthesizing the JSON element fixed the fixture; production SQL did not change for that failure. The original failed input/output remains retained outside the product checkout. Independent runtime-result acceptance passed. Both exact disposable targets were reconciled, cleanly stopped and removed; no consumed runner may be replayed. Full private source/fixture hashes and raw receipts are retained in the scoped evidence.

## Limits
This is bounded SQL evidence, not full migration, package, native-driver or publication lifecycle qualification. No E10 path, external publication, shared service, install/pull/build, production grants/manifest, version or release operation occurred. One controlled contention schedule does not qualify all races, starvation, physical IO, throughput,4096 actual visits or all coherent collision cases. Generated history sequences may have gaps after rollback. A returned claim is staged in the caller transaction and does not prove commit or broker delivery. Full package remains NOT_READY.
