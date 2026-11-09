"""Explicit driver checking, never connection construction."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_native_recovery_profile import profile, readiness

from modkit_events.persistence.errors import PersistenceError


class PreflightTests(unittest.TestCase):
    def test_requirements_never_import_driver(self):
        p = profile(self)
        with patch.dict(sys.modules, {"psycopg": None, "psycopg.pq": None}):
            req = p.recovery_requirements(readiness=readiness())
            with self.assertRaises(PersistenceError):
                p.verify_recovery_driver(req)

    def test_deferred_driver_exact_profile(self):
        p = profile(self)
        req = p.recovery_requirements(readiness=readiness())
        for version, lib, impl, ok in (
            ("3.3.8", 180006, "binary", True),
            ("3.3.7", 180006, "binary", False),
            ("3.3.8", 180005, "binary", False),
            ("3.3.8", 180006, "python", False),
        ):
            pg = SimpleNamespace(
                __version__=version, pq=SimpleNamespace(version=lambda: lib, __impl__=impl)
            )
            with patch.dict(sys.modules, {"psycopg": pg, "psycopg.pq": pg.pq}):
                if ok:
                    self.assertIs(p.verify_recovery_driver(req).requirements, req)
                else:
                    with self.assertRaises(PersistenceError):
                        p.verify_recovery_driver(req)

    def test_unsupported_layout(self):
        p = profile(self)
        with patch.object(p.sys, "version_info", (3, 13, 4)):
            with self.assertRaises(PersistenceError):
                p.recovery_requirements(readiness=readiness())

    def test_forged_nested_limits_never_runs_comparison_hooks(self):
        p = profile(self)
        req = p.recovery_requirements(readiness=readiness())

        class Hook:
            def __eq__(self, other):
                raise AssertionError("comparison hook")

        object.__setattr__(req.lifecycle_minimum, "result_bytes", Hook())
        with self.assertRaises(PersistenceError):
            p.verify_recovery_driver(req)

    def test_simulated313_verified_receipt_identity_and_stale_profile_refusal(self):
        from test_native_recovery_profile import simulated313

        p = profile(self)
        with patch.object(p.sys, "version_info", (3, 12, 3)):
            old = p.recovery_requirements(readiness=readiness())
        pg = SimpleNamespace(
            __version__="3.3.8", pq=SimpleNamespace(version=lambda: 180006, __impl__="binary")
        )
        with simulated313(p), patch.dict(sys.modules, {"psycopg": pg, "psycopg.pq": pg.pq}):
            req = p.recovery_requirements(readiness=readiness())
            result = p.verify_recovery_driver(req)
            self.assertEqual(result.interpreter_profile_id, req.interpreter_profile_id)
            self.assertIn(
                "/cpython-3.13.5-linux-x86_64-gil-release-recovery-v1/", result.supported_profile_id
            )
            with self.assertRaises(PersistenceError):
                p.verify_recovery_driver(old)
