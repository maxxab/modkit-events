# Conventional native execution: source decision and qualification plan

Date: 2026-11-08 UTC. Status: architecture decision prepared under the user's delegated ownership; independently review before native implementation. No native caller, driver behavior, connection setting or runtime is changed by this document.

## Product requirements and the design assumption being revised

The original MODKIT-IMPLEMENTATION-PLAN.md requires an active caller-owned transaction, no silently opened second transaction or commit, same-root atomicity, full business rollback before a separate failure root, reconciliation of uncertain commits, bounded execution, and no release while underlying work is still running. Its automatic destructive cleanup prohibition is in the retention section and concerns stored work/history/payload retention. It does not require a database driver to leave a broken socket open after interruption.

The stronger promise that no dependency may ever cancel or physically close a connection before a Modkit cleanup permit appears in agent-authored native lifecycle design. foundation/t2-v2-contract.md identifies itself as a proposal whose final selection is root-owned; foundation/t2-v2-contract-decision.md explicitly records a Lead selection. No direct user-authored ban on ordinary driver emergency cleanup was found in the original plan or retained AGENTS-user-instructions.md. Historical native-guarantee-reconciliation-v27/reconciliation.md treated its selected strict profile as requiring a user exception without quoting a direct user instruction for that stronger promise.

That internal assumption is revised here. This does not waive the original product requirements or any actual operational permission, independent review, E10/direct-QA, service/fixture, installation, ERP, security or release gate.

## Selected standard approach

Use supported public psycopg synchronous Connection/Cursor or RawCursor operations through the existing Events-owned canonical lifecycle and shared operation gate. Do not override Connection.wait, copy private generator loops, patch installed driver code, suppress signals/logging, add another registry/controller or hide another connection.

Package-owned statement execution never begins, commits, rolls back, reconnects or swaps the caller's root. Caller-selected lifecycle entry/finalization remains explicit. The supported driver may perform its own interrupt cancellation and emergency connection closure as part of the public call. That behavior is observable failure handling, not successful application transaction finalization and not a Modkit cleanup acknowledgement.

The already selected received-primary rule remains: preserve the actual BaseException object, cause/context/suppression and received traceback suffix at the first package catch. Do not promise to reconstruct interrupts or traceback frames the driver replaced before that catch.

## Exact pinned driver behavior

The local pinned psycopg 3.3.8 source is /home/faris/modkit-native-v2-venv/lib/python3.12/site-packages/psycopg. connection.py SHA256 is 0095cbe8262b43645f54611b817226ecab68a24252a1d38afbdfdc6d72573ab4; _connection_base.py SHA256 is 14115b0bdcb81125b3c340340b4e8e674bb1ae03f4b320c94c2b93d30462f36e. These hashes were rechecked by reading, not importing the driver.

Cursor.execute calls Connection.wait. connection.py:479-516 catches KeyboardInterrupt/SystemExit while ACTIVE, tries cancellation, waits again, and may log a fixed warning and finish the connection on timeout. Its _try_cancel at343-349 logs an Exception with a fixed prefix and %s. The public cancel_safe documentation explicitly says successful cancellation is not a guarantee of server cancellation.

The cancellation error construction follows _connection_base.py:317-320 to generators._cancel:106-119 and the libpq cancellation error message. This identifies a cancellation transport diagnostic, not a query result or a query-parameter formatter. It is not a proof that every possible driver, TLS, logger or application callback diagnostic is secret-free.

Earlier exact-version source investigation is already complete in public-wait-source-v29/report.md. It did not establish a supported wait override. Repeating that search or implementing a textual private-loop workaround is not the next step.

## Single authority and uncertainty rules

- Keep the existing canonical resource domain, original physical connection identity, root association and exact ExecutionLedger. No facade owns a second ticket or independent uncertainty flag.
- Reserve and freeze the immutable request before admission. Keep complete request/result materialization charged under the existing lifecycle, including failure-retained graphs; a payload-byte count is not a process-RSS bound.
- Hold the shared operation ticket while the actual driver call is running, even if a caller await is cancelled. Do not infer thread completion from cancellation.
- On returned driver exception, malformed result, missing acknowledgement, unexpected close or failed postcondition, publish sticky unconfirmed/UNKNOWN state before any possible later use. No success result or replay permission follows.
- An observed closed/IDLE connection does not prove rollback, COMMIT, explicit physical-close issuance or refunded authority. Driver emergency closure does not mint a cleanup receipt. Keep affected lifecycle records charged unless a separately reviewed existing terminal rule actually applies.
- Explicit cleanup occurs only after actual I/O has stopped and the existing lifecycle permits it. A secondary cleanup failure cannot replace the received primary. No automatic statement/COMMIT/close retry is added.
- An active aborted root, nested transaction, pool transfer or replacement driver cannot silently become an eligible new root. Enforce the selected supported profile using public observations and documented cooperative ownership limits.

## Diagnostic privacy and noninterference

The original prohibition on plaintext credentials in diagnostics remains. Modkit must not log raw parameters, rows, DSNs, secret references, arbitrary exception text or protected material. It uses fixed diagnostic codes and safe correlation fields. This revision does not give permission to transmit secrets.

Application-owned logging remains application-owned; do not alter global handlers, disable warnings or install a filtering workaround. Distinguish normal driver cancellation diagnostics from unproved possibilities. Qualify actual selected driver and logger paths using nonsecret sentinel data and bounded fault cases. If a concrete supported path exposes credential/payload values or changes an already established business outcome, fix it through a supported narrow interface or report that specific remaining incompatibility. Do not waive the product secrecy/noninterference requirements, and do not prohibit every public driver API merely because arbitrary application hooks can fail.

## Implementation order and tests

1. Integrate the pure E14/E28 descriptor/binary codec prerequisite. Its exact accepted production dependencies already exist in the private checkout. This provides no native execution and enables no W statement.
2. Independently review this revised lifecycle boundary and the exact existing canonical lifecycle dependencies to be brought into the private checkout. Select only reviewed source from frozen packets, not the protected live WIP wholesale.
3. Implement the first native E14/E28 statement path using the existing common gate, request/result backing and explicit caller root. Reuse the pure descriptor and complete raw request/Outbox validation. No new controller, generic callback executor or fake readiness receipt.
4. Test-first local source cases for exact root/ledger/spec mismatch, busy admission, immutable request snapshots, all-result validation, unexpected failure identity, sticky uncertainty and held-running exclusion. These are source tests, not real driver proof.
5. Under a separately released isolated native fixture, qualify normal E14/E28 execution in the same caller transaction, explicit caller rollback/commit behavior, binary metadata and bounds, and cancellation before/during/after driver return. Exercise ordinary interrupt, cancellation failure, timeout-driven close, secondary close failure and a failing application log handler with nonsecret sentinels. Assert no hidden adapter transaction, no replacement connection, no staged result after uncertainty, no replay, no running-ticket refund and preserved received primary. Record actual callback/sink contents; source-only checks cannot certify them.
6. Add separately reviewed typed operation plans and complete materialization for remaining Events operations and Workers W01-W05 through the one controller. Native success does not qualify either SQLAlchemy PostgreSQL driver recipe.

The current task completes step 1 and prepares this decision; steps 2-6 remain unfinished and must not be labeled ready from a pure test pass. Final migration/grant manifests and E33 readiness are still absent.

## Workers consumer contract to preserve

Workers owns its closed descriptors and typed decoders, consuming shared StatementSpec/FrozenRequest types. No reverse Events import of Workers is allowed.
- submit -> W01 staged JobAdmissionObservation, never commit acknowledgement.
- read_job -> W02 complete JobRecord or None.
- list_jobs -> W03 complete bounded tuple of JobRecord.
- find_jobs -> execute W04 lookup only; frozen W01 expected_submission is comparison evidence and must never execute.
- acquire -> W05 complete header-first ScanPage of JobClaimObservation. Preserve retained E04 postimages and fresh internal material snapshot; do not reconstruct with later E15/W02 calls.

All parameters freeze before admission/await, canonical descriptor ownership must be exact, and every row must validate before exposing any prefix. W05's existing accepted dependency remains Events60eac7ac7311c7e45bbccbcea2a22a1de8f7ad7e; this source decision does not replace that evidence.

## Alternatives

Retaining a universal no-dependency-cleanup promise would leave ordinary supported psycopg unusable and has no established supported alternative. A custom wait loop/private generator driver adds fragile complexity and is rejected. Automatically choosing an ORM or another driver changes the required recipe and does not qualify its ownership/diagnostics. The selected public-driver behavior with conservative UNKNOWN handling is the conventional approach consistent with the original product requirements.

## Durable source index

- Original product requirements: /home/faris/modkit-handoff-20261106/handoff/2026-11-06/jobs/modkit/MODKIT-IMPLEMENTATION-PLAN.md.
- Earlier transport constraints: /home/faris/modkit-handoff-20261106/handoff/2026-11-06/jobs/modkit/TRANSPORT-AND-QUALIFICATION-HANDOFF.md.
- Retained direct user instructions: /home/faris/modkit-local-20261106/docs/handoffs/AGENTS-user-instructions.md.
- Internal selected native design: /home/faris/modkit-local-20261106/foundation/t2-v2-contract.md and /home/faris/modkit-local-20261106/foundation/t2-v2-contract-decision.md.
- Later conflict/source investigation: /home/faris/modkit-local-20261106/foundation/continuation-v3/dot-events-review-20261107/native-guarantee-reconciliation-v27/reconciliation.md and /home/faris/modkit-local-20261106/foundation/continuation-v3/dot-events-review-20261107/public-wait-source-v29/report.md.
- Exact received-primary contract: /home/faris/modkit-local-20261106/foundation/continuation-v3/native-b1-design-correction/received-traceback.md.

## Exact next source slice

Immutable existing-controller copies are under /home/faris/modkit-local-20261106/foundation/continuation-v3/native/format-correction/after/. The selected production files are ledger.py, resource_registry.py, resource_lifecycle.py, managed_lifecycle.py and native_sync.py beneath src/modkit_events/persistence/. Corresponding tests are tests/test_resource_lifecycle.py and tests/test_managed_lifecycle.py. All seven match the accepted after-pins.json and current protected-live bytes; exact paths and hashes are saved in /home/faris/modkit-local-20261106/events-pure-transport-20261108/next-controller-provenance.json. Independent source acceptance is native/independent-review.md plus format-correction/independent-impact-review.md. Historical native-qa/qa.md proves only its bounded normal/aborted recipe, not the proposed statement adapter.

Integrate that reviewed controller dependency closure, then add typed request/result backing and explicit statement-start/complete/held transitions to its existing records. Current preparation/result setters accept bytes only. Current admit creates OP with running=False; release_ticket guards live results but has no running-operation guard because no statement executor currently uses that state. The real executor must mark running before the public driver call, prevent release while running, retain failure backing, and publish a complete typed result only after whole validation and actual call completion. Serializing a request to bytes while executing unrelated live parameters is not integration.

E14/E28 is a meaningful first actual route: E14 exercises caller-root association and scalar execution; E28 exercises bytea binding, complete binary rows, optional absence, full immutable event/replay coupling, and paid materialization through the same controller. It does not by itself unblock W05. After this route is qualified, Workers plans can reuse the controller while adding owned descriptor registration, FLOAT8/array inputs, bounded scan headers, complete joined records, and their typed decoders. Add those as real supported operations, not a generic 39-key compiler or new Workers controller.

The existing pinned native interpreter is /home/faris/modkit-native-v2-venv/bin/python. Its previously recorded libpq is 180006; revalidate identity before any separately authorized driver qualification. The first profile needs actual cancel-safe behavior; fallback cancel on libpq older than 17 needs its own proof only if that profile is later supported. Existing lifecycle tests use MODKIT_NATIVE_TEST_PYTHON for optional synthetic driver controls; absence yields explicit skips. No interpreter or driver was imported or installed during this source assessment.
