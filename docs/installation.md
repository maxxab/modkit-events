# Explicit PostgreSQL installation closure candidate

## Qualification state

This candidate supplies immutable migration resources and an inert owner-receipt
reader. Source/pure checks are not PostgreSQL installation, ACL, native parameter
transport, wheel/sdist, installed-origin or release qualification. Native
qualification remains blocked. A manifest or E33 row is not proof of readiness.
No startup/import runs SQL, opens connections, creates roles, grants access,
commits, rolls back or retries.

Metadata is a separate release gate: both packages are version0.1.0 but Workers
requires modkit-events>=0.2,<0.3 and expected Events native extras are undeclared.
Ignoring dependencies or importing a checkout does not qualify an installed pair.

## Trusted identities and rights

The application supplies existing PostgreSQL16+ NOLOGIN owner, modkit_runtime,
modkit_reconciler and modkit_operator roles without superuser, BYPASSRLS,
CREATEROLE, CREATEDB or replication capability. The distinct owner has database
CREATE and owns both components. Owner/operator have no other ancestor roles;
runtime/reconciler may inherit only operator. Installation creates no memberships.

Select the intended authorized role before native resource adoption. Four-role
checks do not constrain every descendant LOGIN/session path. Applications avoid
more privileged sessions and establish business/tenant authority. These are trusted
application-service roles, not end-user or row-level tenant isolation. READ wrappers
can expose sensitive whole-application data.

All three roles get direct schema USAGE and E09,E15-E21,E28-E30,E33,E34.
Runtime additionally gets E01-E08 (eight-argument E04),E10/E11,E14,E22-E25,E32.
Reconciler additionally gets E12/E13/E14/E26/E27/E31. Operator has no mutation/E14.
E12 is administrative cancellation; ordinary failed-handler cancellation uses E11.
E14 stays the sole public SECURITY INVOKER function, allocating caller xid.
Nine-argument E04 and private helpers remain owner-only; same-owner Workers W05
SECURITY DEFINER calls bounded E04 internally.

No direct restricted table/column/sequence access, schema CREATE or grant options.
Private composite _parse_result and its array remain private. Ordinary table row
types retain built-in PUBLIC USAGE; arrays follow element privileges. Type usage
does not grant table access. No type/default-privilege repair occurs.

## Authenticate before execution

A separately trusted release record binds exact initial/grants bytes, MKMF
aggregate, descriptor bytes, owner_receipt.sql, reader code and distribution
artifacts. Self-consistent local hashes are not authenticity or state attestation.
manifest() verifies the two resources; read_sql(migration, resource) returns
verified UTF-8 SQL.

MKMF v1 remains MKMF plus byte1, big-endian uint32 count2, then UTF-8-sorted paths
with uint32 lengths and32 raw SHA256 bytes. Receipt/descriptor pins are separate.
Workers binds its sole Events/version1 dependency to the actual verified aggregate.

read_owner_receipt(events_migration, /) always takes the verified Events Migration,
including when obtaining the generic Workers receipt template. One anchored lease
verifies Events manifest/resources and membership, then fixed owner_receipt.sql
under an unconditional4096-byte bound and independently reviewed literal digest.
Workers separately verifies its descriptor/dependency before binding its own tuple.
The reader verifies template identity only, never database state.

Only supported finite POSIX/Z1 origins are accepted. Missing, altered, oversized,
unsupported-origin and uncertain-cleanup reads fail closed. No arbitrary filename/
hash or loader fallback. Windows resource transport remains unsupported.

## Caller-owned sequence

After exact resources are independently qualified and deployment authorized,
the primary path is one explicit owner transaction:

1. Authenticate closure/target. Execute the entire Events initial SQL.
2. Execute complete Events grants preflight, exact grants and postflight. They
   check roles/ancestry, explicit owner defaults, function ABI/body identity,
   direct/effective ACLs, table/column/sequence/type boundaries.
3. Execute the separately pinned generic receipt INSERT with six bound fields
   from Events Migration: component,version,32-byte decoded migration_digest,
   catalog_contract_id,scope_format_id,intent_format_id. The SQL supplies applied_at
   with pg_catalog.clock_timestamp().
4. Verify compatible Events closure/receipt and Workers dependency. Execute entire
   accepted Workers initial, then Workers grants/postflight.
5. Retrieve shared template using Events descriptor and bind separately validated
   Workers six-field identity to its owner receipt.
6. Caller explicitly commits. Only acknowledged COMMIT establishes durability.

Never interleave grants within initial files. Workers requires the reviewed
Events-schema preflight correction; old structural source rejects Events grants.
An earlier separately committed Events-only root is permitted only with acknowledged
compatible closure/receipt and verified Workers dependency preconditions.

Native $1-$6 placeholders require a qualified parameter transport, never value
interpolation or general SQL rewriting. Actual transport qualification is pending;
the Python reader does not translate driver placeholders.

Receipt insertion is owner-only. applied_at has no default and is omitted by E33;
owner inspection validates the exact tuple and database timestamp. An inserted
uncommitted row is staged, not success. Duplicate insert, grant failure or rollback
must not be relabeled success. Uncertain commit/close stays UNKNOWN pending separate
authorized owner reconciliation. No automatic retry/upsert, role change or hidden
transaction finalization.

## Remaining evidence

Independent source review and separate pure QA; wheel/sdist/rebuilt-wheel and
outside-checkout origin/metadata qualification; separately authorized native
installation/ACL/transport tests remain gates. Native tests must execute lawful
restricted-role chains, forbidden signature pairs, effective/SET/default/column
leakage, type topology, private W05 composition, six-bind receipt timestamp and
staged/committed/unknown transaction cases. Owner-only or old scoped functional
SQL evidence does not qualify the complete installation.
