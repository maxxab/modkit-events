"""Mandatory pre-SQL native capacity gate."""

import unittest
from dataclasses import replace

from test_native_recovery_contract import header, request
from test_native_recovery_profile import profile

from modkit_events.persistence import managed_lifecycle as m
from modkit_events.persistence.errors import ErrorCode, _ValidationReject


class LifecycleTests(unittest.TestCase):
    def test_short_result_mandatory_guard(self):
        self.assertEqual(
            m._listing_capacity_error({"data": request(), "capacity": 100000}, 1),
            ErrorCode.CAPACITY_EXCEEDED,
            "E13 mandatory guard missing",
        )

    def test_minima_exact_and_short(self):
        p = profile(self)
        prep = {"data": request(), "capacity": p._recovery_preparation_min()}
        self.assertIsNone(m._listing_capacity_error(prep, p._recovery_result_min(1)))
        self.assertEqual(
            m._listing_capacity_error(prep, p._recovery_result_min(1) - 1),
            ErrorCode.CAPACITY_EXCEEDED,
        )
        prep["capacity"] -= 1
        self.assertEqual(
            m._listing_capacity_error(prep, p._recovery_result_min(1)), ErrorCode.CAPACITY_EXCEEDED
        )

    def test_tamper_and_original_payload_hooks(self):
        p = profile(self)
        req = request()
        object.__setattr__(req, "statement", replace(req.statement))
        self.assertEqual(
            m._listing_capacity_error(
                {"data": req, "capacity": p._recovery_preparation_min()}, p._recovery_result_min(1)
            ),
            ErrorCode.PROFILE_REJECTED,
        )
        from modkit_events.persistence import rows as R

        page = R._decode_native_recovery_result_raw(request(), (header(),))

        class Hook:
            def __sizeof__(self):
                raise AssertionError("hook invoked")

            def __eq__(self, other):
                raise AssertionError("hook invoked")

        object.__setattr__(page, "visited", Hook())
        with self.assertRaises(_ValidationReject):
            m._typed_result_size(request(), page)

    def test_actual_start_gate_precedes_running(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import patch

        from modkit_events.persistence.errors import PersistenceError

        p = profile(self)
        req = request()
        marker = object()
        ticket = SimpleNamespace(_subject=marker)
        result = object()
        for short in (True, False):
            preparation = {"data": req, "capacity": p._recovery_preparation_min()}
            operation = {"state": "ADMITTED", "prep": preparation, "results": 1, "running": False}
            physical = SimpleNamespace(
                operation=operation,
                current=marker,
                roots={marker: {"token": marker, "state": "ACTIVE"}},
            )
            record = {
                "operation": operation,
                "populated": False,
                "capacity": p._recovery_result_min(1) - int(short),
            }
            result = SimpleNamespace(_stamp=object())
            with (
                patch.object(m, "_context", return_value=False),
                patch.object(m, "_require_handles"),
                patch.object(m, "_construction", return_value=nullcontext()),
                patch.object(m, "_ticket", return_value=physical),
                patch.object(m, "_envelope", return_value=record),
                patch.object(m, "_usable", return_value=True),
                patch.object(m, "_failure_admission_error", return_value=None),
            ):
                if short:
                    with self.assertRaises(PersistenceError) as caught:
                        m._start_operation(ticket, result, object())
                    self.assertEqual(caught.exception.code, ErrorCode.CAPACITY_EXCEEDED)
                    self.assertEqual(operation["state"], "ADMITTED")
                    self.assertFalse(operation["running"])
                else:
                    self.assertIs(m._start_operation(ticket, result, object()), req)
                    self.assertEqual(operation["state"], "RUNNING")
                    self.assertTrue(operation["running"])
