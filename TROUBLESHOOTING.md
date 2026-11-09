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
