# E11 fenced failure persistence

Bounded independent source, pure-check and SQL-native acceptance PASS. Full package NOT_READY; this is not managed native-issuer/B1 qualification.

Caller must establish full business-root rollback and confirmed failure/no-effect before calling E11 in a distinct caller-owned root. Root inequalities are structural checks, never historical proof. No native B1 activation, transaction ownership or external replay authority is added. TRUE stages the result; caller-confirmed COMMIT is required for durable reporting. Unknown commit requires observation, not blind replay.

Exact catalog E11 returns one bool. All outcomes require a live complete fence and deadline; deadline is checked before lease after locks. Invalid retries reject unchanged. Retry requires application_safe, remaining budget and a strictly future schedule strictly before deadline. It resolves the attempt to failed with exact evidence, clears the current dispatch pointer, preserves count and capacity. Terminal failure/cancellation retain the pointer and release inbox capacity once. Cancellation means independently established no effect. E12 winning first revokes ownership and defeats E11.

Parent/work/attempt locks precede fresh E15 integrity and clock checks. Whole mutation postimages, every history receipt field and a fresh E15 poststate are checked. Caller rollback rolls back all effects; history sequence gaps are possible. No SQL transaction-history inference or operation-ID replay API exists.

Manual trace and independently challenged design: /home/faris/modkit-local-20261106/events-fenced-failure-20261109/proposal-v1.md. Source release: source-release-v1.json in that directory. Existing 432362-byte SQL prefix remains frozen. Owned changes are append-only SQL, new test and two documentation files.

Evidence: missing-body RED and E11-SR-001 ordering RED were observed before their respective changes. Corrected focused source suite passed38 checks; Ruff and diff checks passed. Independent source review and bounded SQL-native acceptance passed on the corrected448641-byte SQL, SHA256 ed8c7032cdd7bd6a67dc2a41e38c1384e0173094544de63bb37e9ddac4a35429. These source checks do not themselves execute SQL.

The separate standalone-psycopg runner passed43 recorded case entries, including repeated labels, not43 unique acceptance requirements. Its single scenario invocation exited0 with empty stderr. Actual committed dispatch, caller business-root rollback, distinct failure commit/rollback, terminal/retry/cancel outcomes, jobs/inbox, full state/history/capacity comparisons, due redispatch, serial E12/E13 precedence and observed blocking-lock crossings of lease/deadline passed. Original and continuation input pins were independently verified. Existing E10/E13/W05 fixtures were not replayed.

Exact owned container cleanup was independently verified: graceful SIGTERM, exit0/Pid0, non-force removal and exact-target absence. The wrapper exited1 only because its absence assertion expected capitalized 'No such' while Docker returned lowercase 'no such object'. Raw receipts remain unchanged; this was reporting error E11-REPORT-001, not product/scenario failure or a surviving resource. The image remains intentionally retained.

Evidence: /home/faris/modkit-local-20261106/events-fenced-failure-20261109/qa-v1/runtime-observation-v1.md and the independently retained independent-native-acceptance-v1.md report in the same feature evidence tree. No further fixture or cleanup replay is required.

Q18 remains NOT RUN/outside this packet: deliberate receipt tampering, direct max-revision alteration, native B1, unknown COMMIT and transport loss. Exact final-clock equality, concurrent cancellation/recovery races, provider effects, managed native failure bridge, broader drivers/platforms/install/grants/release/ERP and original A-O acceptance remain unqualified. Caller proof of full rollback and confirmed failure/no-effect remains mandatory; structural root checks and this bounded runner do not supply that capability to applications. E31/E32/E33 remain open. Full product NOT_READY.

## E11-SR-001 correction

A terminal inbox row may lawfully have parent nonterminal_count=0. E15 integrity checks remain first; exact fence and running-state classification now precede the positive nonterminal parent-count guard. A spent fence therefore rejects as PZ003 rather than misclassifying the lawful zero count as corruption. The focused ordering regression failed before this correction; it is structural evidence only. Independent bounded runtime QA closed this regression: last-item E11 terminal count0 spent-fence replay returned PZ003 with unchanged complete footprint; original-fence replay after E12 cancelled resolved retry at count0 also returned PZ003. This covers serial terminal-producer precedence, not a concurrent race.
