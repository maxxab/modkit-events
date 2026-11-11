# Explicit held-work resolution through E31

E31 resolves **already-held** jobs and inbox work. It does not discover dead workers,
establish a provider outcome, or automatically restart/retry a handler. All native
qualification and deployment claims require separately accepted evidence.

## Application authority and durable request

The application or authorized reconciler must establish current scope/tenant
authority and independently confirm the outcome. For safe retry it must positively
establish replay safety, including reconciliation of old business transactions and
unknown effects. Evidence and binding bytes are bounded audit content, not a proof
verifier. Timeout, lease expiry, process death, absent success, or empty recovery
evidence is never enough.

Before issuance, durably retain the exact operation ID and immutable 11-field E31
request in application-owned storage. The ordered fields are work_id,
expected_revision, cycle, attempt, dispatch_id, operation_id, outcome, retry_at,
result, evidence, binding. This durable storage is an application prerequisite, not
a new Events journal. A committed Events receipt records a committed decision; it
cannot recover a lost uncommitted request.

Outcomes are:
- confirmed_success: result bytes required (empty is legal), retry_at=None.
- confirmed_rejection: result=None, retry_at=None.
- confirmed_cancelled: result=None, retry_at=None.
- safe_retry: result=None, an exact UTC datetime retry_at required.

Result, evidence and binding are exact immutable bytes, each at most 1,048,576
bytes. SQL additionally validates held-state identity and revision. Safe retry
requires lawful replay policy, remaining budget, no cancellation, and database-time
future scheduling before deadline. Terminal confirmations are not inferred from
those policy predicates.

## Paid API and explicit transaction

The optional driver leaf is modkit_events.persistence.native_execution.
prepare_resolution(execution, /, *, execution_ledger, capacity, work_id,
expected_revision, cycle, attempt, dispatch_id, operation_id, outcome,
retry_at=None, result=None, evidence, binding) returns a paid preparation handle.
The capacity argument is mandatory. Composite request/context construction occurs
after the reservation inside the existing paid construction boundary.

Use normally initialized active-domain resources and the original caller-owned
managed connection/root. The call sequence is:
1. Start an explicit root using native_sync.start_root.
2. Call prepare_resolution with the durably retained exact request and budgeted A capacity.
3. managed_lifecycle.admit(root, preparation, execution_ledger=ledger).
4. managed_lifecycle.reserve_result(ticket, result_capacity, execution_ledger=ledger).
5. native_execution.execute(ticket, result_handle, execution_ledger=ledger).
6. managed_lifecycle.read_result(result_handle, execution_ledger=ledger).
7. Explicitly finalize the caller root with native_sync.commit or rollback.

Check the actual native_sync signatures for positional/keyword arguments.
No factory or issuer commits, rolls back, opens a substitute connection, or retries.
A returned ResolutionObservation is staged. Only acknowledged COMMIT establishes
durability. Preserve caller business changes in the same root where atomicity is
required; no atomicity is promised across databases.

The transport admits exactly one row, 16 canonical fields plus cap_ok.
3,145,882 bytes is a conservative sum-of-column-caps ceiling, not an attainable
all-populated valid row and not a Python graph reservation. A and B charge object
carriers and each retained scalar occurrence, including repeated references to the
same bytes object. Caller budgets must include that overhead under the qualified
interpreter. A generic 1024-byte preparation default is not a large-request budget.

Drop caller aliases to the observation before declaring result release. Release
the result, then the ticket; drop request aliases and release the preparation.
Use existing supported root/connection/execution cleanup after acknowledged
finalization. Never manipulate counters directly. If retention/release is uncertain,
preserve obligations instead of refunding them.

## Restart and uncertain acknowledgement

After an unknown native outcome, retain the old domain's obligations and stop using
it. Do not reset, import, refund or release the old stopped-domain HELD graph.
Creating a fresh ledger/checkout inside that domain is not a recovery mechanism.

A separately initialized recovery process obtains current authority and reads the
exact durably retained request. Repeat the same E31 request and operation ID:
- If the previous decision committed, return its original receipt, original root
  xid and recorded time, even after subsequent lawful work-state changes.
- If it rolled back, the same request can execute only while current eligibility
  remains valid. For example, an elapsed retry_at may now reject. Never silently
  edit the request or generate a replacement operation ID.
- If the request or outcome evidence is missing, leave the incident unresolved.

Historical resolution_root_xid is not required to equal the recovery transaction
xid. For a newly applied decision, SQL writes the actual executing caller root.
The reconciler explicitly commits its own root. It does not repeat business effects.

## Bounded operational examples

For a confirmed successful held inbox delivery, verify application authority and
external outcome, persist the exact success request before issuance, execute and
commit it. Observe its E15 terminal resolution witness. For jobs, W02 additionally
supports the matching job observation. Rejection/cancellation uses the same flow
with the corresponding outcome and no result.

For a held job proven safe to replay, persist a safe_retry request with a suitable
future deadline-bounded time, execute and commit. This schedules retry_waiting; it
does not dispatch. A later separately authorized W05/E06 can acquire a distinct
dispatch. No actual Worker handler redelivery is promised by E31 alone.

For a lost COMMIT acknowledgement, the retained request and committed receipt allow
a fresh process to reconcile. Neither the receipt nor an in-memory request solves
crash-before-request-persistence.

## Installation and acceptance boundaries

The development schema evolves by append-only E31 SQL, preserving the old initial
SQL prefix and recording the changed full digest. E33 behavior is unchanged:
externally supplied manifest pins must match installed receipts. Synthetic test
receipt seeding is not deployment certification. No automatic receipt replacement,
startup DDL, PUBLIC grant, or production upgrade is provided here. Production
migration, least-privilege grants and manifest certification remain explicit
follow-ons.

Pure codec/fake-driver tests are not real PostgreSQL/libpq/COMMIT proof. Independent
source review, isolated native qualification for both kinds/all four outcomes,
unknown-ack branches, and E15/W02 compatibility are separate gates. Automatic E13,
E31 scanning, Worker restart, provider recovery and lossless incident handoff are
outside this feature.
