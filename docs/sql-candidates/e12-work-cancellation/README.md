# E12 cooperative cancellation: bounded SQL qualification

E12 now has a source implementation of its existing four-parameter catalog contract. It cancels queued/retry-waiting/claimed/blocked-schema work, holds running work without claiming to undo external effects, and preserves terminal/already-requested-held observations without mutation. It acquires parent then Work then current attempt, repeats protected E15 validation after locks, and checks complete update/history receipts.

The accepted v54-fix1 design is reused; no public ABI, binding, decoder, native transport or existing SQL function changes were made. Existing migration prefix (365533 bytes, SHA256 0b51b172c86cc0a9a70ca290df0e612d93ea2a2165edbaa4224b4d0347b40ef9) is preserved byte-for-byte, including JSON performance fixes.

## Evidence and limitations

- Source-first RED:12 failures, each reporting missing E12.
- Focused GREEN:83 passed across test_work_cancellation_sql.py and existing test_persistence_contracts.py.
- New test no-cache Ruff and scoped git diff whitespace check passed.
- Independent emitted-source review accepted the unchanged SQL candidate. A separately authorized PostgreSQL 18.1 run installed the full migration and passed the selected SQL lane once, with all 21 qualification markers in order. Successful installation is not proof that every deferred PL/pgSQL branch ran.
- Actual bounded coverage: lawful queued/blocked-schema intake cancellation, terminal stale-fence repeats, claimed matching/stale/unpaired-fence cases, running-to-held cancellation and held repeat, plus E15/E19 observations. Assertions compared complete preimages/postimages across all 12 tables and three sequences, exact history, capacity, revision and timestamp deltas.
- Explicit rollback left all 12 tables empty in both same-session and separate-connection checks. Sequence counters correctly survived: work history 11/called, delivery history 4/called, publication history 1/not-called. No other client backend was observed.
- The reviewed 39-function helper/trigger/check/default closure and typed seven-operation fixture had no direct/indirect E10 call. No guard was created or repaired. This is SQL-only rollback qualification, not native transport, committed dispatch or external-effect evidence.
- Independent review accepted the bounded SQL result and final graceful disposal. No fixture remains: the exact stopped target was removed without force and exact ID/name absence was verified.
- Original disposal attempt is preserved as failed: Docker's deprecated --time notice on stdout broke the strict receipt check after stop returned 0. Separately authorized narrow reconciliation confirmed graceful shutdown; remaining-only removal/absence checks passed without repeating stop, creation or SQL. This was a cleanup receipt failure, not a product SQL failure.

The package remains NOT_READY. There are29 authored Events operation bodies of34, not29 qualified operations. E11/E13/E31/E32/E33, final resources/grants/receipts, native/ORM lanes and the original A-O integration/ERP retirement gates remain open.

See [the implementation plan](../../superpowers/plans/2026-11-08-events-work-cancellation.md) for the exact contract, accepted evidence and deferred qualification. Source and runtime evidence remain in the assigned private task directory; no old fixture or consumed runtime grant was reused. Held-first uncertainty, historical retry-waiting, other terminals/jobs, MAX/corruption, concurrency/guard/clock schedules, native/ORM and full production installation coverage remain unqualified.
