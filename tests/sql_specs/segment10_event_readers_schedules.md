# E16/E34 prospective schedules and coverage

AB-SQL v2, NOT_RUN/not parsed. Concrete design: external foundation/event-readers-v2-corrected/design-v2.md. Current production SQL and accepted S8/S9/setup remain frozen. segment10_event_readers.sql needs future reviewed E16/E34 bodies and a separately approved trusted-owner READ COMMITTED transaction with final full rollback. It is one DO, not a standalone installation script.

Instantiated owner fixtures: three coherent inbox candidates at sorted IDs10/20/30; coherent inbox40 later updated only at work.updated_at=infinity; work-only inbox50; coherent job60. All installed subtype rows pass intact composition triggers. Existing private framing helpers produce setup intent, while target observations are checked against supplied IDs/bytes/state/half fields. No public producer provenance is asserted.

| Requirement | Proposed control | Current status |
|---|---|---|
| E16 true absence / exact singleton / original evidence | count0 and STRICT row + supplied Work identity/evidence and all4half fields | AUTHORED NOT_RUN |
| Subscription partition / indexed missing-half discoverability | other subscription count0; work-only50 event lookup count0 | AUTHORED NOT_RUN; not uncertain admission absence |
| E16 malformed selected composition | unsupported work timestamp40 exactPZ012, normal-return sentinel | AUTHORED NOT_RUN |
| E16 complete input validation | NULL/empty/whitespace/invalidUTF8/257byte subscription and event | AUTHORED NOT_RUN |
| E34 zero/one / dedup | count0; STRICT event-only, key-only, direct+key+event singleton | AUTHORED NOT_RUN |
| Three split winners and returned ordering | exact UUID array by returned ordinality; all3 supplied evidence/half records | AUTHORED NOT_RUN |
| Direct-key and event-key overlap | exact2element ordered arrays | AUTHORED NOT_RUN |
| Wrong-kind direct job evidence | STRICT job row, actual intent/scope/material; false+4NULL | AUTHORED NOT_RUN |
| Missing half / malformed later branch | direct50; full result aggregation validdirect+unsupported-time event40 or key40 exactPZ012 | AUTHORED NOT_RUN |
| True absent-work orphan | separate setup insertion blocked by intact BEFORE INSERT triggerPZ012 with normal-return sentinel; no installed orphan or FK23503 claim | AUTHORED NOT_RUN; impossible reader fixture under intact trigger/FK |
| Input framing / kind / required fields | inbox-only/NULLs/trailing scope/empty key/event rejected PZ006 | AUTHORED NOT_RUN; E17's broader accepted framing controls reused as bounded evidence, E34 delegation/bridge source challenge required |
| Final full row footprint |12tables+3scalar sequence states, before/after family | AUTHORED NOT_RUN; not attempted-write proof |

Still uninstantiated: true SHA256 event/subscription collisions and cross-branchPZ012-over-PZ002 runtime combinations; defensive orphan and opposite-half sentinel branches under intact composition triggers/FKs; unsupported isolation/native coercion matrix; E34 valid optional/Unicode/NUL/max scope forwarding; exhaustive installed60/61wire ABI/all56+suffix variants; effective owner/default ACL/membership/temp/overload; two-session fixed snapshots and following-command visibility; query plans/cost/index drift/performance; public E03 atomic admission and full-byte arbitration;3driver recipes/artifacts/platform/all84/application/migration gates. No source/pure-decode result substitutes for these service checks.

Root selected phased architecture in event-readers-contract-decision-v2.md, conditional on actual-source obligations; S10 correction independent closure still pending. Independent source challenge must verify the proposed deterministic event-only-before-E17 phases, complete input validation before discovery, raw cardinality/presence/ID exactness, identical indexed key predicates, overlap proof, NR-2 tags/no-row sentinel propagation, no duplicate E15 for overlap, and every integrity check before representability/projecting. MATERIALIZED alone is not an ordering proof.

Future snapshot schedule: two owned sessions, explicit READ COMMITTED roots; sessionA holds a reader command/snapshot while sessionB changes a coherent candidate and commits using a separately reviewed lawful producer or constrained owner setup. A single invoking STABLE read must retain one whole old/new composition; following A read command may observe committed new state. Do not add sleeps or same-command DML visibility assumptions; deterministic synchronization, exact data oracles/footprints and root-owned cleanup must be designed before execution. This is a plan, not an executable passed schedule.

Root owns isolated environment and separately reviewed missing-function RED modes first. This fixture packet supplies no E16/E34 runtime RED proof; root owns any separately authorized current RED receipt. Earlier E18/E17 REDs and S9GREEN cannot substitute. Setup/signature errors do not count as target failures. Any future GREEN needs exact source/fixture/setup pins, normal exit/empty stderr, target DO completion, explicit ROLLBACK/final marker and independent schema0/role0 aftermath. Body release remains pending S10-R1/R2/R3 closure and root authorization. Fresh user confirmation remains mandatory before PyPI or a publication-triggering tag.
