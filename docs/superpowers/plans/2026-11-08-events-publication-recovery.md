# E26 Publication Recovery Implementation Plan

**Goal:** Recover expired publication ownership without replaying uncertain external effects.
**Architecture:** Reuse E22's bounded raw digest scan and nonblocking row lock. Reuse E28 for complete preimage validation, retain exact UPDATE RETURNING rows, and append existing transition history.
**Tech Stack:** PostgreSQL PL/pgSQL and Python source-contract tests.
**Spec:** Existing E26 catalog, bindings, scan decoder and publication transition contracts, within the original persistence/recovery milestones.

## Constraints and trace
E26 accepts limit1..256, nullable32-byte cursor and discovery budget1..4096>=limit, with the existing17-column scan result. Require READ COMMITTED and fixed security-definer search path with PUBLIC execute revoked. Validate the full locked row before expiry/revision eligibility. The unchanged existing migration prefix and all other operations remain intact.

Only expired claimed/no-intent rows return to pending; expired publishing/intent rows go to held. Clear token/lease and increment revision once. Preserve immutable identity/replay, intent and all prior receipt/outcome bytes, and set updated_at from final database time. Exact recovery history uses the retained intent, null operation/receipt and empty evidence/binding. No postwrite STABLE reread.

## Approach decision
A bulk eligible-only query would lose the raw visited-identity and cursor contract. Duplicating E28 validation would introduce avoidable drift. The existing per-identity scan is the conventional fit. For an exhausted max-int8 revision, skip after integrity and expiry validation rather than fail the whole scan or wrap/reuse ownership; max-minus-one remains usable. This is a bounded scan choice, not a guarantee of remediation. Pass exhaustion does not promise that all expired rows recovered.

## Review focus
- Future/maximum-revision rows with corrupt replay must fail PZ012 before eligibility skips.
- Maximum-minus-one and maximum must be covered for both claimed and publishing.
- Intentful recovery must preserve every opaque field and never become pending.
- Locked/ineligible raw identities must consume budget and advance cursor.
- Header/item frames, exact histories and no-write rejection must match existing decoders.

## Steps
- [x] Trace catalog, binding, transitions, readers, writers and trigger reachability before tests.
- [x] Write source tests and observe missing-E26 failure.
- [x] Append the minimal E26 body and pass source guards.
- [x] Independently review exact source, fixture and isolated execution inputs, including no-E10 reachability.
- [x] Run the reviewed bounded PostgreSQL fixture and one two-session contention schedule; retain actual outcomes and verify cleanup.
- [x] Update the explicit test inventory and run affected checks.
- [ ] Complete final independent source and committed-byte review.
- [ ] Commit the feature locally, regenerate changelog in a separate commit and verify exact committed bytes.

Full package and migration remain NOT_READY. Wider persistence operations, native transport, application integration, artifact and release gates remain separate.

## Verified scope
The original fixture failed during helper compilation before behavior ran; both CASE expressions in IF comparisons were parenthesized and the corrected fixture passed. No production SQL correction was needed. The bounded runtime and overlapping lock-skip schedule passed; source guards passed14, affected checks151, and the available base678 tests plus279 subtests. There were59 optional skips and an unavailable optional Pydantic module was excluded. These results do not complete the wider migration or release gates.
