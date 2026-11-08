# E29 publication-history reader

The package migration now authors the catalog-defined E29 reader. Independent source review passed. Bounded PostgreSQL18.1 execution and independent saved-result review passed. The complete package remains NOT_READY.

E29 uses READ COMMITTED, validates the nonblank UTF-8 event ID (at most256 bytes), nonnegative int8 cursor and limit1..256, then reads one indexed ascending page. Digest discovery does not discard full-ID aliases. Selected record corruption raises PZ012; a coherent different-full-ID digest hit raises PZ002 after every selected row passes integrity. Missing or end pages are empty. No current outbox observation, publication certificate or commit certainty is inferred.

The inert test_runtime.sql requires an outer rollback transaction on a fresh disposable database. It directly seeds structurally valid outbox rows; their minimal opaque envelopes are not claimed to pass E28 or public enqueue. It exercises all publication status shapes, both renewal intent forms, zero UUIDs, receipt boundary, UTF-8 byte boundary including permitted U+0000, maximum/continuation/missing/high/absent pages and full projection. It checks12 invalid argument cases, unchanged parent/history/sequence state,19 selected semantic corruption cases and a malformed stored digest. Each poison row is rolled back; only disposable transaction-local constraints are relaxed.

No realistic coherent SHA-256 collision fixture exists. That PZ002 branch and complete-page integrity precedence remain source-reviewed, not runtime-executed, without altering the production hash path. Concurrent snapshot races, actual index execution plans/physical IO, lifecycle/admission, native drivers and full migration/release gates remain unqualified. Runtime ACL/isolation checks belong to the separately reviewed wrapper.

No E10, old runtime target, native/shared-service work, dependency installation, production grants/manifest/version change, push or publication is included.


## Verification evidence
The new source test first produced16 missing-function failures and one existing-index pass, then17 passed. Focused source/decoder/artifact/standalone checks passed128 tests and248 subtests. Available base checks passed227 tests and269 subtests with30 optional skips; the known unavailable optional Pydantic module was excluded. Focused lint/format checks passed.

Two disposable attempts failed because of fixture assumptions, without changing product SQL: sequences lack a composite row type, requiring explicit sequence fields for JSON snapshots; valid U+0000 is a permitted nonblank bytea identifier, not invalid UTF-8. Both failures rolled back completely, and each exact target was cleanly shut down and removed before the next attempt. The corrected fixture passed on a fresh third target.

The successful run checked the exact migration/fixture,12 invalid inputs,19 selected semantic-corruption cases, malformed digest precedence, unchanged storage, all listed paging/projection cases, default execute privilege absence, explicit operator execution, private history access denial and REPEATABLE READ PZ005 precedence. Both transactions rolled back and aftermath reported zero fixture schemas, roles, prepared transactions and other client backends.

This is not proof of concurrent snapshot behavior, production role deployment, a coherent SHA-256 collision, actual physical IO bounds, all possible corruptions, public lifecycle correctness, native transport or complete migration/package readiness.

Independent evidence review accepted the bounded result. All three exact disposable targets are removed. Each stop waiter returned137 as its container exited; fresh inspection showed clean exit0, no OOM and a completed database shutdown before removal, without retrying stop. No shared service was changed.
