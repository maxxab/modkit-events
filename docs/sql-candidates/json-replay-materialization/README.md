# Bounded JSON replay materialization

Status: source-reviewed fix with the original bounded W01/W02 native regression independently accepted. Full shared-helper, W05 and release qualification remain incomplete (NOT_READY).

## Cause and change

The shared job replay entry point, _json_to_j(bytea), previously passed stored bytea directly into repeated get_byte calls. PostgreSQL may fetch or decompress that datum on each call. A controlled PostgreSQL 18.1 diagnostic used identical bytes and an independent canonical frame: flat input took 610.749 ms, stored pglz input 14995.959 ms, and the same stored bytes through a full substring 557.943 ms. All outputs matched. These one-shot results establish a material representation cost for that input, not a complete timing attribution for the earlier W01 timeout.

The change is confined to _json_to_j. It rejects NULL, measures logical octet_length, rejects input above 1048576 bytes, then retains one full bytea substring before scanning. Every existing UTF-8, BOM, whitespace, recursive parse, canonical-byte and trailing-input check uses that retained value.

The raw stored bytes, signature, immutability, security/search path, ACLs, canonical format and limits are unchanged. Empty input still rejects. W01 and E15 continue to validate proposed and stored replay independently. No json/jsonb conversion, parser rewrite, timeout increase, payload reduction or storage-setting change is involved. The separate _event_replay_frame entry point is not changed or performance-qualified.

The additional retained input is bounded by the existing 1 MiB cap. Decompression and PL/pgSQL assignment may also use transient copies. This is not an exact allocation-count, peak-memory or RSS guarantee.

## Source verification

The new source guards first failed against the unchanged SQL because the outer materialization was absent. After the change, the focused source, existing Python semantic-contract and artifact-policy selection passed 110 tests and 272 subtests. These source guards enforce placement and retention; they do not execute PostgreSQL.

The full suite stopped during collection because the existing optional Pydantic dependency is absent. The established available-source selection, excluding only tests/test_contracts_pydantic.py, passed 764 tests and 293 subtests, with 97 optional skips. The five existing Workers W05 source-contract tests passed. Ruff and git diff --check passed. No dependency was installed.

Existing independent semantic requirements cover escaped NUL, strict UTF-8 and surrogate handling, decoded duplicate keys, byte-key ordering, integer versus float, signed zero, malformed/trailing input and size/depth/node/collection limits. Complete SQL checks against those expected outcomes on flat and stored bytes, including chunk edges 4095/4096/4097 and late malformed input, remain incomplete. Source and Python oracle checks do not certify that runtime corpus.

## Bounded native regression result

The original failed joint W01/W02 attempt remains a historical failure. At the exact changed SQL snapshot, a fresh independently reviewed invocation of the unchanged native test passed its normal, key-conflict and ID-conflict phases. The test retained the 256 KiB payload string, 20-second statement timeout and one-CPU limit, using PostgreSQL 18.1, psycopg 3.3.8 and libpq 180006.

The normal phase passed initial submission, protected full and missing reads, identical duplicate submission, caller rollback and commit, independent visibility checks, tested result lifetimes and capacity assertions. Both conflict phases passed their exception, held/uncertain-state and committed-baseline assertions. Closing a held conflict connection is not a managed cleanup/refund receipt. All three phases passed bounded client diagnostic checks; this does not include server-log privacy.

The elapsed times were 7.923 seconds for the complete normal subprocess and about 2.026 seconds for each complete conflict subprocess. They are not individual query timings or performance guarantees. This acceptance closes the observed original timeout regression for this invocation and profile, without establishing all drivers, platforms, payloads, concurrency or memory behavior.

The combined continuation stopped later at a fixture observation-permission error. Full W05 rollback/negative proof, the shared-helper semantic corpus, server-log privacy and final fixture aftermath remain incomplete. The completed native phases remain valid; the later observation error is not evidence of another product defect. Migration/grants, installed artifacts, broader controller coverage and release readiness remain unqualified.

## Dependency provenance

Before this change, the complete SQL was 365263 bytes with SHA256 482a0776b9917bb581431b40f35caad4e957a8d6789b7c4c5eba896f892a4719. The current candidate is 365533 bytes with SHA256 0b51b172c86cc0a9a70ca290df0e612d93ea2a2165edbaa4224b4d0347b40ef9. The function maps show only _json_to_j changed and every SQL byte outside that body unchanged.

This edit changes the older W05-qualified prefix. Preserve historical W05 evidence against Events 60eac7ac7311c7e45bbccbcea2a22a1de8f7ad7e and its 321406-byte SQL prefix, SHA256 0800ed51a5588e9f2d44aa4edb87a4ce262a775b330bd229d8576f0e48292228. It cannot silently certify this new helper snapshot.

W05 calls E04, which validates through E15, _intent_valid and _json_to_j. Current dependency acceptance needs an explicit decision and independent review of the changed helper plus unchanged ABI/locking/capture bodies. New-snapshot runtime checks must cover valid acquisition and corrupt selected replay rejection, including later-row failure rolling back earlier claims/history. Those complete acceptance criteria remain open; the bounded W01/W02 result does not close them. E10 remains separately gated.

## Evidence

Retained review artifacts include the source diagnosis, independent causal-diagnostic review, RED/GREEN logs, complete function maps and exact candidate hashes. The accepted bounded native result is recorded in review-native-result-v1.md, SHA256 c85a9c20e4c0a262cb411c0f1d035c449de4977337481df4252099710bfbf3f4. Historical failed-attempt evidence is preserved separately.

PostgreSQL reference implementations: [bytea access and substring](https://github.com/postgres/postgres/blob/REL_18_1/src/backend/utils/adt/varlena.c), [detoasting and slice allocation](https://github.com/postgres/postgres/blob/REL_18_1/src/backend/access/common/detoast.c).
