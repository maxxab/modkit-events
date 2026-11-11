"""PROPOSED one-shot hosted native smoke. NOT APPROVED OR EXECUTED.

No fixture creation or automatic recovery/disposal on error. Only direct main
execution with the explicit future packet gate can connect.
"""

import json
import os
import platform
import struct
import sys
import sysconfig
from pathlib import Path


def main():
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "maxxab/modkit-events",
        "MODKIT_NATIVE_PACKET": "events-e14-close-v1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_JOB": "events-e14-close-v1",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    if any(os.environ.get(k) != v for k, v in required.items()):
        raise RuntimeError("exact separately approved hosted packet context required")
    if any(k.startswith("PG") for k in os.environ):
        raise RuntimeError("inherited PostgreSQL settings refused")
    if len(sys.argv) != 1 or not sys.flags.isolated or sys.flags.optimize:
        raise RuntimeError("isolated nonoptimized invocation without arguments required")
    if sys.platform != "linux" or tuple(sys.version_info) != (3, 13, 5, "final", 0):
        raise RuntimeError("exact Linux CPython3.13.5 required")
    if (
        platform.machine() != "x86_64"
        or struct.calcsize("P") != 8
        or sysconfig.get_config_var("Py_DEBUG") != 0
        or sysconfig.get_config_var("Py_GIL_DISABLED") != 0
        or getattr(sys, "_is_gil_enabled", lambda: False)() is not True
    ):
        raise RuntimeError("exact release/GIL x86_64 build required")
    import psycopg

    import modkit_events

    if (
        psycopg.__version__ != "3.3.8"
        or psycopg.pq.__impl__ != "binary"
        or psycopg.pq.version() != 180006
    ):
        raise RuntimeError("exact binary driver required")
    if sys.prefix == sys.base_prefix or not Path(modkit_events.__file__).resolve().is_relative_to(
        Path(sys.prefix).resolve()
    ):
        raise RuntimeError("outside-checkout installed candidate required")
    from modkit_events.persistence import managed_lifecycle as m
    from modkit_events.persistence import native_execution as e
    from modkit_events.persistence import native_sync as n
    from modkit_events.persistence.catalog import get_statement
    from modkit_events.persistence.ledger import ExecutionLedger

    ledger = ExecutionLedger()
    m.configure_managed_registry(
        limits=m.LifecycleLimits(
            retained_cells=1,
            admitted_live=1,
            checkouts=1,
            roots=1,
            roots_per_checkout=1,
            executions=1,
            preparations=1,
            preparations_per_execution=1,
            prepare_bytes=4096,
            prepare_bytes_per_execution=4096,
            results=1,
            results_per_ticket=1,
            result_bytes=64,
            result_bytes_per_ticket=64,
            cleanup_bundles=1,
            cleanup_bytes=4096,
            construction_slots=2,
        ),
        execution_ledger=ledger,
    )
    execution = m.reserve_execution(ledger)
    actual = n.ManagedConnection.connect(
        execution_ledger=ledger,
        host="127.0.0.1",
        hostaddr="127.0.0.1",
        port=5432,
        dbname="modkit_events_ci",
        user="modkit_ci_runtime_login",
        password="modkit-ci-public-fixture-only",
        passfile="/dev/null",
        connect_timeout=5,
        sslmode="disable",
        autocommit=False,
        application_name="events-e14-close-v1",
        options="-c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000 -c timezone=UTC",
    )
    checkout = n.attach_native(actual, execution, execution_ledger=ledger)
    xids = []
    for end in ("rollback", "commit"):
        root = n.start_root(checkout, execution_ledger=ledger)
        actual.execute("SET LOCAL ROLE modkit_runtime")
        identity = actual.execute(
            "SELECT current_database(),session_user,current_user,current_setting('server_version_num')::int"
        ).fetchone()
        if identity != ("modkit_events_ci", "modkit_ci_runtime_login", "modkit_runtime", 170011):
            raise RuntimeError("target identity mismatch")
        expected = int(actual.execute("SELECT pg_current_xact_id()::text").fetchone()[0])
        preparation = e.prepare(
            execution, get_statement("E14"), (), execution_ledger=ledger, capacity=4096
        )
        ticket = m.admit(root, preparation, execution_ledger=ledger)
        result = m.reserve_result(ticket, 64, execution_ledger=ledger)
        e.execute(ticket, result, execution_ledger=ledger)
        value = m.read_result(result, execution_ledger=ledger)
        if type(value) is not int or value != expected:
            raise RuntimeError("native binary XID/root mismatch")
        # Keep the independently queried scalar, never the borrowed result alias.
        xids.append(expected)
        value = None
        m.release_result(result, execution_ledger=ledger)
        m.release_ticket(ticket, execution_ledger=ledger)
        m.release_preparation(preparation, execution_ledger=ledger)
        if end == "rollback":
            receipt = n.rollback(root, execution_ledger=ledger)
            m.acknowledge_root_end(receipt, execution_ledger=ledger)
        else:
            receipt = n.commit(root, execution_ledger=ledger)
            if (
                m.acknowledge_commit_result(receipt, execution_ledger=ledger)
                is not m.CommitOutcome.COMMITTED
            ):
                raise RuntimeError("commit outcome not confirmed")
        m.release_root(root, execution_ledger=ledger)
    if xids[0] == xids[1] or ledger.uncertainty.present:
        raise RuntimeError("successive root or uncertainty mismatch")
    m.retire(checkout, execution_ledger=ledger)
    intent = m.prepare_cleanup(checkout, execution_ledger=ledger)
    bundle = m.reserve_cleanup(intent, 4096, execution_ledger=ledger)
    permit = m.pin_cleanup(bundle, execution_ledger=ledger)
    receipt = n.close(permit, execution_ledger=ledger)
    m.acknowledge_physical_close(receipt, execution_ledger=ledger)
    if not actual.closed:
        raise RuntimeError("driver close not observed")
    m.release_cleanup(bundle, execution_ledger=ledger)
    m.detach_terminal(checkout, execution_ledger=ledger)
    m.dispose_execution(execution, execution_ledger=ledger)
    counters = m.capacity_snapshot(execution_ledger=ledger)
    if any(counters.values()) or ledger.uncertainty.present:
        raise RuntimeError("final counters/uncertainty not zero")
    print(
        json.dumps(
            {
                "case": "events-e14-close-v1",
                "status": "PASS",
                "distinct_root_xids": True,
                "physical_close": True,
                "counters": counters,
            }
        )
    )


if __name__ == "__main__":
    main()
