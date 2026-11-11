# Bounded JSON replay materialization

Status: source-reviewed fix with independently accepted bounded W01/W02 native regression, 43-case helper corpus, targeted current-helper W05 SQL dependency and final observation checks. Full native and release qualification remain incomplete (NOT_READY). The isolated fixture was subsequently shut down and removed.

## Cause and change

The shared job replay entry point, _json_to_j(bytea), previously passed stored bytea directly into repeated get_byte calls. PostgreSQL may fetch or decompress that datum on each call. A controlled PostgreSQL 18.1 diagnostic used identical bytes and an independent canonical frame: flat input took 610.749 ms, stored pglz input 14995.959 ms, and the same stored bytes through a full substring 557.943 ms. All outputs matched. These one-shot results establish a material representation cost for that input, not a complete timing attribution for the earlier W01 timeout.

The change is confined to _json_to_j. It rejects NULL, measures logical octet_length, rejects input above 1048576 bytes, then retains one full bytea substring before scanning. Every existing UTF-8, BOM, whitespace, recursive parse, canonical-byte and trailing-input check uses that retained value.

The raw stored bytes, signature, immutability, security/search path, ACLs, canonical format and limits are unchanged. Empty input still rejects. W01 and E15 continue to validate proposed and stored replay independently. No json/jsonb conversion, parser rewrite, timeout increase, payload reduction or storage-setting change is involved. The separate _event_replay_frame entry point is not changed or performance-qualified.

The additional retained input is bounded by the existing 1 MiB cap. Decompression and PL/pgSQL assignment may also use transient copies. This is not an exact allocation-count, peak-memory or RSS guarantee.

## Source verification

The new source guards first failed against the unchanged SQL because the outer materialization was absent. After the change, the focused source, existing Python semantic-contract and artifact-policy selection passed 110 tests and 272 subtests. These source guards enforce placement and retention; they do not execute PostgreSQL.

The full suite stopped during collection because the existing optional Pydantic dependency is absent. The established available-source selection, excluding only tests/test_contracts_pydantic.py, passed 764 tests and 293 subtests, with 97 optional skips. The five existing Workers W05 source-contract tests passed. Ruff and git diff --check passed. No dependency was installed.

The independent SQL semantic results are recorded below. Source guards and Python oracle checks remain separate evidence and do not by themselves certify PostgreSQL behavior.

## Bounded native regression result

The original failed joint W01/W02 attempt remains a historical failure. At the exact changed SQL snapshot, a fresh independently reviewed invocation of the unchanged native test passed its normal, key-conflict and ID-conflict phases. The test retained the 256 KiB payload string, 20-second statement timeout and one-CPU limit, using PostgreSQL 18.1, psycopg 3.3.8 and libpq 180006.

The normal phase passed initial submission, protected full and missing reads, identical duplicate submission, caller rollback and commit, independent visibility checks, tested result lifetimes and capacity assertions. Both conflict phases passed their exception, held/uncertain-state and committed-baseline assertions. Closing a held conflict connection is not a managed cleanup/refund receipt. All three phases passed bounded client diagnostic checks. The separately completed server-log check is scoped below.

The elapsed times were 7.923 seconds for the complete normal subprocess and about 2.026 seconds for each complete conflict subprocess. They are not individual query timings or performance guarantees. This acceptance closes the observed original timeout regression for this invocation and profile, without establishing all drivers, platforms, payloads, concurrency or memory behavior.

That combined continuation stopped later at a fixture observation-permission error and remains a failed attempt. The original timeout and earlier incorrect 8192-digit integer-oracle attempt also remain historical failures. Their records were not relabeled; the completed native phases were preserved without replay. A separately reviewed continuation completed the bounded checks below.

## Bounded helper and final observation results

All 43 corrected helper cases matched independent expected canonical bytes or NULL outcomes through direct and stored-row routes. Coverage includes escaped NUL, UTF-8/escape/surrogate rules, decoded duplicate keys and ordering, integer/float distinctions and signed zero, finite float extrema/underflow, chunk edges 4095/4096/4097, late invalid input, grammar/trailing/empty/NULL failures, depth 32/33, collection sizes 65536/65537 and independent raw/canonical 1 MiB boundaries. Integer checks accept 4096 digits and reject 4097, 8192 and 8193 digits. A small node-budget guard passed; the outer 262144-node boundary was not reached because the canonical framing limit dominates valid outputs.

For identical 262155-byte input with an independent 262178-byte canonical expectation, flat input took 596.426 ms and stored input took 572.056 ms under the unchanged 20-second statement timeout and one-CPU limit. The stored datum was observed at 3021 physical bytes with pglz compression; compression was not established for every corpus row. These one-shot measurements support removal of the demonstrated representation amplification, not statistical speedup, throughput, allocation, RSS or SLA guarantees. Temporary-table rollback and absence checks passed.

The final observer found the expected committed baseline: one Work, payload, history and business row, with no prepared transactions or other database clients. This compact observation is not a full database checksum. The bounded 250-line server-log capture contained neither synthetic payload nor material sentinel; actual outputs stayed below the capture limits. It does not certify all possible logs. Final containment and all 119 input-pin checks passed. A separate disposition receipt confirms clean shutdown and non-force removal of the isolated fixture, with the exact container and owned socket absent and qualification evidence preserved.

Migration/grants, installed artifacts, other drivers/platforms, broader controller/concurrency/scaling coverage and release readiness remain unqualified.

## Dependency provenance

Before this change, the complete SQL was 365263 bytes with SHA256 482a0776b9917bb581431b40f35caad4e957a8d6789b7c4c5eba896f892a4719. The current candidate is 365533 bytes with SHA256 0b51b172c86cc0a9a70ca290df0e612d93ea2a2165edbaa4224b4d0347b40ef9. The function maps show only _json_to_j changed and every SQL byte outside that body unchanged.

This edit changes the older W05-qualified prefix. Preserve historical W05 evidence against Events 60eac7ac7311c7e45bbccbcea2a22a1de8f7ad7e and its 321406-byte SQL prefix, SHA256 0800ed51a5588e9f2d44aa4edb87a4ce262a775b330bd229d8576f0e48292228. It cannot silently certify this new helper snapshot.

W05 calls E04, which validates through E15, _intent_valid and _json_to_j. Independent common and consumer reviews now accept the targeted changed-helper dependency at this exact snapshot. Valid acquisition matched all 75 named SQL values and the exact claim/history delta. Both valid and later-corrupt-replay roots passed complete 13-table rollback comparisons. Sequence transitions 3 to 4 and then 4 to 5 prove actual claim allocations, including the earlier real claim before the later malformed row failed; sequence increments persist across rollback. The received PZ012 neutral-composition error passed exact checks before missing-subtype validation.

This closes only the targeted current-helper SQL dependency. The negative row was naked Work, not a complete malformed family or a post-E04 material fault. Named SQL values do not qualify binary column order, the W05 native decoder/profile, broad concurrency or fairness. Historical prefix evidence remains historical; unchanged ABI/locking/capture reasoning is carried forward only through the exact function map. E10 remains separately gated.

## Evidence

Retained review artifacts include the source diagnosis, independent causal-diagnostic review, RED/GREEN logs, complete function maps and exact candidate hashes. The accepted bounded native result is recorded in review-native-result-v1.md, SHA256 c85a9c20e4c0a262cb411c0f1d035c449de4977337481df4252099710bfbf3f4. Consolidated bounded acceptance is recorded in review-consolidated-results-v1.md, SHA256 3eba9215a5fb5c0b3da44e45e1f7f13d6e415890a6946f2d27ac5b5b9eedfb6f. Consumer acceptance is recorded in w05-current-dependency-result-acceptance-v1.md, SHA256 059a20486f8bf07599386e1f46b19da7b4fa95e5e82ee89a874cddf20127e06f. Historical failed-attempt evidence is preserved separately.

PostgreSQL reference implementations: [bytea access and substring](https://github.com/postgres/postgres/blob/REL_18_1/src/backend/utils/adt/varlena.c), [detoasting and slice allocation](https://github.com/postgres/postgres/blob/REL_18_1/src/backend/access/common/detoast.c).
