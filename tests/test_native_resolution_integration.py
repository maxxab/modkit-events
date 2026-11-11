"""Opt-in real E31 managed transport qualification source.

Not executed by source-only checks. Requires separately reviewed disposable schema,
least-privilege grants, SQL helpers and psycopg 3.3.8/libpq 180006 interpreter.
No installation, receipt seeding, fixture reset or DB access at import.
The killed-process cases lose APPLICATION acknowledgement, not a claimed
libpq COMMIT-response-loss fault injection. That latter gate remains separate.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve()
SOURCE = HERE.parents[1] / "src"
HELPERS = HERE.parent / "native"


def _helpers():
    sys.path.insert(0, str(HELPERS))
    import test_e31_resolution_sql_integration

    return test_e31_resolution_sql_integration


def _encode(value):
    from datetime import datetime
    from uuid import UUID

    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _child(request_path, mode):
    """One fresh normally initialized managed domain; never import old liabilities."""
    sys.path.insert(0, str(SOURCE))
    from modkit_events.persistence import managed_lifecycle as m
    from modkit_events.persistence import native_execution as e
    from modkit_events.persistence import native_sync as n
    from modkit_events.persistence.catalog import get_statement
    from modkit_events.persistence.ledger import ExecutionLedger

    request = _helpers()._load_request(Path(request_path))
    ledger = ExecutionLedger()
    m.configure_managed_registry(
        limits=m.LifecycleLimits(
            retained_cells=2,
            admitted_live=2,
            checkouts=2,
            roots=2,
            roots_per_checkout=1,
            executions=2,
            preparations=2,
            preparations_per_execution=2,
            prepare_bytes=8388608,
            prepare_bytes_per_execution=4194304,
            results=2,
            results_per_ticket=1,
            result_bytes=8388608,
            result_bytes_per_ticket=4194304,
            cleanup_bundles=2,
            cleanup_bytes=1024,
            construction_slots=4,
        ),
        execution_ledger=ledger,
    )
    execution = m.reserve_execution(ledger)
    actual = n.ManagedConnection.connect(
        os.environ["MODKIT_NATIVE_TEST_DSN"], execution_ledger=ledger
    )
    checkout = n.attach_native(actual, execution, execution_ledger=ledger)
    root = n.start_root(checkout, execution_ledger=ledger)

    a = e.prepare(execution, get_statement("E14"), (), execution_ledger=ledger, capacity=4096)
    t = m.admit(root, a, execution_ledger=ledger)
    b = m.reserve_result(t, 4096, execution_ledger=ledger)
    e.execute(t, b, execution_ledger=ledger)
    caller_root = str(m.read_result(b, execution_ledger=ledger))
    m.release_result(b, execution_ledger=ledger)
    m.release_ticket(t, execution_ledger=ledger)
    m.release_preparation(a, execution_ledger=ledger)

    args = dict(zip((p.name for p in get_statement("E31").parameters), request))
    a = e.prepare_resolution(execution, execution_ledger=ledger, capacity=4194304, **args)
    t = m.admit(root, a, execution_ledger=ledger)
    b = m.reserve_result(t, 4194304, execution_ledger=ledger)
    e.execute(t, b, execution_ledger=ledger)
    observation = m.read_result(b, execution_ledger=ledger)
    rendered = json.dumps(
        {
            "receipt": {
                name: _encode(getattr(observation, name))
                for name in observation.__dataclass_fields__
            },
            "caller_root": caller_root,
        }
    )
    observation = None  # Drop borrowed result alias before release.
    m.release_result(b, execution_ledger=ledger)
    m.release_ticket(t, execution_ledger=ledger)
    args = request = None
    m.release_preparation(a, execution_ledger=ledger)
    if mode == "staged_stop":
        print("ORACLE_READY " + mode, flush=True)
        # Parent kills this process: open root rolls back, no domain transfer.
        import signal

        signal.pause()
        raise AssertionError("unexpected resume")
    if mode == "rollback":
        end = n.rollback(root, execution_ledger=ledger)
        m.acknowledge_root_end(end, execution_ledger=ledger)
    else:
        end = n.commit(root, execution_ledger=ledger)
        assert (
            m.acknowledge_commit_result(end, execution_ledger=ledger) is m.CommitOutcome.COMMITTED
        )
    if mode == "committed_stop":
        print("ORACLE_READY " + mode, flush=True)
        import signal

        signal.pause()
        raise AssertionError("unexpected resume")
    m.release_root(root, execution_ledger=ledger)
    print(rendered, flush=True)
    # Process-local liabilities are never reset/imported/refunded by a successor.


_OUTPUT_LIMIT = 8 * 1024 * 1024
_RETAINED_CHILDREN = []


@contextmanager
def _retained_request_directory(*, prefix):
    """Independent invocation keeps its only request evidence even on failure."""
    directory = tempfile.mkdtemp(prefix=prefix)
    yield directory
    # Deliberately no implicit cleanup, on success or failure.


def _read_outputs(child):
    values = []
    for path in (child.stdout_path, child.stderr_path):
        with path.open("rb") as stream:
            value = stream.read(_OUTPUT_LIMIT + 1)
        if len(value) > _OUTPUT_LIMIT:
            raise RuntimeError("child output exceeds bounded diagnostic limit")
        values.append(value)
    return tuple(values)


def _retain_failure(child, error, stage):
    """Best-effort durable diagnostics never replace or erase the primary error."""
    if not any(item is child for item in _RETAINED_CHILDREN):
        _RETAINED_CHILDREN.append(child)
    record = dict(
        pid=child.pid,
        mode=child.mode,
        request_path=str(child.request_path),
        request_sha256=child.request_sha256,
        stdout_path=str(child.stdout_path),
        stderr_path=str(child.stderr_path),
        stage=stage,
        kill_attempted=child.kill_attempted,
        error_type=type(error).__name__,
        status="unresolved; no quiescence or cleanup claimed",
    )

    def diagnostic(value):
        if isinstance(value, bytes):
            return value[:4096].decode("utf-8", errors="replace")
        return str(value)[:4096] if value is not None else ""

    record["exception_stdout"] = diagnostic(getattr(error, "output", None))
    record["exception_stderr"] = diagnostic(getattr(error, "stderr", None))
    try:
        stdout, stderr = _read_outputs(child)
        record.update(stdout=diagnostic(stdout), stderr=diagnostic(stderr))
    except BaseException as diagnostic_error:
        record["output_capture_error"] = type(diagnostic_error).__name__
    note = "E31 child retained: " + json.dumps(record, sort_keys=True)
    try:
        error.add_note(note)
    except BaseException:
        pass
    try:
        child.stdout_path.with_name("failure.json").write_text(json.dumps(record, indent=2))
    except BaseException as diagnostic_error:
        try:
            error.add_note("retained diagnostic write failed: " + type(diagnostic_error).__name__)
        except BaseException:
            pass


def _spawn(path, mode):
    if mode not in ("commit", "rollback", "staged_stop", "committed_stop"):
        raise ValueError("unsupported child mode")
    path = Path(path).resolve()
    digest = hashlib.sha256()
    request_sha256 = None
    if path.exists():
        with path.open("rb") as request:
            for block in iter(lambda: request.read(65536), b""):
                digest.update(block)
        request_sha256 = digest.hexdigest()
    directory = Path(tempfile.mkdtemp(prefix="e31-child-", dir=path.parent))
    stdout_path, stderr_path = directory / "stdout.bin", directory / "stderr.bin"
    # Child inherits file descriptors; closing parent copies never closes a pipe
    # read end or sends SIGPIPE. These persistent files are not cleanup-owned.
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-B", str(HERE), "--issue", str(path), mode],
            stdout=stdout,
            stderr=stderr,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
    return SimpleNamespace(
        process=process,
        pid=process.pid,
        request_path=path,
        request_sha256=request_sha256,
        mode=mode,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        kill_attempted=False,
    )


def _collect(child, *, timeout):
    """Popen.communicate timeout does not kill; no Popen context manager."""
    child.process.communicate(timeout=timeout)
    return _read_outputs(child)


def _issue(path, mode="commit"):
    child = _spawn(path, mode)
    try:
        stdout, stderr = _collect(child, timeout=30)
        if child.process.returncode != 0 or stderr:
            raise AssertionError("child did not return a clean acknowledged result")
        return json.loads(stdout)
    except BaseException as error:
        _retain_failure(child, error, "issue")
        raise


def _kill_at_oracle(path, mode):
    if mode not in ("staged_stop", "committed_stop"):
        raise ValueError("deliberate kill requires an exact controlled stop mode")
    child = _spawn(path, mode)
    expected = ("ORACLE_READY " + mode + "\n").encode("ascii")
    try:
        deadline = time.monotonic() + 30
        while True:
            # Regular files never wait for a partial line to finish. Every read
            # is capped, and the monotonic deadline applies to partial output.
            stdout, stderr = _read_outputs(child)
            status = child.process.poll()
            if status is not None:
                raise RuntimeError("oracle child exited before a proven live boundary")
            if child.mode != mode or child.pid != child.process.pid:
                raise RuntimeError("spawned child identity or expected mode changed")
            if stderr or not expected.startswith(stdout):
                raise RuntimeError("wrong, extra or diagnostic oracle output")
            if time.monotonic() >= deadline:
                raise TimeoutError("complete exact oracle line not received before deadline")
            if stdout == expected:
                break
            time.sleep(0.02)
        # Only this branch authorizes one kill. Set before attempting it; any
        # kill/collection failure retains uncertainty and never retries.
        if child.kill_attempted:
            raise RuntimeError("controlled kill already attempted")
        child.kill_attempted = True
        child.process.kill()
        stdout, stderr = _collect(child, timeout=10)
        if child.process.returncode is None or child.process.returncode >= 0:
            raise RuntimeError("controlled kill termination is unconfirmed")
        if stdout != expected or stderr:
            raise RuntimeError("controlled kill collection changed oracle output")
    except BaseException as error:
        _retain_failure(child, error, "controlled-oracle")
        raise


@unittest.skipUnless(
    os.environ.get("MODKIT_NATIVE_TEST_DSN") and os.environ.get("MODKIT_E31_NATIVE_RELEASE") == "1",
    "requires separate exact-source isolated native release",
)
class NativeResolutionIntegration(unittest.TestCase):
    def test_both_kinds_all_outcomes_and_exact_fresh_process_repeat(self):
        h = _helpers()
        states = {
            "confirmed_success": "succeeded",
            "confirmed_rejection": "failed",
            "confirmed_cancelled": "cancelled",
            "safe_retry": "retry_waiting",
        }
        for kind in ("job", "inbox"):
            for outcome, state in states.items():
                with self.subTest(kind=kind, outcome=outcome), h.connect() as conn:
                    held = h.make_held(conn, kind)
                    retry = (
                        h._clock(conn) + timedelta(minutes=5) if outcome == "safe_retry" else None
                    )
                    request = h.resolution_request(held, outcome, retry_at=retry)
                    conn.commit()
                    with _retained_request_directory(prefix="e31-native-request-") as temp:
                        path = Path(temp) / "request.json"
                        h._persist_request(path, request)  # fsync file+directory before issuance.
                        first = _issue(path)
                        self.assertEqual(
                            str(first["receipt"]["resolution_root_xid"]), first["caller_root"]
                        )
                        seen = h.observe(conn, held["work_id"])
                        self.assertEqual(seen["state"], state)
                        self.assertEqual(seen["attempt_count"], held["attempt_count"])
                        self.assertEqual(seen["ownership_revision"], held["ownership_revision"] + 1)
                        if outcome != "safe_retry":
                            self.assertEqual(
                                str(seen["resolution_record_operation_id"]), str(request[5])
                            )
                        if kind == "job":
                            w02 = conn.execute(
                                "SELECT * FROM modkit_workers.w02(%s::uuid)", (held["work_id"],)
                            ).fetchone()
                            self.assertTrue(all(w02[k] == v for k, v in seen.items()))
                        stable = h.snapshot(conn, held["work_id"])
                        conn.commit()
                        repeated = _issue(path)
                        self.assertEqual(first["receipt"], repeated["receipt"])
                        self.assertNotEqual(first["caller_root"], repeated["caller_root"])
                        self.assertEqual(stable, h.snapshot(conn, held["work_id"]))
                        conn.commit()

    def test_explicit_rollback_has_no_durable_resolution(self):
        h = _helpers()
        for kind in ("job", "inbox"):
            with self.subTest(kind=kind), h.connect() as conn:
                held = h.make_held(conn, kind)
                before = h.snapshot(conn, held["work_id"])
                conn.commit()
                with _retained_request_directory(prefix="e31-native-rollback-") as temp:
                    path = Path(temp) / "request.json"
                    h._persist_request(path, h.resolution_request(held, "confirmed_success"))
                    _issue(path, "rollback")
                    self.assertEqual(before, h.snapshot(conn, held["work_id"]))
                    conn.commit()

    def test_process_death_loses_application_ack_committed_and_rolled_back(self):
        h = _helpers()
        for kind in ("job", "inbox"):
            for mode in ("staged_stop", "committed_stop"):
                with self.subTest(kind=kind, mode=mode), h.connect() as conn:
                    held = h.make_held(conn, kind)
                    before = h.snapshot(conn, held["work_id"])
                    conn.commit()
                    with _retained_request_directory(prefix="e31-native-unknown-") as temp:
                        path = Path(temp) / "request.json"
                        request = h.resolution_request(held, "confirmed_success")
                        h._persist_request(path, request)
                        _kill_at_oracle(path, mode)
                        after = h.snapshot(conn, held["work_id"])
                        if mode == "staged_stop":
                            self.assertEqual(before, after)
                        else:
                            self.assertEqual(len(after["receipts"]), len(before["receipts"]) + 1)
                        conn.commit()
                        recovered = _issue(path)  # Same exact persisted request, new active domain.
                        receipt = h.call_e31(conn, request)
                        receipt["resolution_root_xid"] = int(receipt["resolution_root_xid"])
                        self.assertEqual(
                            recovered["receipt"], {k: _encode(v) for k, v in receipt.items()}
                        )
                        stable = h.snapshot(conn, held["work_id"])
                        conn.commit()
                        self.assertEqual(_issue(path)["receipt"], recovered["receipt"])
                        self.assertEqual(h.snapshot(conn, held["work_id"]), stable)
                        conn.commit()

    def test_missing_exact_request_never_reconstructs_or_issues(self):
        with _retained_request_directory(prefix="e31-native-missing-") as temp:
            child = _spawn(Path(temp) / "absent.json", "commit")
            try:
                stdout, stderr = _collect(child, timeout=15)
            except BaseException as error:
                _retain_failure(child, error, "missing-request-control")
                raise
            self.assertNotEqual(child.process.returncode, 0)
            self.assertFalse(stdout)
            self.assertIn(b"FileNotFoundError", stderr)


class NativeRetentionControls(unittest.TestCase):
    """Connection-free mocks only; never launch an OS child or connect to DB."""

    def setUp(self):
        from unittest.mock import patch

        guard = patch(
            __name__ + ".subprocess.Popen",
            side_effect=AssertionError("real child forbidden in pure controls"),
        )
        guard.start()
        self.addCleanup(guard.stop)

    def fake(self, mode="staged_stop"):
        from types import SimpleNamespace
        from unittest.mock import Mock

        process = Mock()
        process.pid = 4317
        process.poll.return_value = None
        process.returncode = -9
        process.communicate.return_value = (None, None)
        return SimpleNamespace(
            process=process,
            pid=4317,
            request_path=Path("/retained/request.json"),
            request_sha256="a" * 64,
            mode=mode,
            stdout_path=Path("/retained/stdout"),
            stderr_path=Path("/retained/stderr"),
            kill_attempted=False,
        )

    def patches(self, child, outputs):
        from contextlib import ExitStack
        from unittest.mock import patch

        stack = ExitStack()
        stack.enter_context(patch(__name__ + "._spawn", return_value=child))
        stack.enter_context(patch(__name__ + "._read_outputs", side_effect=outputs))
        stack.enter_context(patch(__name__ + "._retain_failure"))
        stack.enter_context(patch(__name__ + ".time.sleep"))
        return stack

    def test_unproven_oracle_never_killed(self):
        from unittest.mock import patch

        for output in (
            (b"", b""),
            (b"ORACLE_READY staged_stop", b""),
            (b"WRONG\n", b""),
            (b"ORACLE_READY committed_stop\n", b""),
            (b"ORACLE_READY staged_stop\nextra", b""),
            (b"ORACLE_READY staged_stop\n", b"error"),
        ):
            with self.subTest(output=output):
                child = self.fake()
                with (
                    self.patches(child, [output] * 3),
                    patch(__name__ + ".time.monotonic", side_effect=[0, 31, 32]),
                ):
                    with self.assertRaises(BaseException):
                        _kill_at_oracle(child.request_path, child.mode)
                child.process.kill.assert_not_called()
                child.process.terminate.assert_not_called()
                child.process.communicate.assert_not_called()

    def test_eof_read_and_status_errors_never_killed(self):
        for failure in ("eof", "read", "status"):
            with self.subTest(failure=failure):
                child = self.fake()
                if failure == "eof":
                    child.process.poll.return_value = 0
                if failure == "status":
                    child.process.poll.side_effect = OSError("status")
                outputs = [OSError("read")] if failure == "read" else [(b"", b"")]
                with self.patches(child, outputs):
                    with self.assertRaises(BaseException):
                        _kill_at_oracle(child.request_path, child.mode)
                child.process.kill.assert_not_called()
                child.process.terminate.assert_not_called()

    def test_complete_expected_oracle_allows_exactly_one_kill(self):
        for mode in ("staged_stop", "committed_stop"):
            child = self.fake(mode)
            line = ("ORACLE_READY " + mode + "\n").encode()
            with self.patches(child, [(line, b""), (line, b"")]):
                _kill_at_oracle(child.request_path, mode)
            child.process.kill.assert_called_once_with()
            child.process.communicate.assert_called_once_with(timeout=10)
            child.process.terminate.assert_not_called()
            self.assertTrue(child.kill_attempted)

    def test_authorized_kill_collection_timeout_never_kills_twice(self):
        child = self.fake()
        error = subprocess.TimeoutExpired("child", 10, output=b"partial", stderr=b"err")
        child.process.communicate.side_effect = error
        with self.patches(child, [(b"ORACLE_READY staged_stop\n", b"")]):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                _kill_at_oracle(child.request_path, child.mode)
        self.assertIs(caught.exception, error)
        child.process.kill.assert_called_once_with()
        child.process.terminate.assert_not_called()

    def test_issue_timeout_preserves_original_without_cleanup(self):
        child = self.fake("commit")
        error = subprocess.TimeoutExpired("child", 30, output=b"partial")
        child.process.communicate.side_effect = error
        with self.patches(child, []):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                _issue(child.request_path)
        self.assertIs(caught.exception, error)
        child.process.kill.assert_not_called()
        child.process.terminate.assert_not_called()
        child.process.wait.assert_not_called()

    def test_issue_zero_nonzero_and_malformed_output(self):
        for code, output, success in [
            (0, b'{"receipt":{}}', True),
            (1, b"bad", False),
            (0, b"partial", False),
        ]:
            child = self.fake("commit")
            child.process.returncode = code
            with self.patches(child, [(output, b"")]):
                if success:
                    self.assertEqual(_issue(child.request_path), {"receipt": {}})
                else:
                    with self.assertRaises(BaseException):
                        _issue(child.request_path)
            child.process.kill.assert_not_called()
            child.process.terminate.assert_not_called()

    def test_diagnostics_preserve_provenance_and_original_failure(self):
        from unittest.mock import patch

        child = self.fake("commit")
        primary = subprocess.TimeoutExpired("child", 30, output=b"partial", stderr=b"diagnostic")
        with (
            patch(__name__ + "._read_outputs", return_value=(b"file partial", b"file stderr")),
            patch.object(Path, "write_text") as write,
        ):
            _retain_failure(child, primary, "issue")
        payload = json.loads(write.call_args.args[0])
        self.assertEqual(payload["pid"], 4317)
        self.assertEqual(payload["request_path"], str(child.request_path))
        self.assertEqual(payload["request_sha256"], "a" * 64)
        self.assertEqual(payload["mode"], "commit")
        self.assertIn(child, _RETAINED_CHILDREN)
        self.assertIn("file partial", payload["stdout"])
        self.assertIn("partial", payload["exception_stdout"])
        self.assertTrue(primary.__notes__)
        with (
            patch(__name__ + "._read_outputs", side_effect=OSError("read diagnostics")),
            patch.object(Path, "write_text", side_effect=OSError("write diagnostics")),
        ):
            _retain_failure(child, primary, "issue")
        child.process.kill.assert_not_called()
        child.process.terminate.assert_not_called()

    def test_requests_and_spawn_output_are_never_temporary_cleanup_owned(self):
        import ast

        tree = ast.parse(Path(__file__).read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        self.assertFalse(
            any(
                isinstance(n.func, ast.Attribute) and n.func.attr == "TemporaryDirectory"
                for n in calls
            )
        )
        self.assertFalse(
            any(isinstance(n.func, ast.Attribute) and n.func.attr == "readline" for n in calls)
        )

    def test_unproven_boundary_does_not_trigger_old_finally_kill(self):
        from unittest.mock import Mock, patch

        child = self.fake()
        child.kill = child.process.kill
        child.communicate = child.process.communicate
        child.stdout = Mock()
        with (
            patch(__name__ + "._spawn", return_value=child),
            patch("selectors.DefaultSelector") as selector,
            patch(__name__ + "._read_outputs", side_effect=OSError("read fault"), create=True),
            patch(__name__ + "._retain_failure", create=True),
        ):
            selector.return_value.__enter__.return_value.select.return_value = []
            with self.assertRaises(BaseException):
                _kill_at_oracle(child.request_path, child.mode)
        child.process.kill.assert_not_called()

    def test_complete_oracle_after_deadline_is_not_kill_authority(self):
        from unittest.mock import patch

        child = self.fake()
        with (
            self.patches(child, [(b"ORACLE_READY staged_stop\n", b"")] * 2),
            patch(__name__ + ".time.monotonic", side_effect=[0, 31]),
        ):
            with self.assertRaises(TimeoutError):
                _kill_at_oracle(child.request_path, child.mode)
        child.process.kill.assert_not_called()

    def test_kill_error_is_not_retried_or_collected(self):
        child = self.fake()
        primary = OSError("kill outcome uncertain")
        child.process.kill.side_effect = primary
        with self.patches(child, [(b"ORACLE_READY staged_stop\n", b"")]):
            with self.assertRaises(OSError) as caught:
                _kill_at_oracle(child.request_path, child.mode)
        self.assertIs(caught.exception, primary)
        child.process.kill.assert_called_once_with()
        child.process.communicate.assert_not_called()
        child.process.terminate.assert_not_called()

    def test_changed_identity_or_mode_has_no_kill_authority(self):
        for field in ("pid", "mode"):
            child = self.fake()
            setattr(child, field, 99 if field == "pid" else "committed_stop")
            with self.patches(child, [(b"ORACLE_READY staged_stop\n", b"")]):
                with self.assertRaises(RuntimeError):
                    _kill_at_oracle(child.request_path, "staged_stop")
            child.process.kill.assert_not_called()

    def test_issue_read_error_and_nontermination_preserve_original(self):
        for failure in ("read", "communicate"):
            child = self.fake("commit")
            primary = OSError("retained")
            if failure == "communicate":
                child.process.communicate.side_effect = primary
            with self.patches(child, [primary]):
                with self.assertRaises(OSError) as caught:
                    _issue(child.request_path)
            self.assertIs(caught.exception, primary)
            child.process.kill.assert_not_called()
            child.process.terminate.assert_not_called()
            child.process.wait.assert_not_called()

    def test_spawn_uses_files_and_request_directories_never_cleanup(self):
        from unittest.mock import Mock, mock_open, patch

        process = Mock(pid=4317)
        with (
            patch.object(Path, "resolve", return_value=Path("/retained/request.json")),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "open", mock_open()),
            patch(__name__ + ".tempfile.mkdtemp", return_value="/retained/child"),
            patch(__name__ + ".subprocess.Popen", return_value=process) as spawn,
        ):
            child = _spawn(Path("/retained/request.json"), "commit")
        self.assertIs(child.process, process)
        self.assertNotEqual(spawn.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertNotEqual(spawn.call_args.kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(child.request_path, Path("/retained/request.json"))
        with patch(__name__ + ".tempfile.mkdtemp", return_value="/retained/request"):
            with self.assertRaises(RuntimeError):
                with _retained_request_directory(prefix="control-") as directory:
                    self.assertEqual(directory, "/retained/request")
                    raise RuntimeError("preserve request provenance")

    def test_clock_failure_retains_without_kill(self):
        from unittest.mock import patch

        child = self.fake()
        primary = OSError("clock")
        with (
            self.patches(child, []),
            patch(__name__ + ".time.monotonic", side_effect=primary),
            patch(__name__ + "._retain_failure") as retain,
        ):
            with self.assertRaises(OSError) as caught:
                _kill_at_oracle(child.request_path, child.mode)
        self.assertIs(caught.exception, primary)
        retain.assert_called_once_with(child, primary, "controlled-oracle")
        child.process.kill.assert_not_called()

    def test_postkill_uncertainty_never_authorizes_second_kill(self):
        line = b"ORACLE_READY staged_stop\n"
        for status, output in (
            (None, (line, b"")),
            (0, (line, b"")),
            (-9, (line, b"stderr")),
            (-9, (b"changed", b"")),
        ):
            child = self.fake()
            child.process.returncode = status
            with self.patches(child, [(line, b""), output]):
                with self.assertRaises(RuntimeError):
                    _kill_at_oracle(child.request_path, child.mode)
            child.process.kill.assert_called_once_with()
            child.process.terminate.assert_not_called()
            child.process.communicate.assert_called_once_with(timeout=10)

    def test_file_reads_have_fixed_caps_and_reject_oversize(self):
        from unittest.mock import mock_open, patch

        child = self.fake()
        for raw, oversized in ((b"partial", False), (b"x" * (_OUTPUT_LIMIT + 1), True)):
            stream = mock_open(read_data=raw)
            with patch.object(Path, "open", stream):
                if oversized:
                    with self.assertRaises(RuntimeError):
                        _read_outputs(child)
                else:
                    self.assertEqual(_read_outputs(child), (raw, raw))
            self.assertTrue(
                all(call.args == (_OUTPUT_LIMIT + 1,) for call in stream().read.call_args_list)
            )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--issue":
        if os.environ.get("MODKIT_E31_NATIVE_RELEASE") != "1":
            raise SystemExit("separate native release required")
        _child(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
