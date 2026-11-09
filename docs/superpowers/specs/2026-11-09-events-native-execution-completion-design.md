# Fixed native dispatch, guard and completion bridge

## Scope and evidence

Extends the existing native issuer to canonical E06/E08/E09/E10, alongside
unchanged E14/E28 and Workers routes. Independent acceptance now records PASS
for the bounded native packet: one short success cycle, omitted completion,
stale fencing and the public-driver unsigned-XID transport envelope. Its exact
fixture was removed gracefully. This is not broad driver, production or full
product qualification; full product remains NOT_READY. No SQL function body,
profile registry, controller or Workers runtime is added by this bridge.

## Caller API and capacity

`prepare(execution, statement, parameters, /, *, execution_ledger, context=None,
capacity=1024)` validates capacity as an exact positive integer before entering
construction, then reserves declared backing before freezing the request.
BRIDGE-SR-001 closed the exposed-capacity validation gap; direct prepare tests
reject hostile capacities without charges, hooks, I/O or new uncertainty.
None creates an empty context; selected completion statements require an exact
canonical ReturnContext with Fence (E06/E08/E09) or GuardRef (E10), coupled to
all corresponding parameters. The original request/context stay retained.

Choose preparation capacity before examining or copying application payloads:

- E06: 1053184 bytes, covering 1 MiB evidence, two 256-byte identifiers and fixed graph.
- E10: 1052672 bytes, covering 1 MiB result and fixed graph.
- E08/E09: 4096 bytes.
- The existing default 1024 remains compatible, not universally sufficient.

Recommended result reservations: E06/E10 64 bytes; E08/E09 4096 bytes for the
complete possible GuardRow. A known absent E09 result fits 64, but callers cannot
assume absence before executing and should reserve 4096. These are conservative
structural budgets for the supported 64-bit CPython 3.12 profile, not RSS or native
allocator guarantees. Exact accounting charges each occurrence, including aliased
context fields and UUID integer backing. Too-small preparation fails before I/O;
too-small result after SQL retains HELD/UNKNOWN rather than permitting retry.

The admission contract tests on the selected interpreter measured maximum E06
preparation 1050247 bytes and E10 1049857 bytes; maximum-domain unsatisfied guard
648 bytes, E06/E10 scalar 28 bytes and absent E09 16 bytes. Recommendations retain
structural margin rather than presenting these observations as portable limits.

## Fixed transport and validation

E06 returns cap_ok BOOL plus attempt INT4, maximum 5 binary payload bytes; E10
cap_ok plus ok BOOL, maximum 2. Both are EXACT_ONE. E08/E09 return cap_ok and all 11
canonical GuardRow columns, maximum 123 bytes: three UUIDs, XID8, INT8, two INT4s,
BOOL and nullable TIMESTAMPTZ/terminal_state/result_digest. The nullable terminal
state travels as UTF8 BYTEA capped 9; digest BYTEA capped 32. SQL CASE projections
null variable fields if caps fail. E08 is EXACT_ONE and E09 OPTIONAL_ONE.
Every fixed projection has LIMIT 2 overflow detection.

The issuer checks exact field names, OIDs, binary formats, widths, cardinality,
command tag/count and cap_ok before copying a bounded row. It rejects additional
resultsets and validates complete selected results with
`rows._decode_native_event_result_raw(request, rows, /)` without replacing the
retained parameters. E06 publishes exact int 1..1000 equal to expected_attempt+1;
E08/E09 require an unsatisfied complete guard and exact five-field fence;
E09 absence publishes None; E10 publishes exact True, never truthiness or None.

Cursor-local Int8BinaryDumper handles selected Events integers, with fixed SQL
casts narrowing bounded cycle/attempt. E10's validated unsigned root_xid remains
an integer in the retained request; only the D-owned temporary parameter tuple
contains its decimal string (at most 20 ASCII digits). Public StrBinaryDumper
binds TEXT and the fixed SQL uses `$3::pg_catalog.text::pg_catalog.xid8`. This
avoids signed-int8 narrowing and uses no custom driver hooks. Binary result XIDs
remain OID 5069 and unsigned eight-byte values. Temporary adapted parameters are
cleared before normal construction exit; unexpected failure retains the frame.
Connection/global adapters and canonical request identity remain unchanged.

## Manual caller transaction recipe

1. Complete existing W05 acquisition and acknowledge caller COMMIT.
2. Execute E06 using the acquired fence in a short root; acknowledge COMMIT
   before business execution or an external effect. Retain incremented attempt.
3. Start a caller-owned business root on the supported original physical
   connection. Observe E14 and execute E08 with the dispatched fence. Compare
   complete GuardRow.root_xid with that E14 observation before business writes.
4. Perform caller business writes, then E10 using the corresponding GuardRef in
   that same root. E09 is optional observation, not a required extra round trip.
5. Only actual caller COMMIT acknowledgement establishes success. Observe the
   durable job/business result in a fresh eligible root for acceptance evidence.

Fence has no expected XID field; the decoder does not invent one. Existing SQL
binds guard production to actual root and E10 checks the supplied GuardRef.
The accepted bounded native cases below establish omitted-completion commit
rejection and stale-fence rejection before business writes. They do not establish
all possible stale-fence races after business writes.

## Failure and lifetime

The original controller alone owns admission, reservation, RUNNING/COMPLETED,
paid borrowing and release. No hidden commit, rollback, connection replacement,
physical close or replay occurs. The first received BaseException remains exact,
including cancellation/cause/context/traceback semantics. Malformed rows,
publication failure, close failure or lost acknowledgement preserve charged
resources and HELD/UNKNOWN. Driver emergency closure is not rollback proof or a
cleanup receipt. Staged True is not a commit receipt.

## Focused verification

New codec and issuer fixtures cover descriptor caps, complete binary guards,
unsigned root boundaries, optional absence, metadata/cardinality/extra-resultset
faults, false unit results, cursor-local adapters, retained identity, temporary
parameter cleanup and close-failure primary retention. Contract fixtures owned
by the admission slice cover raw coupling, maximum-domain occurrence accounting,
exact/one-byte-short capacities and public-constructor tripwires. Existing native
transport/issuer suites provide compatibility checks. Synthetic fixtures do not
import the real driver or prove server execution, cancellation or release readiness.


## Accepted bounded native evidence

Independent native acceptance is PASS; cleanup is REMOVED_GRACEFULLY. Evidence
home: `/home/faris/modkit-local-20261106/events-execution-completion-20261109/qa-v1/`.
The acceptance report supersedes the result report's then-pending independent
review status. This document reconciliation is later than the frozen execution
snapshot; it does not claim the changed document bytes were runtime inputs.

- `native-result-v1.md`, SHA256
  `d256a42b00b9b249fc0b23957a5ed03511478f1a10754142f4b84569ee343fb3`.
- `independent-native-acceptance-v1.md`, SHA256
  `f728221b51e3afb418d6d0a05429050f48fa3c66a673b8f01b6d355f0c3e19fe`.
- Executed source-freeze-v2 manifest SHA256
  `9074476e8d705c5212a596f39f4d08b427ef589047e24843c362b00e9b8f77dd`.
- Integrated Events SQL SHA256
  `ed8c7032cdd7bd6a67dc2a41e38c1384e0173094544de63bb37e9ddac4a35429`;
  unchanged Workers revision `14bba197e6d09dcda6826ba12113d02065698463`.
- Original packet manifest SHA256
  `4d5f80c43d823cb1186709df3efd40c6d81bf1fd60df0aab4fff38a8d32d9f2b`;
  original input manifest SHA256
  `25f20d9f4c8f345fe748e0a2f5cfc797db2395821ff47413e58c465f1381c592`.
- Reviewed continuation manifest SHA256
  `f88b75dff888af7ebdab766c2a4989ae4478db2490a05fbcb91c79cf66b0e716`;
  corrected runner SHA256
  `a9ec7416c192dabd46cb48ac1a08096e0cb5a2a6bfcf116339807d3fff452595`.
  Original and corrected inputs were reverified after the scenarios.

### Preserved fixture failure and reviewed continuation

The first run installed the isolated schema/business table and passed the
unsigned-XID/full-revision transport envelope. It then failed with
LOCAL_INVALID_ARGUMENT before W01 because the fixture supplied ABSENT
recovery_metadata as `{}` instead of `b''`. This remains a recorded fixture
failure, not a product failure or successful first run. Read-only reconciliation
found no active runner/client and no application rows. A separately reviewed
runner changed only that argument and continued in the same container without
restart, schema setup replay or transport-envelope replay. The original failure
and inputs were preserved.

### Actual transaction observations

Each of three separate jobs used real managed W01 submission with acknowledged
caller commit, W05 acquisition with acknowledged commit, and native E06 returning
attempt 1 with a separately acknowledged dispatch commit before the business root.

Success: E14 observed the actual root. E09 was absent, E08 returned a complete
guard whose root matched E14 before the business insert, and E09 then returned
the same guard. E10 staged exact True in that same business root. An independent
connection could not see the insert before acknowledged caller COMMIT. Fresh
W02 validated succeeded state, exact result and attempt 1. Independent reads
counted one durable business effect, one succeeded attempt and one complete-history
row; outbox stayed empty. The history count plus coherent W02/E15 witness is not
new independent field-by-field history qualification. Accepted direct E10 evidence
remains the basis for the broader history claim.

Omitted completion: E08 and business insert without E10 caused actual COMMIT
PZ001, unsatisfied finalization guard. The exact received primary and its
cause/context/suppression were preserved. Root UNKNOWN and the retained COMMIT
operation with running=False were asserted; no HELD state is invented for this
commit operation. Fresh observation after transport closure showed unchanged
Events-table footprints and no business/guard effect. These observations do not
mint a managed rollback or cleanup receipt, release authority or refund.

Stale fence: changing only the token caused native E08 PZ003 before business
mutation. The exact primary survived; execution HELD/root UNKNOWN and uncertainty
were retained. Ticket release was denied without capacity change. Events-table
footprints remained unchanged, with no business/guard effect. Physical transport
closure was not treated as a cleanup receipt or failed-result refund.

The original public-driver envelope verified binary xid8 values 1, 2**63-1,
2**63 and 2**64-1 using bounded decimal text::xid8, plus revision 2**63-1 through
INT8 binary transport with exact metadata/bytes. This proves those transport
ranges, not naturally allocated high transaction IDs or fabricated high-root
guards/revisions. The business scenarios used actual observed roots. The pinned
native profile was psycopg 3.3.8/libpq 180006 with PostgreSQL 180001.

### Exact cleanup and limits

Only CID
`77c5dcda4ffb8d24b54ecdf5a5246daf9c5d8b9debf8131518be5aeb00eb85ff`
was used, with existing image SHA256
`1ce96cce5978a21ae11f09b3ad3cb619e1d0c7297c8f3becae51c6a9bb2979b0`.
Recorded exact-ID TERM succeeded; bounded wait and stopped inspection showed
exit 0, Pid 0, no OOM and no restart. Non-force removal succeeded, and subsequent
inspect returned the exact no-such-object CID with empty object list, proving
absence rather than a generic daemon/socket error. No further fixture operation
is needed. Continuation `result.json` SHA256 is
`446901a35be19e018fbfceacee2931b243f2ed5bb13417d29725b53ce231ceb6`.

Maximum-domain retained-graph measurements above remain pure 64-bit CPython 3.12
evidence. The native image used CPython 3.13 for representative bounded cases,
not maximum-payload or maximum-domain retained-capacity qualification. These are
not RSS bounds. This packet does not implement or qualify a concrete WorkSource,
B1/E11 failure settlement, renewal/supervisors, native outgoing E02/provider effects,
broad cancellation/concurrency races, E31-E33 or production readiness. Full product
remains NOT_READY; independent bounded native acceptance is not a public release.
