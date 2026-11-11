# Pending executable fixture: immutable intent projections

Authored before private intent verifier. NOT_RUN. Required fixture must construct MKSC-1 scope and MKPF-1 work-intent independently of SQL helper under test, then pass every typed projection separately.

1. Exact 14-slot job intent, nullable tenant/owner/key/deadline, mapping semantic and matching replay: true. Reordered replay object keys and whitespace retain equality; original replay is stored separately.
2. Change each of kind, subscription, namespace, command, schema decimal, scope application/tenant/owner, key, semantic bytes, protected bytes, replay policy, max attempts, deadline or original schedule without updating frame: false. Do not use SHA equality as verifier.
3. Job with nonnull subscription; inbox with null subscription; unknown kind/replay policy; max attempts0/1001; canonical version0/2: false. Initial deadline ordering is not an admission validity restriction.
4. Scope version fixed1, frame projections with NUL preserve raw bytes; malformed UTF8/blank/overlong identities reject.
5. Inbox semantic must equal complete event replay canonical frame with same command and version. Job semantic must be canonical mapping and equal decoded replay mapping, preserving int/float/signed-zero distinctions.
6. Unsupported but well-formed schema2147483648 and 4096decimal digits preserve complete intent; no int4 cast here. Runnable version handled separately.
7. Oversize or missing semantic/replay/binding/intent inputs reject before parsing. Infinity/BC/10000 timestamps reject.

This matrix is not an executed test and is not a replacement for future independent SQL known-answer tests. It isolates private equality validation, not admission arbitration or material readiness.

FL10-ADMISSION-TIME-1 explicit vectors (SQL NOT_RUN): identical typed job/inbox admission with original schedule2030-01-02 and deadline2030-01-01,2030-01-02,2030-01-03 must all validate when exact intent matches. Same cases with both timestamps in the database past still validate; initial admission retains immutable values and normal queued/blocked/capacity behavior. Claim/dispatch must not run at deadline equality or later. Recovery of any undisbursed queued/blocked/claimed/retry record with deadline<=sampled DB-now moves expired and releases capacity once. This is not an early-terminal intake shortcut and does not authorize any local clock comparison.
