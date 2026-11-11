"""Opt-in real-driver qualification against an explicitly supplied disposable DB.

No connection occurs during import. The caller owns fixture setup and cleanup.
Run directly with a pinned interpreter and MODKIT_NATIVE_TEST_DSN, or leave it
unset to skip. This test does not authorize installing a driver or starting DBs.
"""

import json
import logging
import os
import signal
import sys
import unittest
from pathlib import Path


def profile():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import psycopg

    from modkit_events.persistence import managed_lifecycle as managed
    from modkit_events.persistence import native_execution as issuer
    from modkit_events.persistence import native_sync as native
    from modkit_events.persistence.catalog import get_statement
    from modkit_events.persistence.ledger import ExecutionLedger

    assert psycopg.__version__ == "3.3.8" and psycopg.pq.version() == 180006
    ledger = ExecutionLedger()
    managed.configure_managed_registry(
        limits=managed.LifecycleLimits(
            retained_cells=4,
            admitted_live=4,
            checkouts=4,
            roots=8,
            roots_per_checkout=4,
            executions=4,
            preparations=8,
            preparations_per_execution=4,
            prepare_bytes=8192,
            prepare_bytes_per_execution=4096,
            results=8,
            results_per_ticket=1,
            result_bytes=33554432,
            result_bytes_per_ticket=4194304,
            cleanup_bundles=4,
            cleanup_bytes=4096,
            construction_slots=8,
        ),
        execution_ledger=ledger,
    )
    execution = managed.reserve_execution(ledger)
    actual = native.ManagedConnection.connect(
        os.environ["MODKIT_NATIVE_TEST_DSN"],
        execution_ledger=ledger,
        application_name="modkit-native-" + os.environ.get("MODKIT_NATIVE_CASE", "normal"),
    )
    checkout = native.attach_native(actual, execution, execution_ledger=ledger)
    return psycopg, managed, issuer, native, get_statement, ledger, execution, actual, checkout


def statement(managed, issuer, get_statement, ledger, execution, root, key, parameters):
    preparation = issuer.prepare(execution, get_statement(key), parameters, execution_ledger=ledger)
    ticket = managed.admit(root, preparation, execution_ledger=ledger)
    result = managed.reserve_result(
        ticket, 64 if key == "E14" else 4194304, execution_ledger=ledger
    )
    issuer.execute(ticket, result, execution_ledger=ledger)
    value = managed.read_result(result, execution_ledger=ledger)
    managed.release_result(result, execution_ledger=ledger)
    managed.release_ticket(ticket, execution_ledger=ledger)
    managed.release_preparation(preparation, execution_ledger=ledger)
    return value


@unittest.skipUnless(
    os.environ.get("MODKIT_NATIVE_TEST_DSN"), "explicit disposable native DSN required"
)
class NativeObservationTests(unittest.TestCase):
    def test_original_root_binary_rows_and_explicit_finalization(self):
        psycopg, managed, issuer, native, catalog, ledger, execution, actual, checkout = profile()
        observer = psycopg.connect(os.environ["MODKIT_NATIVE_TEST_DSN"], autocommit=True)
        root = native.start_root(checkout, execution_ledger=ledger)
        expected = actual.execute(
            "INSERT INTO public.native_business(id) VALUES(1) RETURNING pg_current_xact_id()::text"
        ).fetchone()[0]
        xid = statement(managed, issuer, catalog, ledger, execution, root, "E14", ())
        self.assertEqual(xid, int(expected))
        self.assertEqual(actual.info.transaction_status, psycopg.pq.TransactionStatus.INTRANS)
        self.assertEqual(
            observer.execute("SELECT count(*) FROM public.native_business").fetchone(), (0,)
        )
        row = statement(
            managed, issuer, catalog, ledger, execution, root, "E28", (b"native-event",)
        )
        self.assertEqual(row.event_id, b"native-event")
        self.assertEqual(row.canonical_version, 1)
        self.assertEqual(row.state, "pending")
        self.assertEqual(row.ownership_revision, 0)
        self.assertEqual(
            (row.token, row.lease_until, row.intent_id, row.receipt, row.outcome_evidence),
            (None,) * 5,
        )
        self.assertEqual(json.loads(row.replay_input)["payload"], {"fixture": "native"})
        from datetime import datetime, timezone

        self.assertIs(type(row.created_at), datetime)
        self.assertIs(type(row.updated_at), datetime)
        self.assertIs(row.created_at.tzinfo, timezone.utc)
        self.assertIs(row.updated_at.tzinfo, timezone.utc)
        self.assertIsNone(
            statement(managed, issuer, catalog, ledger, execution, root, "E28", (b"missing",))
        )

        # Actual public customization is overridden only for the cursor's fixed
        # shapes. The caller's/global maps retain their sentinel classes.
        from psycopg.adapt import Dumper, Loader, PyFormat

        from modkit_events.persistence.native_codec import _selected_sql_descriptor

        called = []

        class PoisonDumper(Dumper):
            format = psycopg.pq.Format.BINARY
            oid = 17

            def dump(self, obj):
                called.append("dumper")
                raise AssertionError("NONSECRET_DUMPER")

        class PoisonLoader(Loader):
            format = psycopg.pq.Format.BINARY

            def __init__(self, *args, **kwargs):
                called.append("loader")
                raise AssertionError("NONSECRET_LOADER")

        actual.adapters.register_dumper(bytes, PoisonDumper)
        psycopg.adapters.register_dumper(bytes, PoisonDumper)
        for column in _selected_sql_descriptor(catalog("E28")).transport_columns:
            actual.adapters.register_loader(column.oid, PoisonLoader)
            psycopg.adapters.register_loader(column.oid, PoisonLoader)
        again = statement(
            managed, issuer, catalog, ledger, execution, root, "E28", (b"native-event",)
        )
        self.assertEqual(again, row)
        self.assertEqual(called, [])
        self.assertIs(actual.adapters.get_dumper(bytes, PyFormat.AUTO), PoisonDumper)
        self.assertIs(psycopg.adapters.get_dumper(bytes, PyFormat.AUTO), PoisonDumper)
        self.assertIs(actual.adapters.get_loader(17, psycopg.pq.Format.BINARY), PoisonLoader)
        receipt = native.rollback(root, execution_ledger=ledger)
        managed.acknowledge_root_end(receipt, execution_ledger=ledger)
        managed.release_root(root, execution_ledger=ledger)
        self.assertEqual(
            observer.execute("SELECT count(*) FROM public.native_business").fetchone(), (0,)
        )

        root = native.start_root(checkout, execution_ledger=ledger)
        # No binary adapters are used by this caller-owned text query.
        actual.execute("INSERT INTO public.native_business(id) VALUES(2)")
        second_xid = statement(managed, issuer, catalog, ledger, execution, root, "E14", ())
        self.assertNotEqual(second_xid, xid)
        self.assertEqual(
            observer.execute("SELECT count(*) FROM public.native_business").fetchone(), (0,)
        )
        receipt = native.commit(root, execution_ledger=ledger)
        self.assertIs(
            managed.acknowledge_commit_result(receipt, execution_ledger=ledger),
            managed.CommitOutcome.COMMITTED,
        )
        managed.release_root(root, execution_ledger=ledger)
        self.assertEqual(
            observer.execute("SELECT id FROM public.native_business").fetchall(), [(2,)]
        )
        self.assertFalse(ledger.uncertainty.present)
        self.assertEqual(managed.capacity_snapshot(execution_ledger=ledger)["D"], 0)
        # Explicit caller fixture cleanup, not an adapter-generated close receipt.
        actual.close()
        observer.close()
        print(
            json.dumps(
                {
                    "case": "normal",
                    "status": "PASS",
                    "same_root_xid": True,
                    "rollback_erased_business": True,
                    "commit_persisted_business": True,
                    "full_and_absent_e28": True,
                    "custom_callbacks": called,
                }
            ),
            flush=True,
        )


def fault_case():
    psycopg, managed, issuer, native, catalog, ledger, execution, actual, checkout = profile()
    from modkit_events.persistence.errors import ErrorCode, PersistenceError

    mode = os.environ["MODKIT_NATIVE_CASE"]
    root = native.start_root(checkout, execution_ledger=ledger)
    actual.execute("INSERT INTO public.native_business(id) VALUES(10)")
    preparation = issuer.prepare(
        execution,
        catalog("E28"),
        (b"NONSECRET_EVENT_SENTINEL_DO_NOT_LOG",),
        execution_ledger=ledger,
    )
    ticket = managed.admit(root, preparation, execution_ledger=ledger)
    result = managed.reserve_result(ticket, 4194304, execution_ledger=ledger)
    interrupt = KeyboardInterrupt("NONSECRET_INTERRUPT")
    logger_error = RuntimeError("NONSECRET_LOGGER_FAILURE")
    logs = []
    records = []
    sentinels = (
        "NONSECRET_EVENT_SENTINEL_DO_NOT_LOG",
        "NONSECRET_CREDENTIAL_SENTINEL",
    )

    class Capture(logging.Handler):
        def emit(self, record):
            text = record.getMessage()
            logs.append(text)
            record_values = {key: repr(value) for key, value in record.__dict__.items()}
            records.append(record_values)
            assert all(
                sentinel not in text
                and all(sentinel not in value for value in record_values.values())
                for sentinel in sentinels
            )
            if mode == "logger":
                raise logger_error

    logger = logging.getLogger("psycopg")
    handler = Capture()
    logger.addHandler(handler)

    def interrupted(signum, frame):
        raise interrupt

    signal.signal(signal.SIGUSR1, interrupted)
    print(
        json.dumps({"event": "STARTING", "backend_pid": actual.info.backend_pid, "case": mode}),
        flush=True,
    )
    caught = None
    received = []

    def observe(frame, event, arg):
        if frame.f_code is issuer.execute.__code__ and event == "exception":
            error = arg[1]
            if not received and (error is interrupt or error is logger_error):
                received.append(
                    (
                        error,
                        BaseException.__cause__.__get__(error),
                        BaseException.__context__.__get__(error),
                        BaseException.__suppress_context__.__get__(error),
                        arg[2],
                    )
                )
        return observe

    previous_trace = sys.gettrace()
    try:
        sys.settrace(observe)
        issuer.execute(ticket, result, execution_ledger=ledger)
    except BaseException as error:
        caught = error
    finally:
        sys.settrace(previous_trace)
    assert len(received) == 1 and received[0][0] is caught
    assert BaseException.__cause__.__get__(caught) is received[0][1]
    assert BaseException.__context__.__get__(caught) is received[0][2]
    assert BaseException.__suppress_context__.__get__(caught) is received[0][3]
    suffix = BaseException.__traceback__.__get__(caught)
    while suffix is not None and suffix is not received[0][4]:
        suffix = suffix.tb_next
    assert suffix is received[0][4]
    if mode == "logger":
        assert caught is logger_error
    else:
        assert caught is interrupt
    state = managed._ticket(ticket, ledger)
    assert state.operation["state"] == "HELD" and state.roots[ticket._subject]["state"] == "UNKNOWN"
    assert ledger.uncertainty.present and state.blocked_root
    assert not managed._results[result._stamp]["populated"]
    assert managed._counts["D"] >= 1
    if mode == "interrupt":
        assert actual.info.transaction_status == psycopg.pq.TransactionStatus.INERROR
        assert not state.operation["running"] and logs == []
    elif mode == "logger":
        assert not actual.closed and state.operation["running"]
        assert any("query cancellation failed:" in item for item in logs)
    else:
        assert actual.closed and state.operation["running"]
        assert any("query cancellation failed:" in item for item in logs)
        assert any(
            "query not terminated after cancellation: closing connection" in item for item in logs
        )
    for action in (
        lambda: managed.release_result(result, execution_ledger=ledger),
        lambda: managed.release_ticket(ticket, execution_ledger=ledger),
    ):
        try:
            action()
        except PersistenceError as error:
            assert error.code is ErrorCode.RESOURCE_BUSY
        else:
            raise AssertionError("failure gate released")
    print(
        json.dumps(
            {
                "case": mode,
                "status": "PASS",
                "held": True,
                "running": state.operation["running"],
                "closed": actual.closed,
                "received_primary_identity": True,
                "received_primary_graph_and_suffix": True,
                "payload_materialization_privacy": "NOT_RUN",
                "logs": logs,
                "records": records,
            }
        ),
        flush=True,
    )
    logger.removeHandler(handler)
    actual.close()  # Explicit fixture-owner teardown after assertions, no refund.


if __name__ == "__main__":
    if os.environ.get("MODKIT_NATIVE_CASE", "normal") == "normal":
        unittest.main()
    else:
        fault_case()
