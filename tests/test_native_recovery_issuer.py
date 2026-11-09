"""Structural PGresult only: no driver execution or connection."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_native_recovery_codec import wire_header
from test_native_recovery_contract import request

from modkit_events.persistence import native_execution as n
from modkit_events.persistence.errors import ErrorCode, PersistenceError


class Result:
    def __init__(self, d, values):
        self.d = d
        self.values = values
        self.ntuples = len(values)
        self.nfields = 61
        self.status = n.pq.ExecStatus.TUPLES_OK
        self.binary_tuples = 1
        self.command_status = ("SELECT " + str(self.ntuples)).encode()
        self.command_tuples = self.ntuples

    def fname(self, i):
        return self.d.transport_columns[i].name.encode()

    def ftype(self, i):
        return self.d.transport_columns[i].oid

    def fformat(self, i):
        return 1

    def fsize(self, i):
        return n._FIXED_WIDTHS[self.ftype(i)]

    def get_value(self, r, c):
        return self.values[r][c]


class IssuerTests(unittest.TestCase):
    def test_header_and_sentinel_materialization(self):
        self.assertTrue(
            callable(getattr(n, "prepare_recovery", None)), "paid E13 preparation missing"
        )
        req = request()
        d = n._selected_sql_descriptor(req.statement, request=req)
        for count in (1, 0, 3):
            result = Result(d, [wire_header()] * count)
            cursor = SimpleNamespace(
                pgresult=result,
                rowcount=count,
                statusmessage="SELECT " + str(count),
                nextset=lambda: None,
            )
            if count == 1:
                self.assertEqual(n._materialize(cursor, req, d).items, ())
            else:
                with self.assertRaises(PersistenceError):
                    n._materialize(cursor, req, d)

    def test_minimum_before_builder(self):
        self.assertTrue(
            callable(getattr(n, "prepare_recovery", None)), "paid E13 preparation missing"
        )
        from test_native_recovery_profile import profile

        p = profile(self)
        minimum = p._recovery_preparation_min()
        with (
            patch.object(n._managed, "_context", return_value=False),
            patch.object(n._managed, "_require_handles"),
            patch.object(n, "_freeze_request_raw", side_effect=AssertionError("builder reached")),
            patch.object(
                n._managed,
                "_reserve_preparation_paid",
                side_effect=AssertionError("reservation reached"),
            ),
        ):
            with self.assertRaises(PersistenceError) as caught:
                n.prepare_recovery(
                    object(),
                    execution_ledger=object(),
                    capacity=minimum - 1,
                    namespace=b"jobs",
                    kind="job",
                    limit=1,
                    scan_after=None,
                    discovery_budget=128,
                )
            self.assertEqual(caught.exception.code, ErrorCode.CAPACITY_EXCEEDED)


class ExecuteTests(unittest.TestCase):
    def test_actual_issuer_serial_flow_and_fault_containment(self):
        from contextlib import ExitStack, nullcontext

        from test_native_recovery_profile import profile

        from modkit_events.persistence import managed_lifecycle as m

        p = profile(self)
        for fault in (None, "short", "metadata", "cap", "nextset"):
            req = request()
            d = n._selected_sql_descriptor(req.statement, request=req)
            cells = list(wire_header())
            if fault == "cap":
                cells[0] = b"\\x00"
            pgresult = Result(d, [tuple(cells)])
            if fault == "metadata":
                pgresult.nfields = 60
            calls = []
            published = []
            held = []
            original = SimpleNamespace(transaction_status=n.pq.TransactionStatus.INTRANS)
            actual = SimpleNamespace(pgconn=original, closed=False)

            class Adapters:
                def register_dumper(self, *args):
                    pass

                def register_loader(self, *args):
                    pass

            class Cursor:
                def __init__(self, connection, *, row_factory):
                    self.adapters = Adapters()
                    self.pgresult = pgresult
                    self.rowcount = 1
                    self.statusmessage = "SELECT 1"

                def execute(self, sql, parameters, *, prepare, binary):
                    calls.append((sql, parameters, prepare, binary))

                def close(self):
                    calls.append("closed")

                def nextset(self):
                    return True if fault == "nextset" else None

            def start(*args, **kwargs):
                minimum = p._recovery_result_min(1)
                code = m._listing_capacity_error(
                    {"data": req, "capacity": p._recovery_preparation_min()},
                    minimum - int(fault == "short"),
                )
                m._reject(code, False)
                return req

            def publish(result, value, **kwargs):
                self.assertLessEqual(m._typed_result_size(req, value), p._recovery_result_min(1))
                published.append(value)

            with ExitStack() as stack:
                patches = [
                    patch.object(n._native, "_shape", return_value=False),
                    patch.object(
                        m, "_construction", side_effect=lambda flag: nullcontext(object())
                    ),
                    patch.object(m, "_start_operation", side_effect=start),
                    patch.object(m, "_operation_profile", return_value=None),
                    patch.object(n._native, "_borrow", side_effect=lambda *a: (actual, original)),
                    patch.object(n._native, "_live", return_value=True),
                    patch.object(n.psycopg, "RawCursor", Cursor),
                    patch.object(m, "set_result", side_effect=publish),
                    patch.object(m, "_complete_operation"),
                    patch.object(m, "validate_ticket"),
                    patch.object(m, "_observe_native_result_paid"),
                    patch.object(m, "_owns_operation_paid", return_value=fault != "short"),
                    patch.object(
                        m, "_fail_operation_paid", side_effect=lambda *a, **k: held.append(k)
                    ),
                ]
                for replacement in patches:
                    stack.enter_context(replacement)
                if fault:
                    with self.assertRaises(PersistenceError):
                        n.execute(object(), object(), execution_ledger=object())
                    self.assertFalse(published)
                    self.assertEqual(bool(held), fault != "short")
                else:
                    n.execute(object(), object(), execution_ledger=object())
                    self.assertEqual(len(published), 1)
                if fault == "short":
                    self.assertEqual(calls, [])
                    n._native._borrow.assert_not_called()
                else:
                    self.assertEqual(len(calls), 2)
                    self.assertIs(calls[0][1], req.parameters)
                    self.assertEqual(calls[0][0], d.sql)
                    self.assertEqual(calls[0][2:], (False, True))
                    self.assertEqual(calls[-1], "closed")


class PreparationTests(unittest.TestCase):
    def test_paid_builder_retains_exact_request_after_reservation(self):
        from contextlib import nullcontext

        from test_native_recovery_profile import profile

        p = profile(self)
        events = []
        token = object()
        retained = []
        original = n._return_context_raw

        def reserve(*args):
            events.append("reserved")
            return token, None

        def context():
            self.assertEqual(events, ["reserved"])
            events.append("context")
            return original()

        def store(preparation, req, ledger, paid, **kwargs):
            self.assertIs(preparation, token)
            self.assertEqual(events, ["reserved", "context"])
            self.assertEqual(req.parameters, (b"jobs", "job", 1, None, 128))
            retained.append(req)
            return None

        with (
            patch.object(n._managed, "_context", return_value=False),
            patch.object(n._managed, "_require_handles"),
            patch.object(n._managed, "_construction", return_value=nullcontext(object())),
            patch.object(n._managed, "_reserve_preparation_paid", side_effect=reserve),
            patch.object(n, "_return_context_raw", side_effect=context),
            patch.object(n._managed, "_set_preparation_paid", side_effect=store),
            patch.object(
                n._managed,
                "_release_preparation_paid",
                side_effect=AssertionError("unexpected release"),
            ),
        ):
            result = n.prepare_recovery(
                object(),
                execution_ledger=object(),
                capacity=p._recovery_preparation_min(),
                namespace=b"jobs",
                kind="job",
                limit=1,
                scan_after=None,
                discovery_budget=128,
            )
        self.assertIs(result, token)
        self.assertEqual(len(retained), 1)
