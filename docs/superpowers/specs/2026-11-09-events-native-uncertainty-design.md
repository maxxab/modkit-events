# Fixed native E32 uncertainty settlement

Status: independently source-reviewed and scoped native-qualified with limitations.
This is not complete WorkSource recovery or production readiness.

## Contract and boundaries

Uses canonical modkit-pg-ab-2 E32 only, by descriptor identity:
(work_id, token, ownership_revision, cycle, expected_attempt, failed_business_root,
operation_id, reason, evidence, binding).
ReturnContext retains one matching Fence. Every parameter is required. Revision is
positive signed int8, cycle is 1, expected_attempt is 0..1000, failed_business_root is
1..2^64-1, reason matches [a-z][a-z0-9_]{0,255}, and evidence/binding each contain at
most 1,048,576 bytes. No rollback receipt or E11 failure binding is required.

Fixed SQL adapts parameter index 5 to at most 20 decimal ASCII bytes and casts
text to xid8. Canonical request stays unsigned int. Cursor-local integer adapters
use int8 for revision while fixed SQL casts cycle/attempt to int4. No global adapters,
generic SQL compiler, automatic transaction finalization or retry are added.

Exactly thirteen canonical result fields:
operation_id, work_id, token, expected_revision, cycle, attempt, dispatch_id,
failed_business_root, reason, evidence, binding, resulting_revision, recorded_at.
The raw decoder couples every request field, maps ownership_revision to
expected_revision and expected_attempt to attempt, and validates every scalar before
constructing SettlementObservation. Return attempt is 1..1000. Revision parity follows
the existing public observation: resulting_revision > expected_revision. The pinned SQL
itself writes expected_revision+1. The returned dispatch UUID belongs to the immutable
receipt, not necessarily today's dispatch.

Physical transport adds a cap_ok boolean before these fields. Reason travels as UTF8
BYTEA; reason/evidence/binding are CASE-capped in SQL before PGresult. Maximum admitted
cell payload is 2,097,513 bytes. LIMIT 2 detects surplus rows; exactly one is required.
Metadata, binary OIDs/formats, widths, caps, nullability, row counts/tags and extra result
sets retain existing rejection gates.

## Paid occurrence accounting

Preparation A/AB counts FrozenRequest, parameters tuple, every scalar occurrence,
ReturnContext, expected tuple, Fence and every Fence field. UUIDs include their integer.
Result B/BB counts the exact SettlementObservation carrier and all thirteen scalar
occurrences, revalidating the complete request/result coupling. Aliased evidence and
binding count twice. Raw driver/decoder copies and discarded validation carriers live
only within the existing paid D frame; they are not silently retained as another result.

Measured on CPython 3.12.3 for maximum reason/evidence/binding and maximum-width
UUID/XID/revisions, with both aliased and nonaliased byte fields. The actual-image
CPython 3.13.5 paid preflight independently reproduced these graph sizes:
- A request graph: 2,098,619 bytes.
- B typed result graph: 2,098,295 bytes.
- Concurrent exact AB+BB: 4,196,914 bytes, which exceeds 4 MiB.
- Recommended explicit reservation: 4,194,304 bytes EACH for preparation and result,
  not a single shared 4 MiB total. A reservation at that recommendation plus B at that
  recommendation charges 8,388,608 bytes across the two counters.

These are complete canonical occurrence-graph charges, not process RSS or total native
driver allocation bounds. The driver-cell cap is a separate bound. The current fixed
carrier model treats startup metadata and bounded D temporaries according to existing
accounting rules; this feature does not weaken or replace those rules.

Pure tests independently calculate complete graphs, compare production sizing, use exact
successful A and B capacities, and reject one-byte-short capacities, including maximum
aliased payloads. Defaults are unchanged: callers must supply sufficient explicit A/B
capacities. Limits must also cover retained business charges, independent control and
observation ownership, future renewal, and nested construction-slot headroom. Never
budget an uncertain refund.

## Independently owned same-scope control lifecycle

This is a caller-owned schematic, not a new WorkSource or incident-handoff API.

1. Before business work, establish separate business and control ExecutionLedgers,
   reserve their executions, and attach separately owned fresh/unpooled native
   connections. Preserve the same work identity and logical application/tenant/owner
   scope. Scope is identity data, never a new fault domain.
2. If business finalization becomes UNKNOWN while the shared resource domain remains
   active, retain its original ledger/root/handles, sticky uncertainty and all charges.
   On the independent control owner, start a clean managed root with existing supported
   readiness/connection gates. Do not replace the business ledger or connection.
3. Prepare E32 with the original Fence, failed business XID, stable operation_id and
   exact evidence/binding/reason. Supply explicit paid A capacity, admit to the control
   root, reserve B, execute once and read the SettlementObservation.
4. A returned receipt is STAGED. Complete supported statement-resource release with
   local aliases dropped as required by the existing lifecycle, explicitly commit the
   control root, and require acknowledge_commit_result to yield COMMITTED.
5. Observe fresh durable state via W02 in a fresh eligible root for Workers jobs. A
   successful commit acknowledgement proves that transaction committed; failed fresh
   observation still leaves current-state verification incomplete. W02 is not
   broadened into a native inbox observer by this feature.
6. Report settlement outcome separately from original business uncertainty. No business
   ledger uncertainty, original liability or rollback proof changes merely because the
   control transaction succeeded.

Pure tests exercise independent ledgers/root identity and active-domain UNKNOWN
preservation with existing state APIs. They do not prove physical same-scope SQL
transactions, commit acknowledgement, fresh W02, or races; the scoped native evidence
below supplies separate qualification for the exercised cases.

If the shared domain is STOPPED, all same-process native work is prohibited, including
on a control checkout created before the incident. Do not reload/reset the registry,
mint another domain or ledger as recovery, refund old obligations, infer rollback from
IDLE/close/new XID, or automatically replay business work. An independently surviving
owner and bounded durable incident handoff across process fail-stop remain missing.

## Receipt, race and uncertainty semantics

- E10 committed first must remain successful; E32 cannot overwrite it.
- E32 committed first fences later E10 through revision/token change, without proving
  business rollback or absence of provider effects.
- Before control commit acknowledgement, returned receipt/held transition is only
  staged. Rollback removes provisional changes. Unknown commit stays unknown.
- Original uncertainty and liabilities remain even after durable E32 settlement.
- Same-ID exact E32 invocation can return historical immutable receipt under the SQL
  contract. It is still mutating and may settle if no receipt exists; it is not a
  read-only probe and is never automatically repeated after ambiguity.
- Same-ID changed request or cross-kind conflict rejects. A new ID must not evade it.
- Historical receipt does not prove current held state; fresh W02 does not by itself
  prove the exact operation_id receipt. No implicit reconciliation policy is supplied.
- Post-start driver/decode/publication/close failures retain existing HELD/UNKNOWN
  behavior, primary exceptions and shared-domain fail-stop. No refund or replay is
  hidden in E32 transport.

## Verification and ownership

Pure coverage: exact request/response contract, variable bounds, all ten coupling
positions, historical dispatch/revision parity, unsigned endpoints, typed publication,
full occurrence accounting, exact/short capacities, issuer adapter and request identity,
staged-only result, malformed returns, primary exception preservation, no implicit retry,
original UNKNOWN liabilities and stopped-domain rejection.

Independent source review and pure QA accepted the combined E32/E05 snapshot. Reused
pure regression: 881 passed, 29 optional-driver skips; these are not native case counts.
Scoped native acceptance covers all 22 planned scenarios across disjoint executions:
16 completed in the original partial run (all nine E32 cases and seven E05 cases), then
six passed in a separately authorized non-replay continuation on the retained fixture.
This was NOT one clean 22-case run. The original run stopped during case17 acquisition
setup; its existing immutable W01 admission was reused, not replayed. The continuation
preserved the prior16 work/history preimages and completed exact graceful fixture
removal with verified absence. An earlier read-only preflight timeout remains UNKNOWN;
the later success does not relabel either failed attempt as a pass.

Accepted E32 evidence includes active-domain logical UNKNOWN with original liabilities
preserved after independent control disposal and fresh W02 held; precreated control
rejection after domain stop; E10-first success preservation and E32-first fencing with
observed blockers; staged rollback and controlled commit-UNKNOWN; maximum native
payload; one-byte-short publication failure; and stale-Fence SQL rejection containment.
Controlled post-IDLE status distortion has a known actual command outcome, not ambiguous
network loss. Stale-Fence rejection is a server SQL failure, not network loss.
The native maximum-payload case carried 1MiB evidence, 1MiB binding and a 256-character
reason, with explicitly synthetic unsigned 2^64-1 input: it qualifies contract/wire
transport, not genuine highest-XID business provenance. The actual undersized native
result used B=2,098,243 bytes with reservation 2,098,242, distinct from the pure
maximum-width graph B=2,098,295 above.

The combined control case retained business guard, renewal result, admitted settlement
and observer root together: C/X/R=4, A/B=2, AB=4,195,328 and BB=4,194,368, plus one
separate raw oracle connection. Settlement commit and fresh W02 held then succeeded.
This measures simultaneous live logical obligations, not simultaneously executing SQL,
RSS, arbitrary workload capacity, or an exact transient construction-D peak; the sampled
D was zero. E32 still reserves 4MiB EACH for A and B, not one combined allowance.

These routes remain active-domain-only. Stopped-domain recovery, cross-process incident
handoff, general WorkSource/supervisor execution, new E11 strict rollback authority and
automatic historical-receipt reconciliation are not supplied. Historical E32 invocation
remains mutating and not automatically retryable. The existing contracts and limitations
above remain unchanged.

SQL/catalog/observations/native_sync/registry/ledger/native_profile/Workers are unchanged
by this feature. The documentation closure reran no tests or runtime operations and
changed no source, test or index files. Detailed accepted source/native receipts and
the disjoint-run history are retained by the coordinator.
