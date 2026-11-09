# Troubleshooting

## 2026-11-09: empty Git objects after an unexpected PC restart

Symptom: `git log` and `git status` failed with an empty-object error and
`fatal: bad object HEAD`. Nine loose objects were zero bytes: four documentation
blobs, four trees and the current documentation commit. The source-only test
log also ended without a result and contained a zero-filled tail.

Cause: abrupt host restart interrupted durability of recent local writes.
The exact storage-layer mechanism is UNKNOWN; no source change is blamed.

Verified recovery: preserve the complete Git directory and working files first.
Reconstruct blobs only when their Git object hashes match the index, reconstruct
trees from the surviving index, and accept commit reconstruction only when its
full original Git object ID matches. All nine original IDs were restored,
including HEAD `4a633e6e8e4fdf9465a49daced0edc67e97749da`, without changing
refs, index, working files or commit history. Repaired object files were fsynced.
`git fsck --full` found no integrity errors; historical dangling objects were
retained. The working tree was clean and the earlier review manifest matched.

Evidence: local sibling qualification workspace `resume-events-20261109`,
`restart-recovery-20261109/{snapshot.json,exact-object-repair-plan.json,
object-repair-result.json,fsck-after-repair.log}`; original damaged metadata,
working files and empty objects remain preserved there. This is local Git
recovery, not release or runtime acceptance. The interrupted test run must not
be reported as passing. No Redis/PostgreSQL runtime release or fixture had been
created by this work before the restart.

## 2026-11-09: grant installation compile failure and bounded runtime stops

The approved disposable PostgreSQL installation attempt stopped after creating
its test roles/databases. PostgreSQL18.1 reported a syntax error at character
101913 in Events grants. The type-topology `IF` condition contained an
unparenthesized SQL `CASE`; its inner `THEN` terminated PL/pgSQL expression
scanning before the SQL expression was complete. Both preflight and postflight
conditions had this defect. Grouping each CASE expression preserves the
comparison and strict topology checks. The reproducing static delimiter check
failed before this change;47focused grant/resource/manifest checks pass after it.
Actual compilation/installation of the corrected SQL remains UNQUALIFIED.
Initial SQL, granted signatures/roles, receipt template and contract IDs are
unchanged. The grant resource and MKMF hashes change; Workers must select the
new Events aggregate before a new reviewed attempt.

The failed fixture remains preserved. The installer reported an unclosed owner
connection before exiting; no inferred commit/rollback/close outcome, native
success or success-only cleanup is claimed. Future harnesses must save the
actual bounded bootstrap failure observation before asserting its outcome.
Evidence: sibling `resume-workers-20261109/native-approved-attempt-r3-result.md`,
`native-install/runtime-r3/` and Events `grants-case-{red,green}.log`.

The separately approved Redis8 create command timed out before returning a CID.
Only its owned CLI child was killed/reaped; no Redis test ran and Redis7 was not
attempted. Read-only reconciliation found the exact name absent at the recorded
observation time; this does not establish the entire prior/late daemon outcome.
The attempt marker, command journal and socket directory remain preserved.
Its timeout cause is UNKNOWN. Separate owner reservation messages crossed,
so the PostgreSQL and Redis attempts were not fully serialized; future runtime
handoff requires an acknowledged common reservation before either dispatcher.
No retry, failed-fixture disposal or new runtime scope is implied by these fixes.
Evidence: sibling `resume-events-20261109/redis/{runtime.json,execution.log}`,
`redis-readonly-reconciliation.json` and `restart-coordination.md`.

### Later reconciliation: failed native fixture disposal

The preservation statement above describes the original failure. A separate exact human approval subsequently authorized failed-r3 disposal; Workers completed the8pinned graceful-stop/wait/nonforce-removal/absence commands. Receipt: sibling resume-workers-20261109/native-r3-disposal-completion.json, disposition EXACT_FAILED_FIXTURE_DISCARDED_NOT_QUALIFIED. Predecessor Events independently verified all17saved result/capture hashes (resume-events-20261109/rollover-checkpoint-2/disposal-receipt-verification.json). No SQL replay or successful installation is established; original native attempt and disposal grants are consumed. Redis UNKNOWN is unaffected. No runtime operation was performed by this handoff.
