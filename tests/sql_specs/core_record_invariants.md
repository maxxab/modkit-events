# Core record fixture specifications, before table source

NOT_RUN. Future PostgreSQL fixture must prove with owner fixture writes then runtime entry points:
- schema receipts require version1, exact32-byte digest and exact profile IDs. No runtime receipt/table rights.
- Subscription positive int4 capacity, nonterminal count0..capacity. Full manifest retains bytes.
- Work job subscriptionNULL / inbox subscriptionnonnull. Fixed scope/frame typed consistency, readonly original schedule, immutable admission preserved by functions and owner-only table access.
- Claimed/running requires token+lease; all other states clear both. Queued/retry/claimed current dispatchNULL even historical attempts exist; running/held require unresolved pointer. Terminal predispatch may have no pointer. Attempt count0..max, cycle>=1, ownership revision>=0.
- Only succeeded has witness: guarded exact guard/fence/digest and no terminal resolution; reconciled exact terminal resolution and no guard/fence/digest. Non-success has no success witness. Both current resolution pointers are absent before terminality, including after safe_retry; that operation remains immutable registry/return evidence. Guarded success has neither resolution pointer. Reconciled success has equal nonnull success and terminal resolution IDs. Failed/cancelled may carry only terminal resolution; expired carries neither. These checks do not prove registry/certificate linkage.
- Nullable key has no key-uniqueness constraint. Present key is partitioned by kind, subscription, namespace,command,scope digest,key digest. Same hash bucket must still compare all full bytes in admission function; a digest collision is conflict, never duplicate success.
- Raw identities include NUL but invalidUTF8/blank/oversized identities reject. Evidence blobs stay bounded1MiB. Unsupported positive schema versions remain decimal bytes.
- Foreign keys are immediate. Guard KEY SHARE does not conflict with state-only NO KEY UPDATE. Full concurrency fixtures remain mandatory and blocked.
