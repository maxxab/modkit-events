# Future real installation fixture cases (authored before preflight source)

NOT_RUN. No role creation, SET ROLE, SQL or fixture operation authorized now.

Apply exact complete component under existing trusted NOLOGIN owner in caller-owned transaction. Valid PG16 profile passes preflight; no receipt until actual-object ACL inventory equality succeeds. Versions below16, selected LOGIN/elevated owner, missing/LOGIN/elevated group, owner/name collision, unrelated group ancestry, forbidden operator/runtime/reconciler inheritance or pre-existing target schema must abort before CREATE SCHEMA. Verify independent observer sees no installed component after caller rollback. No automatic role/default/ACL repair.

Function ACL after initial+grants: exact expected signatures only; owner plus per-key intended grantees; no PUBLIC/nonowner grant option/unexpected named default grants; every private helper owner-only. NULL proacl must use built-in acldefault('f',owner), not pg_default_acl. Deliberately inherited unsafe global/per-schema named grants abort before receipt, without altering defaults or unrelated objects. Missing helper revocation, wrong overload and missing intended grant each fail. These require actual authorized isolated PostgreSQL role setup and three-driver/owner fixtures later, not source greps or accepted metadata tests.
