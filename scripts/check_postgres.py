"""Fresh Actions-only PostgreSQL installation checks, never a deployment runner.

The credentials below are public, disposable fixture values. No existing account,
connection string, native authorization packet, or secret is accepted.
"""

import importlib.metadata
import os
import sys
from pathlib import Path

DATABASE = "modkit_events_ci"
PASSWORD = "modkit-ci-public-fixture-only"
LOGIN_ROLES = {
    "modkit_ci_bootstrap": None,
    "modkit_ci_owner_login": "modkit_owner",
    "modkit_ci_runtime_login": "modkit_runtime",
    "modkit_ci_reconciler_login": "modkit_reconciler",
    "modkit_ci_operator_login": "modkit_operator",
}
READ_FUNCTIONS = {
    "e09",
    "e15",
    "e16",
    "e17",
    "e18",
    "e19",
    "e20",
    "e21",
    "e28",
    "e29",
    "e30",
    "e33",
    "e34",
}
RUNTIME_FUNCTIONS = {
    "e01",
    "e02",
    "e03",
    "e04",
    "e05",
    "e06",
    "e07",
    "e08",
    "e10",
    "e11",
    "e22",
    "e23",
    "e24",
    "e25",
    "e32",
}
RECONCILER_FUNCTIONS = {"e12", "e13", "e26", "e27", "e31"}


def require_ci_environment(env):
    expected = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "maxxab/modkit-events",
        "MODKIT_POSTGRES_TEST": "events-installation-v1",
    }
    if any(env.get(key) != value for key, value in expected.items()):
        raise ValueError("explicit synthetic GitHub CI context required")
    if any(key.startswith("PG") for key in env):
        raise ValueError("existing PostgreSQL environment must not be inherited")


def connection_options(login):
    if login not in LOGIN_ROLES:
        raise ValueError("unknown fixture login")
    return {
        "host": "127.0.0.1",
        "hostaddr": "127.0.0.1",
        "port": 5432,
        "dbname": DATABASE,
        "user": login,
        "password": PASSWORD,
        "connect_timeout": 5,
        "passfile": "/dev/null",
        "service": "",
        "sslmode": "disable",
        "options": "-c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000 -c timezone=UTC",
        "autocommit": True,
    }


def validate_target(row, roles, schemas):
    if not (
        len(row) == 4
        and type(row[0]) is int
        and 170000 <= row[0] < 180000
        and row[1:] == (DATABASE, "modkit_ci_bootstrap", "modkit_ci_bootstrap")
        and roles == ["modkit_ci_bootstrap"]
        and schemas == []
    ):
        raise ValueError("fresh synthetic PostgreSQL 17 target required")


def expected_function_roles(name, arity):
    if name.startswith("_") or (name == "e04" and arity == 9):
        return set()
    if name in READ_FUNCTIONS:
        return {"modkit_runtime", "modkit_reconciler", "modkit_operator"}
    if name in RUNTIME_FUNCTIONS:
        return {"modkit_runtime"}
    if name in RECONCILER_FUNCTIONS:
        return {"modkit_reconciler"}
    if name == "e14":
        return {"modkit_runtime", "modkit_reconciler"}
    raise ValueError("unexpected public function")


def bootstrap(psycopg):
    with psycopg.connect(**connection_options("modkit_ci_bootstrap")) as connection:
        row = connection.execute(
            "SELECT current_setting('server_version_num')::int, current_database(), session_user, current_user"
        ).fetchone()
        roles = [
            r[0]
            for r in connection.execute(
                "SELECT rolname FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname"
            )
        ]
        schemas = [
            r[0]
            for r in connection.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname NOT IN ('public','information_schema') ORDER BY nspname"
            )
        ]
        validate_target(row, roles, schemas)
        with connection.transaction():
            connection.execute("REVOKE ALL ON DATABASE modkit_events_ci FROM PUBLIC")
            for login, role in LOGIN_ROLES.items():
                if role is None:
                    continue
                connection.execute(
                    psycopg.sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(psycopg.sql.Identifier(role))
                )
                connection.execute(
                    psycopg.sql.SQL(
                        "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(psycopg.sql.Identifier(login), psycopg.sql.Literal(PASSWORD))
                )
                connection.execute(
                    psycopg.sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                        psycopg.sql.Identifier(role), psycopg.sql.Identifier(login)
                    )
                )
                connection.execute(
                    psycopg.sql.SQL("GRANT CONNECT ON DATABASE modkit_events_ci TO {}").format(
                        psycopg.sql.Identifier(login)
                    )
                )
            connection.execute("GRANT CREATE ON DATABASE modkit_events_ci TO modkit_owner")
    print("PASS fresh PostgreSQL 17 fixture bootstrap; privileged connection closed")


def selected_role(connection, psycopg, login):
    role = LOGIN_ROLES[login]
    connection.execute(psycopg.sql.SQL("SET LOCAL ROLE {}").format(psycopg.sql.Identifier(role)))
    assert connection.execute("SELECT session_user, current_user").fetchone() == (login, role)
    flags = connection.execute(
        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=session_user"
    ).fetchone()
    assert flags == (False,) * 5


def install(connection, psycopg, migration, initial, grants, receipt):
    selected_role(connection, psycopg, "modkit_ci_owner_login")
    connection.execute(initial, prepare=False)
    connection.execute(grants, prepare=False)
    values = (
        migration.component,
        migration.version,
        bytes.fromhex(migration.migration_digest),
        migration.catalog_contract_id,
        migration.scope_format_id,
        migration.intent_format_id,
    )
    before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    # RawCursor preserves the packaged $1-$6 placeholders. No SQL rewriting.
    with psycopg.RawCursor(connection) as cursor:
        cursor.execute(receipt, values)
    row = connection.execute(
        "SELECT component,version,migration_digest,catalog_contract_id,scope_format_id,intent_format_id,applied_at FROM modkit_events.schema_versions"
    ).fetchone()
    after = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    assert row[:6] == values
    assert before <= row[6] <= after
    # Test the actual catalog ABI, independently of the migration inventory.
    abi = dict(
        connection.execute(
            "SELECT proname,prorettype::regtype::text FROM pg_proc WHERE pronamespace='modkit_events'::regnamespace AND proname IN ('e14','e10','e01','e02','e07','e24','e25','e11','e05','e23','e06','e12')"
        )
    )
    assert abi == {
        "e14": "xid8",
        "e10": "boolean",
        "e01": "boolean",
        "e02": "boolean",
        "e07": "boolean",
        "e24": "boolean",
        "e25": "boolean",
        "e11": "boolean",
        "e05": "timestamp with time zone",
        "e23": "timestamp with time zone",
        "e06": "integer",
        "e12": "text",
    }
    assert connection.execute(
        "SELECT count(*) FROM pg_proc WHERE pronamespace='modkit_events'::regnamespace"
    ).fetchone() == (68,)
    assert connection.execute(
        "SELECT count(*) FROM pg_class WHERE relnamespace='modkit_events'::regnamespace AND relkind='r'"
    ).fetchone() == (12,)
    return values


class RollbackProbe(Exception):
    """Deliberate, acknowledged rollback test, never a failure retry."""


def denied(connection, psycopg, statement):
    try:
        with connection.transaction():
            connection.execute(statement)
            raise AssertionError("forbidden operation unexpectedly succeeded")
    except psycopg.Error as error:
        assert error.sqlstate == "42501", error.sqlstate


def restricted_checks(psycopg, values):
    for login, role in LOGIN_ROLES.items():
        if role not in {"modkit_runtime", "modkit_reconciler", "modkit_operator"}:
            continue
        with psycopg.connect(**connection_options(login)) as connection:
            with connection.transaction():
                selected_role(connection, psycopg, login)
                assert connection.execute(
                    "SELECT * FROM modkit_events.e33('events')"
                ).fetchall() == [values]
                functions = connection.execute(
                    "SELECT proname,pronargs,has_function_privilege(current_user,oid,'EXECUTE') FROM pg_proc WHERE pronamespace='modkit_events'::regnamespace"
                ).fetchall()
                assert len(functions) == 68
                for name, arity, allowed in functions:
                    assert allowed is (role in expected_function_roles(name, arity)), (
                        role,
                        name,
                        arity,
                    )
                assert connection.execute(
                    "SELECT has_schema_privilege(current_user,'modkit_events','USAGE'),has_schema_privilege(current_user,'modkit_events','CREATE')"
                ).fetchone() == (True, False)
                assert connection.execute(
                    "SELECT count(*) FROM pg_class WHERE relnamespace='modkit_events'::regnamespace AND relkind='r' AND (has_table_privilege(current_user,oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(current_user,oid,'SELECT,INSERT,UPDATE,REFERENCES'))"
                ).fetchone() == (0,)
                for query in (
                    "SELECT * FROM modkit_events.schema_versions",
                    "INSERT INTO modkit_events.schema_versions DEFAULT VALUES",
                    "SELECT work_id FROM modkit_events.work",
                    "CREATE TABLE modkit_events.ci_forbidden(value integer)",
                    "SELECT modkit_events._utf8_valid(''::bytea,1,false)",
                    "SET ROLE modkit_owner",
                    "SET ROLE modkit_ci_bootstrap",
                ):
                    denied(connection, psycopg, query)
                if role == "modkit_operator":
                    denied(connection, psycopg, "SELECT * FROM modkit_events.e14()")
                else:
                    assert (
                        len(connection.execute("SELECT * FROM modkit_events.e14()").fetchall()) == 1
                    )
        print("PASS restricted-role authorization:", role)


def main():
    require_ci_environment(os.environ)
    if (
        len(sys.argv) != 1
        or not sys.flags.isolated
        or sys.flags.optimize
        or sys.platform != "linux"
        or tuple(sys.version_info[:3]) != (3, 13, 5)
    ):
        raise ValueError("isolated non-optimized Linux Python 3.13.5 without arguments required")
    import psycopg

    import modkit_events
    from modkit_events.persistence.migrations import manifest, read_owner_receipt, read_sql

    prefix = Path(sys.prefix).resolve()
    origin = Path(modkit_events.__file__).resolve()
    if sys.prefix == sys.base_prefix or not origin.is_relative_to(prefix):
        raise ValueError("fresh outside-checkout installed package required")
    assert importlib.metadata.version("modkit-events") == "0.2.0"
    assert psycopg.__version__ == "3.3.8"
    (migration,) = manifest()
    initial, grants = (read_sql(migration, item) for item in migration.resources)
    assert migration.resources[0].path.endswith("0001_initial.sql")
    assert migration.resources[1].path.endswith("grants_runtime.sql")
    receipt = read_owner_receipt(migration)
    bootstrap(psycopg)
    # This is an intentional rollback test followed by a fresh acknowledged commit.
    # Any unexpected error stops the job; it is never retried or repaired in-place.
    with psycopg.connect(**connection_options("modkit_ci_owner_login")) as connection:
        try:
            with connection.transaction():
                install(connection, psycopg, migration, initial, grants, receipt)
                raise RollbackProbe
        except RollbackProbe:
            pass
        assert connection.execute("SELECT to_regnamespace('modkit_events')").fetchone() == (None,)
        print("PASS installation, exact catalog ABI and receipt rolled back completely")
        with connection.transaction():
            values = install(connection, psycopg, migration, initial, grants, receipt)
            with psycopg.connect(**connection_options("modkit_ci_owner_login")) as observer:
                assert observer.execute("SELECT to_regnamespace('modkit_events')").fetchone() == (
                    None,
                )
            try:
                with connection.transaction():
                    with psycopg.RawCursor(connection) as cursor:
                        cursor.execute(receipt, values)
                    raise AssertionError("duplicate receipt unexpectedly succeeded")
            except psycopg.errors.UniqueViolation:
                pass
            assert connection.execute(
                "SELECT count(*) FROM modkit_events.schema_versions"
            ).fetchone() == (1,)
        print("PASS installation, complete grants and six-bind receipt committed")
    restricted_checks(psycopg, values)
    print(
        "PASS synthetic installed-wheel PostgreSQL checks; migration:", migration.migration_digest
    )
    print("Not full native recovery, fault, deployment or release qualification.")


if __name__ == "__main__":
    main()
