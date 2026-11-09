# Dependent records and history fixture specification

Authored before dependent tables. NOT_RUN.

- Inbox event uniqueness partition is subscription plus SHA256(raw event ID); retain full ID/envelope/replay and compare after conflict waits. Wrong subscription/work kind or missing join half must yield PZ012 at public observation, not a partial object.
- Attempts unique(work,cycle,attempt), unique dispatch ID, work FK immediate. Each dispatch preserves original effect/request/provider/root/time; only outcome/evidence change through authorized transition. Work active pointer must reference the same work/cycle/attempt, checked in routines and observations.
- Work/delivery/publication history append-only to runtime, positive identity IDs used for bounded keyset queries. Updates/deletes unavailable to public roles.
- Outbox ID digest arbitration retains full event envelope/replay; pending/claimed no intent; publishing/held/terminal have retained intent. Active states alone have token/lease. Receipt/evidence shape enforced by settlement routines, not a fabricated durable receipt.
- Identity sequences and tables grant no runtime rights. Actual final ACL audit must detect named-role defaults as well as PUBLIC. No cleanup, TTL or history deletion operation exists.
