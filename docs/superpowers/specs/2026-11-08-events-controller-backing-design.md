# Canonical controller backing and operation lifecycle

## Scope and intent

Extend the existing canonical managed controller so a later native E14/E28 issuer can consume the exact paid immutable request and retain the complete typed result. This is source preparation, not native statement execution, driver qualification, pool support, or Workers W01-W05 readiness.

The selected implementation reuses resource_lifecycle's registry/mutex, ExecutionLedger, managed_lifecycle's existing preparation/result envelopes and single physical operation slot. Five accepted controller modules and two accepted test files are integrated from their reviewed frozen source. No second executor/controller, generic descriptor compiler or reverse Workers import is added.

## Alternatives

Serializing an unrelated bookkeeping request would not charge or bind the values actually executed. A parallel executor would duplicate authority. Both are rejected. Extend the existing typed envelopes and operation state in place, using the existing raw validators and finite E14/E28 shape, while preserving legacy bytes preparation/result controls.

## Typed backing

set_preparation accepts existing exact bytes or an exact FrozenRequest. Typed requests must pass the existing raw E14/E28 canonical-identity, immutable-parameter and empty-context checks. It retains the exact FrozenRequest object rather than a serialization or a substitute request. Request construction remains caller-owned and must occur after envelope reservation and before admission. Private reflective mutation of frozen values is unsupported.

Typed backing is charged using sys.getsizeof of the complete finite retained value graph: request carrier, parameter tuple, scalar values, empty ReturnContext and its tuple; result carrier and every scalar field including UUID integer storage. UUID.int must be an exact bounded 128-bit int, and UUID.is_safe must be one of the known SafeUUID singleton values; the public UUID constructor does not guarantee those field types. Retained datetime values must be exact datetime values in timezone.utc; no arbitrary tzinfo graph is accepted. Shared canonical statement metadata and immutable process-wide singleton state are excluded. References shared across fields are conservatively counted again. There is no generic object traversal or user-supplied size callback. Existing byte payloads retain their established len-based budget. These are explicit Python backing charges, not an RSS/native-buffer/traceback or temporary-allocation bound. Construction slots continue to bound concurrent construction/escaping frames. Native pre-copy and transient driver bounds remain a later issuer requirement.

set_result accepts bytes only for a legacy bytes preparation. For a typed request, it accepts the matching int, complete immutable OutboxRow, or optional None and reuses _decode_columns_raw/_decode_outbox_raw and exact E28 event-id coupling before publication. Do not call the raw request wrapper during result validation because it replaces the retained parameter tuple; the execution request graph must remain unchanged. An explicit populated flag distinguishes absent E28 from an unset envelope. Typed values are visible through read_result only after successful operation completion. Preflight the original retained scalar types and exact UTC tzinfo before raw decoding, because wire validators may normalize UUID strings or invoke timezone callbacks. Validation of a transformed copy does not validate the original retained graph. Expected validation rejection produces a fixed local error; unexpected BaseException keeps construction charged and permanently contains the domain.

## Same-controller operation state

Admission creates ADMITTED, running=False. The private issuer-only _start_operation(ticket, result, ledger) requires the current exact typed preparation, exactly one reserved empty result belonging to that ticket, active exact root and ledger, and usable original physical record. It transitions to RUNNING, running=True and returns the same retained FrozenRequest. Reserve-result and publication cannot attach to another operation or ledger.

The issuer calls set_result only after actual driver work and complete materialization have returned, while the operation remains RUNNING. _complete_operation(ticket, ledger, known=True) then requires that selected result to be populated and transitions to COMPLETED, running=False. Repeated starts/completions reject; neither receipt reconstruction nor replay permission is created.

_hold_operation(ticket, ledger) records HELD, blocks the current root and adds sticky OUTCOME_UNKNOWN. It does not clear running. This permits a cancelled waiter to express uncertainty without pretending its underlying work stopped. _complete_operation(..., known=...), called by the actual worker after physical work stops, accepts either exact bool after HELD, clears running and always retains HELD. The known flag must be an exact bool, never a truthy substitute. A previously held operation cannot become successful even if a late result arrives.

On unknown worker completion, mark HELD, root UNKNOWN and running=False atomically under the canonical lock, then publish OUTCOME_UNKNOWN outside that lock. HELD immediately blocks release even if the ledger union fails; unexpected failure retains construction charge and contains the domain. Hold-before-completion remains running=True.

Unknown/held operations retain their preparation, result envelopes and single physical gate, including after actual completion. There is no new recovery/refund API. Existing future recovery design must independently establish when failure-retained graphs may safely be dropped.

## Release and safety rules

release_ticket and release_result reject whenever the operation is running or held. Preparation release remains blocked by its borrow; root release, abandonment, finalization, cleanup and detach remain blocked by the occupied gate. The cooperative fresh/unpooled profile has no pool-return API; this work adds none.

No begin, commit, rollback, connect, close, cancellation or replay is added. Native_sync is copied unchanged and remains an explicit optional lifecycle issuer. A driver emergency close will not establish a caller rollback or physical-close receipt. Actual public psycopg interruption, logging, privacy and noninterference qualification remains separate.

## Verification

Reuse process-isolated lifecycle fixtures solely to exercise real canonical state and budget behavior; they do not establish database outcomes. Test exact object identity, full graph capacity and overflow, None publication, incorrect complete row/request coupling, wrong ledger/root, duplicate/late transitions, unknown retention, and thread barriers proving no resource release while running. Re-run existing lifecycle/codec/contracts, artifact checks, available base suite and Ruff. Independently review design and final exact source before local feature/changelog commits. Do not import or execute a native driver during this source-only task.
