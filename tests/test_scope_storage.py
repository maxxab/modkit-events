"""Synchronous pure NEW Scope controls; no package/driver imports or SQL proof."""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/modkit_events/persistence/scope.py"
scope_module = None
if SOURCE.exists():
    spec = importlib.util.spec_from_file_location("isolated_scope_candidate", SOURCE)
    scope_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scope_module
    spec.loader.exec_module(scope_module)

W = (
    9,
    10,
    11,
    12,
    13,
    28,
    29,
    30,
    31,
    32,
    133,
    160,
    5760,
    8192,
    8193,
    8194,
    8195,
    8196,
    8197,
    8198,
    8199,
    8200,
    8201,
    8202,
    8232,
    8233,
    8239,
    8287,
    12288,
)


class ScopeControls(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(scope_module, "NEW Scope seam is absent")
        self.m = scope_module

    def invalid(self, call):
        for ambient in (False, True):
            caught = None
            try:
                if ambient:
                    try:
                        raise RuntimeError("CALLER_SECRET")
                    except RuntimeError:
                        call()
                else:
                    call()
            except ValueError as error:
                caught = error
            self.assertIsNotNone(caught, "Invalid scope was admitted")
            self.assertIs(type(caught), ValueError)
            self.assertEqual(caught.args, ("Invalid scope",))
            self.assertIsNone(caught.__cause__)
            self.assertIsNone(caught.__context__)
            self.assertTrue(caught.__suppress_context__)
            self.assertEqual(caught.__dict__, {})

    def test_literal_golden_frames_and_optional_identity(self):
        cases = [
            (("a", None, None), b"MKSC\x01\x00\x01a\x00\x00"),
            (("\x00", None, None), b"MKSC\x01\x00\x01\x00\x00\x00"),
            (("a", "\x00", None), b"MKSC\x01\x00\x01a\x01\x00\x01\x00\x00"),
            (("a", None, "\x00"), b"MKSC\x01\x00\x01a\x00\x01\x00\x01\x00"),
            (("é", "t", "o"), b"MKSC\x01\x00\x02\xc3\xa9\x01\x00\x01t\x01\x00\x01o"),
        ]
        for values, frame in cases:
            with self.subTest(values=values):
                scope = self.m.Scope(*values)
                self.assertEqual(self.m.canonical_scope(scope), frame)
                self.assertEqual(self.m.decode_canonical_scope(frame), scope)
                self.assertEqual(
                    self.m.encode_scope_fields(scope),
                    tuple(None if v is None else v.encode("utf-8") for v in values),
                )

    def test_exact_maximum_nul_and_multibyte_bounds(self):
        scope = self.m.Scope("\x00" * 256, "\x00" * 256, "\x00" * 256)
        want = b"MKSC\x01\x01\x00" + b"\x00" * 256
        want += (b"\x01\x01\x00" + b"\x00" * 256) * 2
        self.assertEqual(len(want), 781)
        self.assertEqual(self.m.canonical_scope(scope), want)
        self.assertEqual(self.m.decode_canonical_scope(want), scope)
        self.invalid(lambda: self.m.decode_canonical_scope(want + b"x"))
        for good, bad in [("é" * 128, "é" * 128 + "a"), ("😀" * 64, "😀" * 65)]:
            self.assertEqual(self.m.decode_scope_fields(good.encode()), self.m.Scope(good))
            self.invalid(lambda: self.m.Scope(bad))

    def test_all_logical_fields_validate_types_blanks_encoding_and_bounds(self):
        class Text(str):
            pass

        for index in range(3):
            for bad in ("", " \t\n", "\ud800", "a" * 257, b"a", 1, True, Text("a")):
                values = ["app", "tenant", "owner"]
                values[index] = bad
                self.invalid(lambda: self.m.Scope(*values))
        self.invalid(lambda: self.m.Scope(None))

    def test_normative_whitespace_and_nonmembers_without_runtime_strip(self):
        for point in W:
            char = chr(point)
            self.invalid(lambda: self.m.Scope(char))
            scope = self.m.Scope(char + "a" + char)
            self.assertEqual(self.m.decode_canonical_scope(self.m.canonical_scope(scope)), scope)
            self.assertEqual(scope.application, char + "a" + char)
        for char in ("\x00", "\u180e", "\u200b", "\ufeff"):
            self.assertEqual(self.m.Scope(char).application, char)
        self.assertNotEqual(
            self.m.canonical_scope(self.m.Scope("é")),
            self.m.canonical_scope(self.m.Scope("e\u0301")),
        )

    def test_raw_projection_snapshots_and_memoryview_order(self):
        for make in (bytes, bytearray, memoryview):
            a, t, o = make(b"a\x00"), make(b" t "), make(b"\xc3\xa9")
            value = self.m.decode_scope_fields(a, t, o)
            self.assertEqual(value, self.m.Scope("a\x00", " t ", "é"))
            self.assertEqual(self.m.encode_scope_fields(value), (b"a\x00", b" t ", b"\xc3\xa9"))
            if make is bytearray:
                a[:] = t[:] = o[:] = b"changed"
                self.assertEqual(value, self.m.Scope("a\x00", " t ", "é"))
        backing = bytearray(b"aXbX")
        view = memoryview(backing)[::2]
        value = self.m.decode_scope_fields(view)
        backing[:] = b"xxxx"
        self.assertEqual(value.application, "ab")
        view.release()
        self.invalid(lambda: self.m.decode_scope_fields(view))

    def test_raw_projection_invalid_each_field(self):
        for index in range(3):
            for bad in (
                "a",
                b"",
                b" ",
                b"x" * 257,
                b"\xffSECRET",
                b"\xc3",
                b"\xc0\x80",
                b"\xed\xa0\x80",
                b"\xf4\x90\x80\x80",
                0,
                False,
            ):
                args = [b"a", b"t", b"o"]
                args[index] = bad
                self.invalid(lambda: self.m.decode_scope_fields(*args))
        self.invalid(lambda: self.m.decode_scope_fields(None))

    def test_malformed_frames_and_nonbytes_reject_without_chain(self):
        good = b"MKSC\x01\x00\x01a\x00\x00"
        bad = [good[:i] for i in range(len(good))]
        bad += [
            b"FAIL" + good[4:],
            b"MKSC\x02" + good[5:],
            b"MKSC\x01\x00\x00\x00\x00",
            b"MKSC\x01\x01\x01" + b"a" * 257 + b"\x00\x00",
            b"MKSC\x01\x00\x01a\x02\x00",
            b"MKSC\x01\x00\x01a\x00\x02",
            b"MKSC\x01\x00\x01a\x01\x00\x00\x00",
            b"MKSC\x01\x00\x01a\x00\x01\x00\x00",
            b"MKSC\x01\x00\x01\xff\x00\x00",
            good + b"extra",
            bytearray(good),
            memoryview(good),
            good.decode("latin1"),
            None,
        ]
        for raw in bad:
            self.invalid(lambda: self.m.decode_canonical_scope(raw))

    def test_frozen_scope_and_tampered_scope_revalidation(self):
        scope = self.m.Scope("a")
        with self.assertRaises(AttributeError):
            scope.application = "b"
        for field, bad in [("application", b"a"), ("tenant", ""), ("owner", "\ud800")]:
            scope = self.m.Scope("a")
            object.__setattr__(scope, field, bad)
            self.invalid(lambda: self.m.canonical_scope(scope))
            self.invalid(lambda: self.m.encode_scope_fields(scope))
        for other in (None, {}, ("a", None, None)):
            self.invalid(lambda: self.m.canonical_scope(other))
            self.invalid(lambda: self.m.encode_scope_fields(other))

    def test_baseexception_identity_is_not_sanitized(self):
        # Trace injection represents cancellation inside active validation wrappers,
        # without importing asyncio, creating a loop or probing resource traps.
        valid = self.m.Scope("a")
        sentinel = KeyboardInterrupt("cancellation")

        def inject(frame, event, arg):
            if (
                frame.f_code.co_filename == str(SOURCE)
                and frame.f_code.co_name == "_encode_field"
                and event == "line"
            ):
                raise sentinel
            return inject

        for call in (
            lambda: self.m.Scope("a"),
            lambda: self.m.canonical_scope(valid),
            lambda: self.m.encode_scope_fields(valid),
            lambda: self.m.decode_scope_fields(b"a"),
            lambda: self.m.decode_canonical_scope(b"MKSC\x01\x00\x01a\x00\x00"),
        ):
            caught = None
            try:
                sys.settrace(inject)
                call()
            except BaseException as error:
                caught = error
            finally:
                sys.settrace(None)
            self.assertIs(caught, sentinel)
