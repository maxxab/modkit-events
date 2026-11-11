"""Finite logical accounting and all 17 lifecycle limits."""

import importlib
import importlib.util
import unittest
from contextlib import ExitStack, contextmanager
from dataclasses import fields
from sys import getsizeof
from unittest.mock import patch
from uuid import UUID

from recovery_test_support import requires_recovery_profile
from test_native_recovery_contract import header, request

from modkit_events.persistence import bindings as B
from modkit_events.persistence import managed_lifecycle as m
from modkit_events.persistence import observations as O


def profile(test):
    test.assertIsNotNone(
        importlib.util.find_spec("modkit_events.persistence.recovery_profile"),
        "pure recovery profile missing",
    )
    return importlib.import_module("modkit_events.persistence.recovery_profile")


def readiness():
    return B.ReadinessExpectation(
        components=tuple(
            O.SchemaStatus(
                component=c,
                version=2147483647,
                migration_digest=b"x" * 32,
                catalog_contract_id="modkit-pg-ab-2",
                scope_format_id="MKSC-1",
                intent_format_id="MKPF-1",
            )
            for c in ("events", "workers")
        )
    )


@requires_recovery_profile
class ProfileTests(unittest.TestCase):
    def test_generic_minima_complete_vector(self):
        p = profile(self)
        exp = readiness()
        req = p.recovery_requirements(readiness=exp)
        self.assertIs(req.readiness, exp)
        self.assertEqual(req.namespace, b"jobs")
        self.assertEqual(req.page_limit, 1)
        self.assertEqual(req.e13_preparation_min, p._recovery_preparation_min())
        self.assertEqual(req.e13_result_min, p._recovery_result_min(1))
        self.assertGreaterEqual(
            req.e13_preparation_min,
            m._preparation_size(
                request(
                    namespace=b"x" * 256,
                    kind="inbox",
                    limit=256,
                    scan_after=UUID(int=2**128 - 1),
                    discovery_budget=4096,
                )
            ),
        )
        limits = req.lifecycle_minimum
        self.assertEqual(len(fields(limits)), 17)
        for f in fields(limits):
            expected = (
                2
                if f.name == "construction_slots"
                else 4096
                if f.name == "cleanup_bytes"
                else max(req.e13_preparation_min, req.e33_preparation_min)
                if f.name.startswith("prepare_bytes")
                else max(req.e13_result_min, req.e33_result_min)
                if f.name.startswith("result_bytes")
                else 1
            )
            self.assertEqual(getattr(limits, f.name), expected, f.name)
        from modkit_events.persistence.catalog import get_statement

        r = B._freeze_request_raw(
            get_statement("E33"), ("workers",), context=B._return_context_raw(readiness=exp)
        )
        self.assertGreaterEqual(req.e33_preparation_min, m._preparation_size(r))
        self.assertGreaterEqual(req.e33_result_min, m._typed_result_size(r, exp.components))

    def test_full_graph_occurrence_accounting(self):
        p = profile(self)
        from test_native_recovery_contract import wire_item

        from modkit_events.persistence import rows as R

        req = request()
        page = R._decode_native_recovery_result_raw(
            req, (header(1, UUID(int=1), False), wire_item())
        )

        def size(v):
            return getsizeof(v) + (getsizeof(v.int) if type(v) is UUID else 0)

        exact = (
            getsizeof(page)
            + getsizeof(page.items)
            + sum(size(getattr(page, n)) for n in ("visited", "next_cursor", "pass_exhausted"))
        )
        exact += sum(
            getsizeof(w) + sum(size(getattr(w, n)) for n in w.__dataclass_fields__)
            for w in page.items
        )
        self.assertEqual(m._typed_result_size(req, page), exact)
        self.assertLessEqual(exact, p._recovery_result_min(1))
        self.assertGreater(p._recovery_result_min(256), 255 * p._recovery_result_min(1))

    def test_every_scalar_maximum_without_allocating_a_max_page(self):
        from datetime import datetime, timezone

        from modkit_events.persistence.catalog import WireType, get_statement

        p = profile(self)
        for col, (_, cap) in zip(get_statement("E13").result.columns[4:43], p._CAPS[4:43]):
            values = {
                WireType.BYTEA: lambda: b"x" * cap,
                WireType.TEXT: lambda: chr(0x10000) * cap,
                WireType.INT4: lambda: -(2**31),
                WireType.INT8: lambda: -(2**63),
                WireType.XID8: lambda: 2**64 - 1,
                WireType.UUID: lambda: UUID(int=2**128 - 1),
                WireType.TIMESTAMPTZ: lambda: datetime(2000, 1, 1, tzinfo=timezone.utc),
                WireType.BOOL: lambda: True,
            }
            value = values[col.wire_type]()
            actual = getsizeof(value) + (getsizeof(value.int) if type(value) is UUID else 0)
            self.assertLessEqual(actual, p._column_max(col, cap), col.name)


# These stand-ins exercise branch selection on the host, NOT actual 3.13 qualification.


@contextmanager
def simulated313(p, *, machine="x86_64", debug=0, free_threaded=0, gil=True):
    import platform
    import sysconfig

    with ExitStack() as stack:
        stack.enter_context(patch.object(p.sys, "version_info", (3, 13, 5, "final", 0)))
        stack.enter_context(patch.object(platform, "machine", return_value=machine))
        stack.enter_context(
            patch.object(
                sysconfig,
                "get_config_var",
                side_effect=lambda name: {"Py_DEBUG": debug, "Py_GIL_DISABLED": free_threaded}.get(
                    name
                ),
            )
        )
        stack.enter_context(patch.object(p.sys, "_is_gil_enabled", return_value=gil, create=True))
        yield


@requires_recovery_profile
class AdditionalProfileTests(unittest.TestCase):
    def test_simulated313_truthful_profile_and_unchanged_minima(self):
        p = profile(self)
        with simulated313(p):
            req = p.recovery_requirements(readiness=readiness())
            self.assertEqual(
                req.interpreter_profile_id, "cpython-3.13.5-linux-x86_64-gil-release-recovery-v1"
            )
            self.assertEqual(
                (req.e13_preparation_min, req.e13_result_min, p._recovery_result_min(256)),
                (761, 5252364, 1344536844),
            )
            self.assertEqual(
                (req.lifecycle_minimum.construction_slots, req.lifecycle_minimum.cleanup_bytes),
                (2, 4096),
            )

    def test_preserved312_identity_and_no_new_machine_restriction(self):
        p = profile(self)
        with simulated313(p, machine="aarch64", debug=1, free_threaded=1, gil=False):
            with patch.object(p.sys, "version_info", (3, 12, 3)):
                self.assertEqual(
                    p.recovery_requirements(readiness=readiness()).interpreter_profile_id,
                    "cpython-3.12.3-linux-64-recovery-v1",
                )

    def test_simulated313_unsupported_builds_and_layouts_fail_closed(self):
        from modkit_events.persistence.errors import PersistenceError

        p = profile(self)
        for changes in (
            {"machine": "aarch64"},
            {"debug": 1},
            {"debug": None},
            {"free_threaded": 1},
            {"free_threaded": None},
            {"gil": False},
            {"gil": None},
        ):
            with self.subTest(changes=changes), simulated313(p, **changes):
                with self.assertRaises(PersistenceError):
                    p.recovery_requirements(readiness=readiness())
        with simulated313(p), patch.object(p.sys, "getsizeof", return_value=9999):
            with self.assertRaises(PersistenceError):
                p.recovery_requirements(readiness=readiness())

    def test_simulated313_requires_full_final_zero_release(self):
        from modkit_events.persistence.errors import PersistenceError

        p = profile(self)
        versions = (
            (3, 13, 5, "alpha", 0),
            (3, 13, 5, "beta", 0),
            (3, 13, 5, "candidate", 0),
            (3, 13, 5, "final", 1),
            (3, 13, 5),
            (3, 13, 5, "final"),
        )
        for version in versions:
            with self.subTest(version=version), simulated313(p):
                with patch.object(p.sys, "version_info", version):
                    with self.assertRaises(PersistenceError):
                        p.recovery_requirements(readiness=readiness())
