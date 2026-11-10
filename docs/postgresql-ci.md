# Synthetic PostgreSQL installation CI

## Scope and design

The package workflow adds a fresh PostgreSQL 17.11 service for Events only.
This conventional disposable Actions service avoids installing a server, changing
network settings or using a database on the user's cloud or desktop computer.
The official image is pinned by digest. The job has a ten-minute limit, exposes
PostgreSQL only on the runner's loopback interface, mounts no persistent volume,
uses no existing credentials or repository secrets and uploads no artifacts.
Checkout credentials are not persisted. Actions owns service teardown, including
a failed or cancelled job. No custom kill, force-delete or retry fallback exists.

The fixed public password is a synthetic fixture value, not a confidential
credential. The checker accepts only the exact hosted Actions repository/context,
a fixed loopback target and an otherwise empty test database/server role set.
It rejects inherited PostgreSQL environment variables and arbitrary arguments.
These checks prevent accidental target selection; they are not a replacement for
workflow authorization or a sandbox against malicious code.

A bootstrap connection creates only four NOLOGIN product roles and four separate
non-superuser, non-inheriting fixture logins. Each login can select its one role,
without membership-administration rights. The owner role alone gets database
CREATE. The privileged bootstrap connection closes before installation checks.
All objects and memberships exist only inside that job's disposable service.
No deployment account, native authorization packet, prior grant or shared runtime
slot is read, reused or changed. Existing uncertain historical outcomes remain
unchanged.

## Checks

1. Build and audit the current Events wheel, then install it in a new virtual
   environment outside the checkout with pinned psycopg 3.3.8 and Python 3.13.5.
2. Verify installed origin and package resources. Execute the complete packaged
   initial and grants SQL under the selected non-login owner role in a transaction.
3. Bind the six owner-receipt fields using psycopg RawCursor, retaining the original
   packaged `$1` through `$6` placeholders. Check exact values and database time.
4. Inspect the actual catalog's twelve corrected single-column function return
   types and the expected function/table counts. Roll the installation back and
   verify the schema is absent.
5. Install again after that acknowledged intentional rollback. Verify the staged
   schema is invisible to a second connection, reject a duplicate receipt, and
   acknowledge a successful commit.
6. Connect separately as each restricted fixture login. Check the entire function
   execution matrix, schema permissions and table/column denial. Exercise actual
   read wrappers, mutation-access denial, private-function denial and role-switch
   denial. Only runtime/reconciler may call E14; operator must be denied.

Each unexpected error stops the lane. It never repairs a fixture or retries an
uncertain operation. A passed lane qualifies these synthetic installed-wheel
installation and ACL cases only. It does not qualify the complete native transport,
recovery/fault scenarios, Workers composition, deployment or release readiness.
No PostgreSQL execution has passed until the exact-commit hosted run says so.

## Verified hosted result

The [17-job run at `9362f0d`](https://github.com/maxxab/modkit-events/actions/runs/42761194113)
completed successfully, including the fresh PostgreSQL installation and ACL job.
All six checks above passed against the unchanged corrected Events wheel and
migration. Standard Actions teardown removed the disposable service and network.
This result establishes only the stated synthetic scope; broader installation
negative cases, full native recovery and downstream composition remain separate.

## Offline preparation

The checker was implemented after nine offline guard tests failed on the missing
implementation. These controls run in the ordinary source suite without a server.
The exact workflow, role/bootstrap/cleanup scope and checker require independent
review before the workflow is published and executed.
