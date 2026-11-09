# Managed native failure after explicit confirmed rollback

## Scope and requirement

The narrow database-local application-failure path implements the original roadmap
Milestone B and Milestone I trace7. Accepted E11 SQL and native E06/E08/E09/E10 are
reused. B1 is historical shorthand, not an existing API or rejected-COMMIT proof.

Supported handler: synchronous, database-local, exclusive cooperative ownership
of the fresh/unpooled original connection; no providers, outgoing events, nested
transactions, raw transaction bypass, replacement connections or concurrent direct
use. Caller classifies the application failure and lawful retry disposition.
Database rollback does not establish external no-effect.

Native statement failures, HELD/UNKNOWN, INERROR, prior ledger uncertainty,
aborted-COMMIT and emergency close are not promoted into proof. E32/native
reconciliation, arbitrary-duration renewal, WorkSource and supervisors remain
outside this change. Full product remains NOT_READY.

## Caller-owned sequence

1. Submit with W01 and acquire with W05, using the accepted caller-owned
   transaction boundaries. Execute E06 and acknowledge its actual COMMIT.
   Retain the dispatched Fence.
2. Start the business root. Execute native E14 then matching E08. E09 may
   corroborate E08 but is not required.
3. Release successful statement result/ticket/preparation obligations, then perform
   database-local work. A synchronous application exception leaves managed ACTIVE
   and physical INTRANS.
4. Explicitly call native_sync.rollback(root, execution_ledger=ledger,
   confirm_failure=True), or the root convenience method. Acknowledge the exact
   returned ROOT_END using acknowledge_root_end.
5. Prepare fixed E11 with Fence, actual failed XID and justified disposition,
   reserving enough capacity for both request and normalized proof backing.
6. Call managed_lifecycle.bind_failure_settlement(preparation, failed_root,
   rollback_receipt, execution_ledger=ledger). Keep failed root retained.
7. Start a distinct settlement root on the same checkout/execution/ledger; admit,
   reserve result and execute E11 through the shared native issuer.
8. TRUE is only staged. Release statement obligations, explicitly COMMIT, and
   acknowledge the exact normal COMMITTED receipt. Fresh durable work/attempt/
   history observation corroborates outcome. Missing/aborted/unknown acknowledgement
   is not success. Never automatically replay E11.

The adapter never replaces a connection or silently finalizes a caller transaction.
Native acceptance must independently observe business effects absent after rollback,
and durable outcome after acknowledged settlement COMMIT.

## Native provenance

The shared issuer calls _observe_native_result_paid after set_result, successful
completion and validate_ticket, inside its existing live D reservation. The hook
checks canonical ticket/result, exact issuer reservation, populated result and
COMPLETED/nonrunning operation. Public result population without that issuer
cannot mint provenance.

Root storage contains bounded primitives only: unsigned E14 XID, five Fence
scalars with UUIDs copied as integers, integer guard ID, flags and preparation
stamp. No GuardRow/request/exception/traceback/driver graph is retained there.
E14 precedes E08; guard root/Fence must match. E09 alone cannot establish proof.
Absent E09 after eligible E08 or conflicting root/target/guard permanently disables
proof without invalidating otherwise normal statement success. Hook failure first
withdraws eligibility and then follows existing issuer HELD/UNKNOWN containment,
including failures after COMPLETED and secondary ledger failure.

## Strict versus ordinary rollback

confirm_failure is exact bool at both public boundaries, before truthiness,
mode branching, D charge, reservation or I/O. Ordinary rollback retains its
existing behavior, including INERROR recovery, and cannot bind E11.

Strict deterministic preflight requires valid current ACTIVE root, usable profile,
no prior uncertainty/blocked root, no competing operation, valid native witness
and original live INTRANS connection. Known rejection leaves state/counters
unchanged after normal D exit.

Under existing FINALIZING/live D the fixed no-assignment probe is:

    SELECT pg_catalog.pg_current_xact_id_if_assigned()

binary=True, prepare=False, no parameters; inspect public PGresult without custom
row loaders. Require TUPLES_OK, one row/column, binary tuples, canonical output
name, xid8 OID5069, format1/size8, SELECT1 command/cardinality metadata, exact
eight-byte nonnull positive unsigned XID equal to witness, and no extra result.
Close cursor normally, recheck original INTRANS identity, call actual
psycopg.Connection.rollback and require original IDLE.

Only the entire normal path records stronger verification. Replacement transactions
completed before the probe are detected. Hostile raw replacement after observation
is unsupported under exclusive ownership, not physically prevented.

Malformed/mismatched probe: INVALID_OBSERVATION, UNKNOWN/blocked and no actual
rollback. Unexpected driver/accessor failure preserves the first BaseException,
cause/context/suppression and existing containment; never retries.
A normal rollback return with false post-IDLE uses known=False, drops aliases,
exits D normally, then raises OUTCOME_UNKNOWN. D may refund, while R and stopped
operation remain retained UNKNOWN. Escaping error graphs retain D. These cases
must not be conflated.

## Error, proof and release protocol

Preflight precedence: exact types; canonical handle/ledger identity; unusable/
prior-uncertainty/blocked; competing operation; ACTIVE/current; witness; physical
status; reservation. Invalid public types: LOCAL_INVALID_ARGUMENT. Invalid/stale
identity or missing witness: INVALID_OBSERVATION. Unusable profile, uncertainty or
known INERROR: PROFILE_REJECTED. Competing operation: RESOURCE_BUSY. Capacity:
CAPACITY_EXCEEDED. Known local errors occur outside normal construction cleanup;
unexpected accessor errors preserve primary and contain, never masquerade as
harmless known rejection.

Bind requires exact acknowledged strict ROOT_END, retained root generation and
original C/X/L, matching native Fence/XID and current immutable E11 carrier.
One A per failed R: repeated same-A bind INVALID_OBSERVATION; different associated
A RESOURCE_BUSY. Malformed carrier LOCAL_INVALID_ARGUMENT, insufficient existing
A capacity CAPACITY_EXCEEDED. No partial link is published on known rejection.

Binding pins exact request/parameter/context/expected/Fence identities and
normalizes all ten parameters. UUIDs become exact integers; UTC timestamp becomes
eight integer fields; strings/bytes remain exact immutable values. Admit and start
repeat shape/identity/snapshot/root checks. Equal replacement tuples/contexts,
mutated UUID/Fence, stale root, changed statement or missing proof cannot reach
E11 I/O.

Atomic start installs RUNNING/exact issuer and permanently consumes failed-root
authority together. Competing start, lost return, transport/commit uncertainty or
later known rollback never restores authority or authorizes replay.

Acknowledged ROOT_END leaves R charged before binding. Releasing unbound ENDED R
abandons proof; later bind rejects. Associated R release is RESOURCE_BUSY.
Releasing unstarted A drops association and permits corrected bind, never R refund.
After start, A release drops dependency but never clears consumption. Repeated
A/R removal is INVALID_OBSERVATION; exact retained receipt acknowledgement stays
idempotent. Unexpected cleanup failure does not prove a completed refund.

## Accounting and qualified reservations

Fixed witness remains under charged R. Snapshot/identity pins remain under A/AB;
no new registry/budget. All construction/probe temporaries remain under existing D.
Binding admission checks twice the full request graph plus binding carrier plus
normalized snapshot, recursively counting timestamp fields and every repeated
reason/evidence occurrence. Second raw-graph allowance covers original identity
pins retained if carrier fields are replaced.

CPython3.12.3 maximum canonical inputs (cycle exactly1, maximum UUID/revision/XID,
attempt1000, retry timestamp, reason256 and evidence1MiB):
- Raw request:1,050,004 bytes.
- Normalized snapshot:1,049,624 bytes.
- Binding carrier:96 bytes.
- Total A backing:3,149,728 bytes.
- Recommended E11 preparation capacity:4,194,304 bytes.
- TRUE:28 bytes; recommended result capacity:64 bytes.
- Conservative fixed root witness mapping:1,188 bytes; structural allowance
  4,096 bytes per charged R bounds this component on this interpreter.

These are Python retained-graph occurrence bounds, not RSS/native-memory/platform
claims. Maximum XID transport does not qualify a live root/fence. Requalify on a
different interpreter. Configured capacity must cover simultaneous A/B obligations;
nothing expands automatically.

## Bounded native acceptance and verification limits

Independent source and separate native QA accepted this explicit strict-rollback
application-failure profile. Accepted source manifest:
25c69d66ff1204eb78c5c5eafba9c558f51f7e892c8e7c365259c5c97e3c0090.
The run used the original accepted E11 SQL, 448,641 bytes, SHA256
ed8c7032cdd7bd6a67dc2a41e38c1384e0173094544de63bb37e9ddac4a35429.
It had no E32 dependency.

The separately released native packet ran once and passed in 29.6772 seconds.
Runtime assertions qualified psycopg 3.3.8 binary transport and PostgreSQL 18.1;
this is not a broader driver/server qualification.
Terminal failed and lawful application_safe retry_waiting cases each demonstrated
committed W01/W05/E06 setup, native E14/E08/E09 provenance, released statement
obligations, a database-local write/application exception, actual strict full
rollback and exact receipt acknowledgement. Fresh observations confirmed business
and guard absence and unchanged Events preimage before settlement.

Distinct-root E11 returned staged identity-True while a fresh observer still saw
the prior state. Only after actual acknowledged settlement COMMIT did fresh W02
and SQL observations confirm the intended terminal/retry state, failed attempt
and evidence, one correct failure-history entry, cleared token/lease and increased
revision. Business/guard/outbox effects remained absent, with normal R/A/B/D
release and no uncertainty in these two cases.

A separate trace replaced physical XID 766 with 767 before the strict probe.
The probe rejected INVALID_OBSERVATION/unconfirmed, left the replacement
transaction INTRANS, and did not enter E11. Proof stayed unverified/unconsumed;
Events preimage remained unchanged and business effects absent. R1/D1 and
C1/X1/P1/V1 remained charged, with A/B0. Closing that raw connection was transport
disposal, not refund or rollback proof.

Native single-use evidence establishes consumed-state persistence through E11,
A release and successful settlement COMMIT. Actual replay rejection, lost-start
return and competing admission remain pure/source-qualified; no native scenario
was replayed to claim those properties.

All 24 representative paid fixture preparations were pure-constructed on runtime
CPython 3.13.5 before database setup. This qualifies these exact fixture inputs,
not maximum-domain 3.13 accounting or RSS. The 3,149,728-byte maximum graph and
exact/one-byte-short capacity evidence above remain CPython 3.12.3 pure evidence.

Cleanup was independently accepted for exact container
5c4f14b6dc05ce16927419682d4ab64c8f792c32d73a6ea59ce6ff32acb6abc2:
graceful TERM, wait exit0, stopped inspection with no OOM/error, exact-ID removal,
and exact-target absence verification. Result status PASS and cleanup
REMOVED_GRACEFULLY were corroborated by raw operation records, not wrapper
status alone. No resource remains assigned to this fixture.

Evidence resides in events-native-failure-20261109/qa-v1:
native-result-v1.md, native-evidence-pins-v1.json, runtime-v1/result.json and
runtime-v1/10.stdout. The accepted packet manifest is
b0732e54bf94927726beb15c91398d53f7186b344a29e5c93a5b05493232f175;
all 82 packet pins were reverified unchanged after execution. The independent
saved-artifact postrun recheck also passed, recorded in
review/independent-native-recheck-v1.md (SHA256
d8254b105e48dec98f012de223f57303a49aa1024e130ea40e6a7adad4b7ae1b).

Author pure tests additionally cover strict-probe metadata/errors, primary
identity, boolean/preflight gates, ordinary receipt rejection, retention,
single-use/association, mutation, exact/one-byte-short capacity and maximum scalar
graphs. Synthetic drivers alone do not prove database behavior.

Acceptance does not qualify HELD/UNKNOWN recovery, provider/outgoing-effect proof,
uncertain settlement reconciliation, native E32, hostile concurrent post-probe
protection, arbitrary-duration renewal, WorkSource, production or full-product
readiness. Prior broad E11/bridge fixtures remain consumed and must not be
replayed. Full product remains NOT_READY.
