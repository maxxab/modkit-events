# E13 Work Recovery Implementation Plan

> For agentic workers: use superpowers:executing-plans with the retained dedicated owner. Source is implemented and its first isolated SQL qualification passed; independent review accepted the bounded runtime result and graceful disposal. No execution grant is contained here.

**Goal:** Implement the existing E13 bounded recovery scan without replaying dispatched effects.
**Architecture:** One append-only PL/pgSQL operation using E04 raw discovery, parent/Work/current-attempt SKIP LOCKED ordering, E15 coherent preimage integrity, E12-style full mutation receipts and buffered validated postimages. No Python ABI/helper/controller change.
**Tech Stack:** Existing PostgreSQL PL/pgSQL and Python>=3.12/pytest.
**Spec:** Existing catalog E13, transitions.py recover rules, rows.py scan contract; private implementation plan at /home/faris/modkit-local-20261106/events-work-recovery-20261108/assessment-plan.md. Independent narrow design PASS: review/design-challenge.md, SHA2562877ea1e962c717dd4abaa664e636fc5077bc362e2e345f3d44235626bdedab1. Source-release-v1.json supplies current scope. Authoritative product plan: /home/faris/modkit-handoff-20261106/handoff/2026-11-06/jobs/modkit/MODKIT-IMPLEMENTATION-PLAN.md.

## Global constraints

Preserve original378764-byte SQL prefix SHA256ef9c3eafac5713a2ad07c62dbde476c1d0d751897a03d0e685788a8766fc2731. E13 ABI is (bytea,text,int4,uuid nullable,int4), returning existing60-column Work scan. Caller owns READ COMMITTED transaction. No E10/guard repair, hidden transaction boundary, retry, provider I/O, package reverse dependency or existing function edit. Scope is appended SQL, tests/test_work_recovery_sql.py, this plan and docs/sql-candidates/e13-work-recovery/README.md. Parent owns staging/commits; W04 paths remain untouched. Public push is held.

## Review focus

Nonblocking attempt contention versus genuine absence; integrity before time/MAX eligibility; raw pagination including terminal zero-capacity rows; deadline/budget precedence and claimed-exhaustion integrity; exact mutation postimages and all-or-nothing page output. Source guards do not execute SQL or prove these runtime cases.

## Task1: Implement existing E13 contract

- [x] Verify HEAD3584597b5c528f868bc675adab333381efe1dbf0 and immutable prefix; reuse E04/E12 patterns after independent design challenge. No separate accepted E13 design existed previously.
- [x] Write focused guards first:11 failures, all E13-missing assertions. RED retained in task directory red.txt.
- [x] Append e13 and PUBLIC revoke only. Discover raw namespace/kind UUIDs in order, advance visited/cursor before skips, and distinguish actual no-next-row exhaustion from either bound. Acquire parent then Work then current attempt without waiting on those row locks; distinguish absent required rows from locked rows.
- [x] Read one fresh E15/Work/parent/current-attempt snapshot after all entity locks. Revalidate identity, full rows and cardinality. Nonterminal parent count must be positive; terminal/ineligible rows with zero count are not corruption. Existing E15 rejects claimed budget exhaustion and corrupt MAX candidates before recovery can skip them.
- [x] Sample one database clock per candidate. Deadline wins over budget; expiry/failure release inbox capacity once. Expired claimed leases return queued only with live deadline and budget. Running lease/deadline loss becomes held with uncertain/empty attempt evidence while retaining dispatch provenance, regardless of replay policy. Every mutation releases ownership, increments revision once and preserves attempt count, availability and cancellation state. MAX skips after integrity; MAX-1 may become MAX.
- [x] Compare complete Work/attempt/parent update receipts and full inserted history. History reason equals transition except attempts_exhausted. Buffer exact postimages; no STABLE E15 post-write reread or partial output before final scan validation.
- [x] Manual end-to-end trace before GREEN covered arguments, raw scan, candidate/lock skips, missing entities, coherent integrity, final time/MAX, all four decisions, mutations/history and retained result shape. No exception handler swallows corruption/native errors. Selected late-candidate failure aborts the statement; this is source reasoning, not runtime proof.
- [x] Focused command: PYTHONDONTWRITEBYTECODE=1 /home/faris/modkit-local-20261106/.venv/bin/python -m pytest -p no:cacheprovider tests/test_work_recovery_sql.py tests/test_persistence_contracts.py -q:82 passed. No full-suite or SQL execution claim.
- [x] Independent emitted-source review accepted the exact source; a separately released first isolated SQL qualification passed.
- [x] Independent review accepted the actual bounded runtime receipts and graceful disposal.
- [x] Final minimal documentation-delta review accepted in review/final-docs-v2-acceptance.md (SHA256685c988a2c34bf4b69d190077887223567978ef3f6a96b834f594d18ab380704).
- Parent-controlled scoped integration follows accepted verification; its actual commit outcome and final pins are recorded in Git history and retained integration evidence.

## Task2: Bounded SQL qualification and graceful disposal accepted

One reviewed v2-runner attempt on a fresh isolated PostgreSQL18.1 target passed in33.91seconds. The final PID1 postgres/postmaster readiness check passed before SQL. E13-QA-01 (the earlier pg_isready-only initialization race) was corrected before runtime; the preserved v1 runner never ran. Exact installed source remained400012bytes SHA2560410fdff4d6e4d02b2d25bdc1135623d817bda1f65b6f1d6d7c1fce16b4cddf0. Full migration installation does not prove execution of every deferred branch.

Lawful E01/E03 inbox seeds, E04 claims and E06 dispatches exercised empty cursor retention, live running raw-budget skip, queued/blocked deadline expiry with item/budget limits, terminal zero-parent-count visits, claimed lease recovery, running lease loss and combined deadline/lease loss, actual exhaustion, and no-mutation second pass. E12 first held cancellation retained uncertain attempt evidence and capacity; repeated held cancellation changed nothing. E15/E19 reads, invalid input and isolation precedence also passed. Complete footprints, postimages, history/capacity/revision deltas and timestamp bounds were checked. No synthetic positive history, guard or E10 call was used.

Explicit rollback left all12tables empty in same-session and separate-connection aftermath checks. Sequence state survived as expected: work history16/called, delivery history5/called, publication history1/not-called. The exact fixture was gracefully stopped with exit0 and removed without force. There is no retained runtime target or replay authority.

Evidence under /home/faris/modkit-local-20261106/events-work-recovery-20261108/: qa/runtime-result-pins-v1.json SHA256592ee57b5584dcb7d27b1bcaff62ef2269b0353450258ac0ef1a8dff72f72589; qa/runtime-v1/result.json SHA256fdf0596fb45a2d48e38f03bdedfdce8246fae641b3a4527600a3c61a6ed97bf3; qualification-v1.sql.log and aftermath-v1.sql.log retain actual markers and observations. The original result-pins status ACTUAL_RUN_PASS_PENDING_INDEPENDENT_ACCEPTANCE is superseded by review/runtime-v1-acceptance.md, SHA256121bff4637ea32a68d14d3caccfd603f2554304ec0c96360f0df0ecfcf8587ad: ACCEPTED bounded runtime PASS and graceful disposal, no findings. That acceptance does not cover excluded cases or grant further execution.

## Deferred cases and readiness

Lawful E11/E31 producers are needed for exhausted queued/retry and positive-count pointer-cleared histories; do not weaken E15 to manufacture claimed exhaustion. Jobs/W01, structural MAX/corruption, exact equality clocks and independent deadline-only causality, all concurrency/guard/E10 races, physical resource/fairness guarantees, committed provider effects, native/ORM and full compatibility/release/ERP gates remain separate. Current status:30 authored operations of34, not30 qualified operations. E11/E31/E32/E33 remain unauthored. Full package NOT_READY.
