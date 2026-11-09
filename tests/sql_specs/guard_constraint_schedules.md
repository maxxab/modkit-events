# Guard constraint schedules before trigger source

NOT_RUN. These require real PostgreSQL transactions and are not emulatable by source checks.

1. Insert unsatisfied outer guard, perform associated write, enter savepoint, fail completion, swallow error and release savepoint: COMMIT rejects PZ001 and rolls back associated write.
2. Insert guard and all associated writes inside savepoint then rollback savepoint: outer commit may succeed, neither guard nor writes survive.
3. Satisfy guard once under correct final fence: delayed INSERT event must SELECT current persisted row, not reject stale NEW.satisfied=false. Commit after lease deadline allowed if final fence valid.
4. SET CONSTRAINTS ALL IMMEDIATE while unsatisfied rejects; already satisfied certificate accepted. Caller must rollback failed transaction state.
5. Change/delete satisfied certificate or mutate immutable guard root/fence/identity rejects PZ008. Unrelated owner DDL remains outside runtime threat model.
6. Guard immediate work FK takes KEY SHARE. Another backend's cancellation/renewal takes NO KEY UPDATE and must not be blocked by the guard's FK lock. Completion locks subscription→work→guard, samples clock after waits.
7. Guard timestamp/result root consistency must be verified by completion function and observation decoders. The structural trigger cannot prove an arbitrary application write belongs to this guard or that complete was the caller's last write.
