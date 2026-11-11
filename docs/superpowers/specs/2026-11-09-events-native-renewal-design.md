# Fixed native E05 renewal

Status: bounded native E05 transport accepted with explicit limitations after independent source review and scoped native qualification. This is not a production worker/scheduler or a claim of full product readiness.

## Contract and transport

The existing E05 catalog/SQL contract is unchanged: six parameters are work_id UUID, token UUID, ownership_revision INT8 (1..2^63-1), cycle INT4 (1), expected_attempt INT4 (0..1000), and lease_seconds FLOAT8. ReturnContext contains exactly the matching Fence and no readiness object.

Only the paid E05 constructor normalizes exact int/float seconds. It checks the canonical finite domain (0,3600] before integer conversion; booleans, subclasses, strings, NaN/infinities, zero, negatives and overflow candidates fail locally. Retained requests require exact float, without coercion or graph replacement. Positive subnormal inputs remain valid. Binary FloatBinaryDumper preserves their represented bits; SQL performs exact microsecond ceiling. Int8BinaryDumper preserves all ownership-revision bits, including values above 2^53; explicit SQL casts keep cycle and attempt INT4.

The immutable fixed query materializes E05 once and returns cap_ok plus lease_until with LIMIT 2. The descriptor requires exactly one row, a true BOOL marker and a nonnullable eight-byte TIMESTAMPTZ. Existing issuer metadata, status, cardinality, next-result-set and binary checks remain intact. Timestamp decoding rejects infinity and dates outside Python UTC datetime's supported range. The returned value is an exact timezone.utc datetime scalar, matching existing public row semantics.

No timestamp contains an echoed Fence or durable receipt. Association is the fixed SQL, retained request/context, and ticket/result/ledger ownership. The result does not prove commit, rollback, or continued eligibility against later cancellation.

## Separate ownership and durability

Use an independently owned execution ledger, checkout and renewal root while the shared resource domain remains active. Keep the business root/checkouts/resources separate. Reserve execution, acquire/attach the clean connection, start root, prepare E05 under paid A/D, admit, reserve B, execute/read, release only legitimately completed statement resources, then explicitly commit and obtain COMMITTED acknowledgement. Afterward take a fresh durable observation through an eligible reader (native W02 for jobs). Do not report a staged timestamp as durable.

E08 holds work KEY SHARE, compatible with E05 NO KEY UPDATE. E05 can still block behind E10, cancellation or arbitrary business SQL. SQL samples authority time after lock acquisition and coherent reads; expired leases, deadlines and cancellation reject renewal without resurrection. No SQL was changed by this transport slice.

Unknown renewal commit is not permission to repeat: E05 has no immutable operation-ID receipt. Preserve liabilities and observe conservatively. A fresh ledger/connection/scope cannot clear process-wide fail-stop. Cancelling an await does not establish that synchronous I/O stopped; no clean-stop, close or refund claim is justified by cancellation alone.

## Paid graph accounting

CPython 3.12.3 pure measurements: maximum E05 A occurrence graph 952 bytes and exact UTC timestamp B graph 48 bytes. Caller recommendations: default A1024 and B64. The A measure includes request/parameter/context/expected-tuple/Fence carriers, all scalar occurrences and UUID integer storage, even when values alias. Static descriptor objects are startup-retained plans. The wire row has only nine cell-payload bytes; wire size is not retained-graph size.

Tests exercise exact A952/B48 and one-byte-short A951/B47. A failure occurs before I/O and releases only the unreturned preparation. B publication failure after execution retains HELD/UNKNOWN liabilities under existing fail-stop behavior, not a fabricated rollback/refund.

A pure two-open-root schedule measured C2/X2/R2/A2/AB1904/B2/BB96/D2, with one issuer executing while the other root remains admitted. D2 includes nested result publication. This is not a simultaneous two-issuer, actual E08 business, completion or fresh-reader capacity guarantee. Their retained graphs, concurrent D frames and additional checkouts require independent headroom. Retained uncertain liabilities cannot be budgeted as refunded.

## Verification and accepted native scope

The combined pure regression passed 881 tests with 29 optional-driver skips. Existing FL6/E32 invariants are preserved. The repository native integration module remains deliberately inert; the native evidence below comes from a separately reviewed and authorized fixture packet, not that skipped module.

Independent review accepted the bounded E32/E05 routes with explicit limitations: 22 planned scenarios have evidence across disjoint executions, 16 in the original partial run and six in a non-replay continuation on the same retained fixture. This was not one clean 22-case run. The continuation reused case17's existing immutable W01 admission, preserved prior16 work/history preimages, and completed graceful fixture removal with verified absence.

Accepted E05 evidence includes:
- Useful renewal while the actual E08 business guard stayed open: the database clock passed the original lease, stayed within the renewed lease, then E10 and fresh W02 succeeded.
- Observed E10-first/renewal-first and cancellation-first/cancellation-after ordering; lease and deadline boundaries crossed while E05 was actually blocked, followed by PZ003/PZ009 rejection with no renewal history or resurrection.
- A staged tiny-subnormal renewal rolled back, leaving the original durable lease and history unchanged. Fresh W02 corroborated the durable state.
- Actual COMMIT and observed IDLE followed by a targeted postcondition distortion left the renewal root logically UNKNOWN/blocked and uncertainty retained; fresh observation saw the committed lease. This is a known physical commit with logical uncertainty, not network-loss ambiguity.
- A stale-Fence native SQL rejection stopped the domain and prevented a precreated control root from issuing SQL. This is post-start SQL rejection, not network loss. A separate 47-byte result reservation failed against the 48-byte timestamp after SQL and retained HELD/UNKNOWN liabilities; neither case establishes a refund.
- In the explicit caller harness, cancellation left the blocked native thread live and resource release was rejected. Only after blocker rollback, thread join and observed backend quiescence did release/close complete; fresh W02 agreed with the result. This qualifies that harness sequence, not a production WorkSource or asynchronous supervisor guarantee.

The actual fixture image used CPython 3.13.5. Its paid constructor/accounting preflight independently measured E05 A952/B48, matching host CPython 3.12.3 measurements; preflight sizing alone is not database proof.

Combined native logical obligations included an open E08 guard and observer root, a retained renewal result and admitted E32 settlement: C/X/R4, A/B2, reserved AB4195328 and BB4194368, with D0 at the recorded point and one separately identified raw oracle connection. These are concurrently live logical obligations, not simultaneously executing SQL, RSS, an exact transient D peak or arbitrary workload capacity. E32 retained separate 4MiB preparation and 4MiB result reservations. Completion and fresh W02 HELD observation preceded disposal.

The original attempt failed during case17 setup before E06/E05: discovery_budget16 exhausted earlier raw identities; the empty-frame explanation was source-derived, not a logged full frame. A first continuation attempt then timed out in read-only preflight before staging; its cause remains UNKNOWN. The later successful continuation does not retroactively convert either failed attempt into a clean pass.

Acceptance references:
- First16 review: partial-native-review-v1.md, SHA256 28ea54b40bc8c675e19f733abb57610197575d1fbed27d31ec178c89c286df72.
- Final scoped acceptance: final-native-acceptance-v1.md, SHA256 bade99e863695a3294a6fc1ea3da9c4b8de9f84fdab860aa3b97a25671511cae.
- Remaining-six result: continuation-native-result-v3.json, SHA256 c2b6df3a6379567a1b7a06f3ab1612c99751577affa3ec93060ded5fe813569c; evidence manifest SHA256 2c2a4aa866cd9e865a0b48bd342fee6651973434bcacd5c81aa0c67615e0b50d.

No native E15/read-source capability, E12 inbox qualification, cross-process incident handoff, new strict E11 rollback proof, production supervisor, scheduler, WorkSource, retry authority, database migration or ledger/domain reset is added. The timestamp alone still does not identify its Fence or prove commit. Full product readiness is not established.
