"""Opt-in SQL behavior checks, not managed-native transport qualification.

Requires separately reviewed disposable schema/grants including Workers W01/W05.
No install, receipt seeding, schema reset, services, or connection on import.
MODKIT_NATIVE_TEST_DSN enables tests. Helpers explicitly commit fixture stages.
Jobs retain canonical jobs namespace with unique command/key; inbox scopes are unique.
Raw scans use validated exact-target predecessor cursors with full bounded scope evidence.
Runtime approval remains separate from authoring this file.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

PARAM_TYPES = (
    "uuid",
    "int8",
    "int4",
    "int4",
    "uuid",
    "uuid",
    "text",
    "timestamptz",
    "bytea",
    "bytea",
    "bytea",
)


def connect(dsn=None):
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(dsn or os.environ["MODKIT_NATIVE_TEST_DSN"], row_factory=dict_row)
    conn.execute("SET statement_timeout='20s'")
    conn.execute("SET lock_timeout='15s'")
    conn.commit()
    return conn


def _call(conn, name, values, types):
    assert name in (
        "modkit_events.e01",
        "modkit_events.e03",
        "modkit_events.e04",
        "modkit_events.e06",
        "modkit_events.e12",
        "modkit_events.e32",
        "modkit_events.e31",
        "modkit_events.e02",
        "modkit_events.e22",
        "modkit_events.e24",
        "modkit_events.e25",
        "modkit_events.e27",
        "modkit_events.e08",
        "modkit_events.e10",
        "modkit_events.e13",
        "modkit_workers.w01",
        "modkit_workers.w05",
    )
    casts = ",".join("%s::pg_catalog." + value for value in types)
    return conn.execute("SELECT * FROM " + name + "(" + casts + ")", values).fetchall()


def observe(conn, work_id):
    rows = conn.execute("SELECT * FROM modkit_events.e15(%s::uuid)", (work_id,)).fetchall()
    assert len(rows) == 1
    return rows[0]


def _frame(tag, fields):
    def field(raw):
        return len(raw).to_bytes(8, "big") + raw

    return b"MKPF\x01" + field(tag) + len(fields).to_bytes(4, "big") + b"".join(map(field, fields))


def _optional(raw):
    return b"0" if raw is None else b"1" + len(raw).to_bytes(8, "big") + raw


def _instant(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ").encode()


def _clock(conn):
    return conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]


def _fixture_identity(kind, work_id):
    assert kind in ("job", "inbox") and type(work_id) is UUID
    unique = ("e31_" + work_id.hex).encode()
    namespace = b"jobs" if kind == "job" else unique
    return namespace, None if kind == "job" else namespace, unique, unique


def _target_scan_after(work):
    target = work["work_id"]
    assert type(target) is UUID and target.int > 0
    # PostgreSQL UUID order is unsigned byte order. No UUID fits this open gap.
    return UUID(int=target.int - 1)


def _validate_raw_scan(raw, work, after):
    assert 1 <= len(raw) <= 256, "raw fixture identity bound exceeded or target missing"
    ids = [row["work_id"] for row in raw]
    assert all(type(value) is UUID for value in ids)
    assert ids == sorted(set(ids)), "raw identities must be complete ordered unique rows"
    assert after == _target_scan_after(work)
    assert all(row["namespace"] == work["namespace"] and row["kind"] == work["kind"] for row in raw)
    target = [row for row in raw if row["work_id"] == work["work_id"]]
    assert len(target) == 1 and target[0]["command_type"] == work["command_type"]
    assert [value for value in ids if value > after][:1] == [work["work_id"]]
    return raw


def _record_raw_scan(conn, work, after):
    # Read ALL raw identities in the scope, including earlier terminal and live
    # incompatible rows. This bounded evidence does not filter them away.
    raw = conn.execute(
        "SELECT work_id,kind,namespace,command_type,state FROM modkit_events.work "
        "WHERE namespace=%s AND kind=%s ORDER BY work_id LIMIT 257",
        (work["namespace"], work["kind"]),
    ).fetchall()
    _validate_raw_scan(raw, work, after)
    print(
        json.dumps(
            {
                "e31_raw_scan": [
                    {
                        "work_id": str(row["work_id"]),
                        "kind": row["kind"],
                        "namespace_hex": row["namespace"].hex(),
                        "command_type_hex": row["command_type"].hex(),
                        "state": row["state"],
                    }
                    for row in raw
                ],
                "scan_after": str(after),
                "target": str(work["work_id"]),
                "limit": 1,
                "discovery_budget": 1,
            }
        ),
        flush=True,
    )


def _check_target_page(rows, work, *, expected_items):
    assert expected_items in (0, 1) and len(rows) == 1 + expected_items
    header = rows[0]
    assert header["record_type"] == "header"
    assert type(header["visited"]) is int and header["visited"] == 1
    assert header["next_cursor"] == work["work_id"] and header["pass_exhausted"] is False
    assert all(
        value is None
        for key, value in header.items()
        if key not in ("record_type", "visited", "next_cursor", "pass_exhausted")
    )
    items = rows[1:]
    for row in items:
        assert row["record_type"] == "item" and row["work_id"] == work["work_id"]
        assert all(row[key] is None for key in ("visited", "next_cursor", "pass_exhausted"))
    return items


def claim_dispatch(conn, work):
    """Explicitly commits claim then dispatch; usable after a lawful safe retry."""
    after = _target_scan_after(work)
    _record_raw_scan(conn, work, after)
    values = (work["namespace"], [work["command_type"]], [1], 1, 600.0, after, 1, 16777216)
    types = ("bytea", "bytea[]", "int4[]", "int4", "float8", "uuid", "int4", "int8")
    if work["kind"] == "job":
        rows = _call(conn, "modkit_workers.w05", values, types)
    else:
        rows = _call(
            conn,
            "modkit_events.e04",
            (values[0], "inbox") + values[1:],
            (types[0], "text") + types[1:],
        )
    items = _check_target_page(rows, work, expected_items=1)
    claimed = items[0]
    conn.commit()
    _call(
        conn,
        "modkit_events.e06",
        (
            claimed["work_id"],
            claimed["token"],
            claimed["ownership_revision"],
            claimed["cycle"],
            claimed["attempt_count"],
            uuid4(),
            b"test_effect",
            b"test_request",
            None,
        ),
        ("uuid", "uuid", "int8", "int4", "int4", "uuid", "bytea", "bytea", "bytea"),
    )
    conn.commit()
    running = observe(conn, work["work_id"])
    conn.commit()
    return running


def _admission_fields(work_id, kind, now, *, replay_policy, max_attempts, deadline):
    """Pure fixture byte construction shared by real admission and static checks."""
    assert kind in ("job", "inbox")
    namespace, subscription, command_type, identity_key = _fixture_identity(kind, work_id)
    available = now - timedelta(seconds=1)
    empty = b"o\0\0\0\0"
    scope = b"MKSC\1\0\3app\0\0"
    protected = _frame(
        b"protected-binding", (b"absent", b"0", b"0", b"0", b"retain", b"0", b"0", b"", b"", empty)
    )
    event_id = identity_key
    envelope = _frame(b"event-envelope", (event_id, command_type, b"1", empty, empty))
    event_replay = json.dumps(
        dict(
            event_id=event_id.decode(),
            name=command_type.decode(),
            schema_version=1,
            payload={},
            metadata={},
        ),
        separators=(",", ":"),
    ).encode()
    semantic = empty if kind == "job" else envelope
    replay = b"{}" if kind == "job" else event_replay
    intent = _frame(
        b"work-intent",
        (
            kind.encode(),
            _optional(subscription),
            namespace,
            command_type,
            b"1",
            b"1",
            scope,
            _optional(identity_key),
            semantic,
            protected,
            replay_policy.encode(),
            str(max_attempts).encode(),
            _optional(None if deadline is None else _instant(deadline)),
            _instant(available),
        ),
    )
    values = (
        work_id,
        kind,
        subscription,
        namespace,
        command_type,
        scope,
        identity_key,
        1,
        b"1",
        b"app",
        None,
        None,
        intent,
        semantic,
        replay,
        protected,
        replay_policy,
        max_attempts,
        deadline,
        available,
    )
    types = (
        "uuid",
        "text",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "int4",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "bytea",
        "text",
        "int4",
        "timestamptz",
        "timestamptz",
    )
    return values, types, event_id, envelope, event_replay


def _make_running(conn, kind, *, replay_policy="application_safe", max_attempts=3, deadline=None):
    """Lawful W01/E03 → W05/E04 → committed E06 → E32/E12; never direct work DML.

    Application oracle: this test never performs the represented external effect.
    A separate rolled-back business root is affirmative fixture evidence, not a
    general rule that missing database/provider success means safe retry.
    """
    work_id = uuid4()
    values, types, event_id, envelope, event_replay = _admission_fields(
        work_id,
        kind,
        _clock(conn),
        replay_policy=replay_policy,
        max_attempts=max_attempts,
        deadline=deadline,
    )
    subscription, namespace = values[2], values[3]
    empty = bytes((111, 0, 0, 0, 0))
    if kind == "job":
        rows = _call(
            conn,
            "modkit_workers.w01",
            values + ("absent", None, None, None, None, None, b"", "retain", empty),
            types
            + ("text", "bytea", "bytea", "bytea", "bytea", "timestamptz", "bytea", "text", "bytea"),
        )
    else:
        _call(
            conn,
            "modkit_events.e01",
            (subscription, b"test_manifest", namespace, 4),
            ("bytea", "bytea", "bytea", "int4"),
        )
        rows = _call(
            conn,
            "modkit_events.e03",
            values + (event_id, 1, envelope, event_replay, True, b"broker", b"transport"),
            types + ("bytea", "int4", "bytea", "bytea", "bool", "bytea", "bytea"),
        )
    assert len(rows) == 1 and rows[0]["inserted"]
    conn.commit()
    running = claim_dispatch(conn, observe(conn, work_id))
    return running


def make_held(
    conn,
    kind,
    *,
    cancellation=False,
    replay_policy="application_safe",
    max_attempts=3,
    deadline=None,
):
    """Lawful helper; commits admission, claim, dispatch and explicit holding."""
    running = _make_running(
        conn, kind, replay_policy=replay_policy, max_attempts=max_attempts, deadline=deadline
    )
    work_id = running["work_id"]
    if cancellation:
        _call(
            conn,
            "modkit_events.e12",
            (work_id, None, None, "test_cancel"),
            ("uuid", "uuid", "int8", "text"),
        )
    else:
        failed = conn.execute("SELECT pg_current_xact_id()::text AS xid").fetchone()["xid"]
        conn.rollback()
        _call(
            conn,
            "modkit_events.e32",
            (
                work_id,
                running["token"],
                running["ownership_revision"],
                1,
                running["attempt_count"],
                failed,
                uuid4(),
                "test_uncertain",
                b"oracle_no_effect",
                b"test",
            ),
            ("uuid", "uuid", "int8", "int4", "int4", "xid8", "uuid", "text", "bytea", "bytea"),
        )
    conn.commit()
    held = observe(conn, work_id)
    assert held["state"] == "held"
    conn.commit()
    return held


def resolution_request(
    held,
    outcome,
    *,
    operation_id=None,
    retry_at=None,
    result=None,
    evidence=b"confirmed_test_oracle",
    binding=b"authorized_test_scope",
):
    if outcome == "confirmed_success" and result is None:
        result = b"test_result"
    if outcome == "safe_retry" and retry_at is None:
        raise ValueError("safe_retry caller must supply explicit database-derived retry_at")
    return (
        held["work_id"],
        held["ownership_revision"],
        held["cycle"],
        held["attempt_count"],
        held["dispatch_id"],
        operation_id or uuid4(),
        outcome,
        retry_at,
        result,
        evidence,
        binding,
    )


def call_e31(conn, request):
    rows = _call(conn, "modkit_events.e31", request, PARAM_TYPES)
    assert len(rows) == 1 and len(rows[0]) == 16
    return rows[0]


def snapshot(conn, work_id):
    """Exact durable state (sequence gaps deliberately excluded)."""
    queries = {
        "work": "SELECT * FROM modkit_events.work WHERE work_id=%s",
        "attempts": "SELECT * FROM modkit_events.attempts WHERE work_id=%s ORDER BY cycle,attempt",
        "history": "SELECT * FROM modkit_events.work_history WHERE work_id=%s ORDER BY history_id",
        "receipts": "SELECT * FROM modkit_events.mutation_operations WHERE work_id=%s ORDER BY operation_id",
        "parent": "SELECT s.* FROM modkit_events.subscriptions s JOIN modkit_events.work w USING(subscription_id) WHERE w.work_id=%s",
        "job": "SELECT * FROM modkit_events.job_payloads WHERE job_work_id=%s",
        "inbox": "SELECT * FROM modkit_events.inbox WHERE work_id=%s",
    }
    return {key: conn.execute(sql, (work_id,)).fetchall() for key, sql in queries.items()}


def _wait_for_lock(observer, pid, expected_blocker_pid, thread, result, timeout=5):
    """Prove this exact blocker within the deadline; retain bounded raw observations."""
    started = time.monotonic()
    until = started + timeout
    evidence = {
        "contender_pid": pid,
        "expected_blocker_pid": expected_blocker_pid,
        "timeout": timeout,
        "samples": [],
        "sample_count": 0,
        "status": "pending",
    }
    try:
        while time.monotonic() < until:
            if not thread.is_alive() or result:
                raise AssertionError("contender completed before verified blocker observation")
            row = observer.execute(
                "SELECT pg_blocking_pids(%s) AS blockers, "
                "session_user::text AS session_user, current_user::text AS current_user",
                (pid,),
            ).fetchone()
            elapsed = time.monotonic() - started
            evidence["samples"].append({"elapsed": elapsed, "row": row})
            evidence["sample_count"] += 1
            # Retain a bounded tail; count explicitly exposes discarded earlier samples.
            del evidence["samples"][:-128]
            if elapsed >= timeout:
                raise AssertionError("blocker observation exceeded deadline")
            if not thread.is_alive() or result:
                raise AssertionError("contender completed during blocker observation")
            if (
                not row
                or not isinstance(row.get("blockers"), list)
                or any(type(value) is not int for value in row["blockers"])
            ):
                raise AssertionError("invalid blocker observation")
            if expected_blocker_pid in row["blockers"]:
                evidence["status"] = "verified"
                return evidence
            time.sleep(0.01)  # Polling only; exact database blocker proves ordering.
        raise AssertionError("expected blocker not observed before deadline")
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["error"] = repr(exc)
        exc.lock_observation = evidence
        raise
    finally:
        evidence["contender_alive"] = thread.is_alive()
        evidence["contender_result"] = dict(result)
        evidence["contender_error"] = getattr(thread, "e31_error", None)
        print("E31_LOCK_OBSERVATION " + json.dumps(evidence, default=str), flush=True)


def _run_lock_contender(contender, request, result, success_key, expected_sqlstate):
    """Publish only acknowledged outcomes; retain exact failed disposition evidence."""
    thread = threading.current_thread()
    outcome = {
        "status": "pending",
        "stage": "statement",
        "request": request,
        "contender_pid": contender.info.backend_pid,
        "errors": [],
        "expected_sqlstate": expected_sqlstate,
    }
    thread.e31_outcome = outcome
    try:
        row = call_e31(contender, request)
        outcome["returned_row"] = row
        outcome["stage"] = "commit"
        contender.commit()
    except BaseException as exc:
        stage = outcome["stage"]
        outcome["primary_error"] = exc
        thread.e31_error = repr(exc)
        outcome["stage"] = "rollback"
        try:
            contender.rollback()
            outcome["rollback"] = "acknowledged"
        except BaseException as rollback_error:
            outcome["rollback"] = "uncertain"
            outcome["rollback_error"] = rollback_error
            outcome["errors"] = [exc, rollback_error]
            outcome["status"] = "commit_uncertain" if stage == "commit" else "rollback_uncertain"
            return
        if stage == "commit":
            outcome["status"] = "commit_uncertain"
            outcome["errors"] = [exc]
        elif expected_sqlstate is not None and getattr(exc, "sqlstate", None) == expected_sqlstate:
            outcome["status"] = "sql_error_rollback_acknowledged"
            result["sqlstate"] = expected_sqlstate
        else:
            outcome["status"] = "unexpected_statement_error"
            outcome["errors"] = [exc]
        return
    outcome["stage"] = "completed"
    outcome["status"] = "commit_acknowledged"
    result[success_key] = row


def _finalize_lock_race(holder, thread, result, contender_pid, original_error=None):
    """Dispose only the test-owned blocker; join without signals and retain failures."""
    evidence = {
        "contender_pid": contender_pid,
        "blocker_pid": holder.info.backend_pid,
        "original_error": repr(original_error) if original_error is not None else None,
        "rollback": "attempted",
        "join": "not_attempted",
    }
    failures = []
    try:
        holder.rollback()
        evidence["rollback"] = "succeeded"
    except BaseException as exc:
        evidence["rollback"] = "failed"
        evidence["rollback_error"] = repr(exc)
        failures.append(exc)
    # Even an uncertain rollback does not authorize a retry or a signal.
    evidence["join"] = "attempted"
    try:
        thread.join(22)
        evidence["join"] = "returned"
    except BaseException as exc:
        evidence["join"] = "failed"
        evidence["join_error"] = repr(exc)
        failures.append(exc)
    try:
        evidence["alive"] = thread.is_alive()
        if evidence["alive"]:
            failures.append(AssertionError("contender remains alive after bounded join"))
    except BaseException as exc:
        evidence["alive"] = None
        evidence["liveness_error"] = repr(exc)
        failures.append(exc)
    outcome = thread.__dict__.get("e31_outcome")
    evidence["contender_outcome"] = outcome
    if not isinstance(outcome, dict):
        failures.append(AssertionError("contender has no acknowledged disposition"))
    else:
        failures.extend(outcome.get("errors", []))
        if outcome.get("status") not in (
            "commit_acknowledged",
            "sql_error_rollback_acknowledged",
        ) and not outcome.get("errors"):
            failures.append(AssertionError("contender disposition incomplete"))
    evidence["result"] = dict(result)
    evidence["error"] = getattr(thread, "e31_error", None)
    if original_error is not None:
        original_error.race_finalization = evidence
    try:
        print("E31_CONTENDER_AFTER_FINALIZER " + json.dumps(evidence, default=str), flush=True)
    except BaseException as exc:
        evidence["emission_error"] = repr(exc)
        failures.append(exc)
    if failures:
        errors = ([original_error] if original_error is not None else []) + failures
        combined = BaseExceptionGroup(
            "E31 race finalization failed; state may be uncertain", errors
        )
        combined.race_finalization = evidence
        raise combined from original_error
    return evidence


def _persist_request(path, request):
    def encode(value):
        if isinstance(value, UUID):
            return {"uuid": str(value)}
        if isinstance(value, datetime):
            return {"instant": value.isoformat()}
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        return value

    with path.open("x", encoding="utf-8") as stream:
        json.dump([encode(value) for value in request], stream)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_request(path):
    def decode(value):
        if type(value) is dict:
            if "uuid" in value:
                return UUID(value["uuid"])
            if "instant" in value:
                return datetime.fromisoformat(value["instant"])
            return bytes.fromhex(value["bytes"])
        return value

    return tuple(map(decode, json.loads(path.read_text())))


# Keep unresolved Popen objects reachable; no destructor-driven cleanup policy.
_RETAINED_ACK_CHILDREN = []
_CHILD_DIAGNOSTIC_LIMIT = 65536


def _child_output(path):
    with path.open("rb") as stream:
        raw = stream.read(_CHILD_DIAGNOSTIC_LIMIT + 1)
    return raw[:_CHILD_DIAGNOSTIC_LIMIT], len(raw) > _CHILD_DIAGNOSTIC_LIMIT


def _save_child_status(path, status):
    # One small evidence record; output reads are capped, files remain untouched.
    with path.open("w", encoding="utf-8") as stream:
        json.dump(status, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def _run_retained_child(argv, request_path, *, committed, timeout=25, popen=None):
    """Collect once, retain process/files on failure, never kill/retry/cleanup.

    Regular files avoid a pipe-close SIGPIPE on parent teardown. Diagnostic reads
    are bounded; output files are not truncated and no live-child survival claim
    is made about unrelated OS/session shutdown. Caller owns later disposition.
    """
    request_path = Path(request_path).resolve()
    request = _load_request(request_path)
    status_path = request_path.parent / "child-status.json"
    stdout_path, stderr_path = (
        request_path.parent / "child.stdout",
        request_path.parent / "child.stderr",
    )
    status = dict(
        mode="after_commit" if committed else "before_commit",
        request_path=str(request_path),
        work_id=str(request[0]),
        operation_id=str(request[5]),
        request_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stage="before_spawn",
        pid=None,
        returncode=None,
    )
    _save_child_status(status_path, status)
    launch = subprocess.Popen if popen is None else popen
    # These are file contexts, never a Popen context manager. Closing the parent's
    # descriptors leaves the child's inherited regular-file descriptors usable.
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        child = launch(argv, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL)
        _RETAINED_ACK_CHILDREN.append((child, str(status_path)))
        status.update(pid=child.pid, stage="spawned")

        def capture(stage, error=None):
            status.update(stage=stage, returncode=child.returncode)
            out, out_truncated = _child_output(stdout_path)
            err, err_truncated = _child_output(stderr_path)
            status.update(
                stdout_hex=out.hex(),
                stderr_hex=err.hex(),
                stdout_truncated=out_truncated,
                stderr_truncated=err_truncated,
            )
            if isinstance(error, subprocess.TimeoutExpired):
                for name, value in (
                    ("timeout_stdout", error.output),
                    ("timeout_stderr", error.stderr),
                ):
                    raw = (
                        value
                        if isinstance(value, bytes)
                        else (
                            value[:_CHILD_DIAGNOSTIC_LIMIT].encode("utf-8", errors="replace")
                            if isinstance(value, str)
                            else b""
                        )
                    )
                    status[name + "_hex"] = raw[:_CHILD_DIAGNOSTIC_LIMIT].hex()
                    status[name + "_truncated"] = len(raw) > _CHILD_DIAGNOSTIC_LIMIT
            _save_child_status(status_path, status)
            return out, err

        try:
            _save_child_status(status_path, status)
            child.communicate(timeout=timeout)
        except BaseException as original:
            try:
                capture(
                    "communicate_timeout"
                    if isinstance(original, subprocess.TimeoutExpired)
                    else "communication_error",
                    original,
                )
            except BaseException as diagnostic_error:
                original.add_note(
                    "Child/request retained; diagnostic capture failed: "
                    + type(diagnostic_error).__name__
                    + "; evidence="
                    + str(status_path)
                    + "; pid="
                    + str(child.pid)
                    + "; mode="
                    + status["mode"]
                    + "; request="
                    + str(request_path)
                    + "; work_id="
                    + status["work_id"]
                    + "; operation_id="
                    + status["operation_id"]
                    + "; request_sha256="
                    + status["request_sha256"]
                )
            raise
        out, err = capture(
            "zero_exit"
            if child.returncode == 0
            else "unknown_exit"
            if child.returncode is None
            else "nonzero_exit"
        )
        if child.returncode is None:
            raise RuntimeError("Child exit unconfirmed; retained evidence: " + str(status_path))
        if child.returncode != 0:
            raise subprocess.CalledProcessError(child.returncode, argv, output=out, stderr=err)
        if status["stdout_truncated"] or status["stderr_truncated"]:
            raise RuntimeError(
                "Child diagnostic bound exceeded; retained evidence: " + str(status_path)
            )
        return status


@unittest.skipUnless(os.environ.get("MODKIT_NATIVE_TEST_DSN"), "explicit disposable DB required")
class E31SQLIntegration(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.addCleanup(self.conn.close)

    def denied(self, request, code):
        before = snapshot(self.conn, request[0])
        self.conn.commit()
        try:
            call_e31(self.conn, request)
        except Exception as exc:
            self.assertEqual(getattr(exc, "sqlstate", None), code)
            self.conn.rollback()
        else:
            self.fail("invalid request accepted")
        self.assertEqual(snapshot(self.conn, request[0]), before)
        self.conn.commit()

    def test_all_eight_kind_outcome_cells(self):
        mapping = {
            "confirmed_success": "succeeded",
            "confirmed_rejection": "failed",
            "confirmed_cancelled": "cancelled",
            "safe_retry": "retry_waiting",
        }
        for kind in ("job", "inbox"):
            for outcome, target in mapping.items():
                with self.subTest(kind=kind, outcome=outcome):
                    held = make_held(self.conn, kind)
                    before = snapshot(self.conn, held["work_id"])
                    retry = (
                        _clock(self.conn) + timedelta(seconds=60)
                        if outcome == "safe_retry"
                        else None
                    )
                    request = resolution_request(held, outcome, retry_at=retry)
                    root = self.conn.execute("SELECT pg_current_xact_id()::text AS xid").fetchone()[
                        "xid"
                    ]
                    receipt = call_e31(self.conn, request)
                    self.assertEqual(str(receipt["resolution_root_xid"]), root)
                    self.assertIsNone(receipt["reason"])
                    self.assertEqual(receipt["operation_kind"], "reconcile_work")
                    self.conn.commit()
                    after = snapshot(self.conn, held["work_id"])
                    observed = observe(self.conn, held["work_id"])
                    self.assertEqual(observed["state"], target)
                    self.assertEqual(observed["attempt_count"], held["attempt_count"])
                    self.assertEqual(observed["ownership_revision"], held["ownership_revision"] + 1)
                    self.assertEqual(
                        observed["cancellation_requested"], held["cancellation_requested"]
                    )
                    self.assertEqual(after["job"], before["job"])
                    self.assertEqual(after["inbox"], before["inbox"])
                    old_attempt = before["attempts"][-1]
                    wanted_attempt = dict(
                        old_attempt,
                        outcome="safe_retry" if outcome == "safe_retry" else target,
                        evidence=request[9],
                    )
                    self.assertEqual(after["attempts"][-1], wanted_attempt)
                    history = after["history"][-1]
                    self.assertEqual(history["evidence"], request[9])
                    self.assertEqual(history["recorded_at"], receipt["recorded_at"])
                    self.assertEqual(len(after["history"]), len(before["history"]) + 1)
                    self.assertEqual(len(after["receipts"]), len(before["receipts"]) + 1)
                    if kind == "inbox":
                        self.assertEqual(
                            after["parent"][0]["nonterminal_count"],
                            before["parent"][0]["nonterminal_count"] - (outcome != "safe_retry"),
                        )
                    if outcome == "safe_retry":
                        self.assertIsNone(observed["dispatch_id"])
                        self.assertFalse(observed["resolution_present"])
                        self.assertEqual(observed["available_at"], retry)
                    else:
                        self.assertEqual(observed["dispatch_id"], held["dispatch_id"])
                        self.assertTrue(observed["resolution_present"])
                        self.assertEqual(observed["resolution_record_operation_id"], request[5])
                        self.assertEqual(observed["terminal_resolution_operation_id"], request[5])
                    if outcome == "confirmed_success":
                        self.assertEqual(
                            receipt["result_digest"], hashlib.sha256(request[8]).digest()
                        )
                        self.assertEqual(observed["success_origin"], "reconciled")
                    if kind == "job":
                        row = self.conn.execute(
                            "SELECT * FROM modkit_workers.w02(%s::uuid)", (held["work_id"],)
                        ).fetchone()
                        self.assertTrue(all(row[key] == value for key, value in observed.items()))
                    stable = snapshot(self.conn, held["work_id"])
                    self.conn.commit()
                    with connect() as fresh:
                        self.assertEqual(call_e31(fresh, request), receipt)
                    self.assertEqual(snapshot(self.conn, held["work_id"]), stable)
                    self.conn.commit()

    def test_wrong_fences_and_malformed_inputs(self):
        for kind in ("job", "inbox"):
            held = make_held(self.conn, kind)
            request = resolution_request(held, "confirmed_rejection")
            for index, value, code in (
                (1, held["ownership_revision"] + 1, "PZ003"),
                (2, 2, "PZ006"),
                (3, 2, "PZ003"),
                (4, uuid4(), "PZ003"),
                (6, "bad", "PZ006"),
                (8, b"unexpected", "PZ006"),
                (9, None, "PZ006"),
                (10, b"x" * 1048577, "PZ006"),
            ):
                with self.subTest(kind=kind, index=index):
                    changed = list(request)
                    changed[index] = value
                    self.denied(tuple(changed), code)

    def test_retry_policy_budget_cancellation_and_time(self):
        for kind in ("job", "inbox"):
            for options in (
                {"replay_policy": "disabled"},
                {"max_attempts": 1},
                {"cancellation": True},
            ):
                held = make_held(self.conn, kind, **options)
                self.denied(
                    resolution_request(
                        held, "safe_retry", retry_at=_clock(self.conn) + timedelta(seconds=30)
                    ),
                    "PZ004",
                )
            held = make_held(self.conn, kind)
            self.denied(resolution_request(held, "safe_retry", retry_at=_clock(self.conn)), "PZ004")
            deadline = _clock(self.conn) + timedelta(seconds=30)
            held = make_held(self.conn, kind, deadline=deadline)
            for retry in (deadline, deadline + timedelta(seconds=1)):
                self.denied(resolution_request(held, "safe_retry", retry_at=retry), "PZ004")

    def test_terminal_confirmation_after_cancellation(self):
        for kind in ("job", "inbox"):
            held = make_held(self.conn, kind, cancellation=True)
            request = resolution_request(held, "confirmed_success")
            call_e31(self.conn, request)
            self.conn.commit()
            observed = observe(self.conn, held["work_id"])
            self.assertTrue(observed["cancellation_requested"])
            self.assertEqual(observed["state"], "succeeded")
            self.conn.commit()

    def test_every_immutable_request_field_conflict(self):
        held = make_held(self.conn, "job")
        request = resolution_request(held, "confirmed_success")
        receipt = call_e31(self.conn, request)
        self.conn.commit()
        other = make_held(self.conn, "job")
        changes = (
            {0: other["work_id"]},
            {1: request[1] + 1},
            {3: 2},
            {4: uuid4()},
            {6: "confirmed_rejection", 8: None},
            {8: b"different"},
            {9: b"different"},
            {10: b"different"},
        )
        for updates in changes:
            changed = list(request)
            for key, value in updates.items():
                changed[key] = value
            self.denied(tuple(changed), "PZ002")
        self.assertEqual(call_e31(self.conn, request), receipt)
        self.conn.commit()
        # Existing hold_uncertain ID is globally unavailable even for same target.
        held = make_held(self.conn, "inbox")
        op = self.conn.execute(
            "SELECT operation_id FROM modkit_events.mutation_operations WHERE work_id=%s",
            (held["work_id"],),
        ).fetchone()["operation_id"]
        self.denied(resolution_request(held, "confirmed_rejection", operation_id=op), "PZ002")

    def test_root_rollback_and_repeat_after_new_dispatch(self):
        held = make_held(self.conn, "job")
        before = snapshot(self.conn, held["work_id"])
        request = resolution_request(held, "confirmed_success")
        call_e31(self.conn, request)
        self.conn.rollback()
        self.assertEqual(snapshot(self.conn, held["work_id"]), before)
        retry = _clock(self.conn) + timedelta(seconds=1)
        request = resolution_request(held, "safe_retry", retry_at=retry)
        receipt = call_e31(self.conn, request)
        self.conn.commit()
        while _clock(self.conn) <= retry:
            self.conn.commit()
            time.sleep(0.01)
        self.conn.commit()
        running = claim_dispatch(self.conn, observe(self.conn, held["work_id"]))
        self.assertNotEqual(running["dispatch_id"], held["dispatch_id"])
        self.assertEqual(running["attempt_count"], held["attempt_count"] + 1)
        stable = snapshot(self.conn, held["work_id"])
        self.assertEqual(call_e31(self.conn, request), receipt)
        self.conn.commit()
        self.assertEqual(snapshot(self.conn, held["work_id"]), stable)
        self.denied(resolution_request(held, "confirmed_rejection"), "PZ003")

    def _race(self, *, rollback, same_target=False, expires=False, competing=False):
        first = make_held(self.conn, "job")
        second = first if same_target else make_held(self.conn, "inbox")
        operation = uuid4()
        request1 = resolution_request(first, "confirmed_rejection", operation_id=operation)
        retry_at = _clock(self.conn) + timedelta(seconds=1) if expires else None
        request2 = resolution_request(
            second,
            "safe_retry" if expires else "confirmed_rejection",
            operation_id=uuid4() if competing else operation,
            retry_at=retry_at,
        )
        receipt1 = call_e31(self.conn, request1)
        result = {}
        with connect() as contender, connect() as observer:
            pid = contender.info.backend_pid

            def run():
                _run_lock_contender(
                    contender,
                    request2,
                    result,
                    "row",
                    (
                        "PZ003"
                        if competing
                        else "PZ004"
                        if expires
                        else "PZ002"
                        if not rollback and not same_target
                        else None
                    ),
                )

            thread = threading.Thread(target=run)
            thread.start()
            try:
                _wait_for_lock(observer, pid, self.conn.info.backend_pid, thread, result)
                if expires:
                    while _clock(observer) <= retry_at:
                        observer.commit()
                        time.sleep(0.01)
                    observer.commit()
                self.conn.rollback() if rollback else self.conn.commit()
            finally:
                _finalize_lock_race(self.conn, thread, result, pid, sys.exception())
            self.assertFalse(thread.is_alive(), "contender did not finish within statement timeout")
        if competing:
            self.assertEqual(result, {"sqlstate": "PZ003"})
        elif expires:
            self.assertEqual(result, {"sqlstate": "PZ004"})
        elif not rollback and not same_target:
            self.assertEqual(result, {"sqlstate": "PZ002"})
        elif not rollback:
            self.assertEqual(result.get("row"), receipt1)
        else:
            self.assertEqual(result["row"]["work_id"], second["work_id"])
        if rollback and expires:
            self.assertEqual(observe(self.conn, second["work_id"])["state"], "held")
            self.assertEqual(
                self.conn.execute(
                    "SELECT count(*) AS n FROM modkit_events.mutation_operations WHERE operation_id=%s",
                    (operation,),
                ).fetchone()["n"],
                0,
            )
        self.conn.commit()

    def test_cross_target_unique_commit_and_rollback(self):
        self._race(rollback=False)
        self._race(rollback=True)

    def test_same_target_exact_race(self):
        self._race(rollback=False, same_target=True)

    def test_same_target_competing_operations(self):
        self._race(rollback=False, same_target=True, competing=True)

    def test_cross_kind_e32_unique_commit_and_rollback(self):
        for rollback in (False, True):
            running = _make_running(self.conn, "job")
            held = make_held(self.conn, "inbox")
            failed = self.conn.execute("SELECT pg_current_xact_id()::text AS xid").fetchone()["xid"]
            self.conn.rollback()
            operation = uuid4()
            _call(
                self.conn,
                "modkit_events.e32",
                (
                    running["work_id"],
                    running["token"],
                    running["ownership_revision"],
                    1,
                    running["attempt_count"],
                    failed,
                    operation,
                    "test_uncertain",
                    b"oracle",
                    b"test",
                ),
                ("uuid", "uuid", "int8", "int4", "int4", "xid8", "uuid", "text", "bytea", "bytea"),
            )
            request = resolution_request(held, "confirmed_rejection", operation_id=operation)
            result = {}
            with connect() as contender, connect() as observer:

                def run():
                    _run_lock_contender(
                        contender, request, result, "receipt", ("PZ002" if not rollback else None)
                    )

                thread = threading.Thread(target=run)
                thread.start()
                try:
                    _wait_for_lock(
                        observer,
                        contender.info.backend_pid,
                        self.conn.info.backend_pid,
                        thread,
                        result,
                    )
                    self.conn.rollback() if rollback else self.conn.commit()
                finally:
                    _finalize_lock_race(
                        self.conn, thread, result, contender.info.backend_pid, sys.exception()
                    )
                self.assertFalse(thread.is_alive())
            if rollback:
                self.assertEqual(result["receipt"]["operation_kind"], "reconcile_work")
                self.assertEqual(observe(self.conn, running["work_id"])["state"], "running")
            else:
                self.assertEqual(result, {"sqlstate": "PZ002"})
                self.assertEqual(observe(self.conn, held["work_id"])["state"], "held")
            self.conn.commit()

    def test_cross_kind_e27_unique_commit_and_rollback(self):
        for rollback in (False, True):
            held = make_held(self.conn, "job")
            event = ("e31_pub_" + uuid4().hex).encode()
            empty = b"o\0\0\0\0"
            envelope = _frame(b"event-envelope", (event, b"run", b"1", empty, empty))
            replay = json.dumps(
                dict(
                    event_id=event.decode(), name="run", schema_version=1, payload={}, metadata={}
                ),
                separators=(",", ":"),
            ).encode()
            _call(
                self.conn,
                "modkit_events.e02",
                (event, 1, envelope, replay),
                ("bytea", "int4", "bytea", "bytea"),
            )
            self.conn.commit()
            digest = int.from_bytes(hashlib.sha256(event).digest(), "big")
            assert digest > 0
            rows = _call(
                self.conn,
                "modkit_events.e22",
                (1, 600.0, (digest - 1).to_bytes(32, "big"), 1),
                ("int4", "float8", "bytea", "int4"),
            )
            claimed = [row for row in rows if row["record_type"] == "item"]
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0]["event_id"], event)
            self.conn.commit()
            item = claimed[0]
            intent = uuid4()
            _call(
                self.conn,
                "modkit_events.e24",
                (event, item["token"], item["ownership_revision"], intent),
                ("bytea", "uuid", "int8", "uuid"),
            )
            self.conn.commit()
            _call(
                self.conn,
                "modkit_events.e25",
                (
                    event,
                    item["token"],
                    item["ownership_revision"],
                    intent,
                    "uncertain",
                    None,
                    b"oracle",
                ),
                ("bytea", "uuid", "int8", "uuid", "text", "bytea", "bytea"),
            )
            self.conn.commit()
            outbox = self.conn.execute(
                "SELECT * FROM modkit_events.e28(%s::bytea)", (event,)
            ).fetchone()
            operation = uuid4()
            _call(
                self.conn,
                "modkit_events.e27",
                (
                    event,
                    outbox["ownership_revision"],
                    operation,
                    "rejected",
                    None,
                    b"oracle",
                    b"test",
                ),
                ("bytea", "int8", "uuid", "text", "bytea", "bytea", "bytea"),
            )
            request = resolution_request(held, "confirmed_rejection", operation_id=operation)
            result = {}
            with connect() as contender, connect() as observer:

                def run():
                    _run_lock_contender(
                        contender, request, result, "receipt", ("PZ002" if not rollback else None)
                    )

                thread = threading.Thread(target=run)
                thread.start()
                try:
                    _wait_for_lock(
                        observer,
                        contender.info.backend_pid,
                        self.conn.info.backend_pid,
                        thread,
                        result,
                    )
                    self.conn.rollback() if rollback else self.conn.commit()
                finally:
                    _finalize_lock_race(
                        self.conn, thread, result, contender.info.backend_pid, sys.exception()
                    )
                self.assertFalse(thread.is_alive())
            if rollback:
                self.assertEqual(result["receipt"]["operation_kind"], "reconcile_work")
            else:
                self.assertEqual(result, {"sqlstate": "PZ002"})
                self.assertEqual(observe(self.conn, held["work_id"])["state"], "held")
            self.conn.commit()

    def test_waiter_retry_expires_after_unique_rollback(self):
        self._race(rollback=True, expires=True)

    def test_deadline_blocks_retry_but_not_terminal_confirmation(self):
        for kind in ("job", "inbox"):
            deadline = _clock(self.conn) + timedelta(seconds=5)
            held = make_held(self.conn, kind, deadline=deadline)
            while _clock(self.conn) < deadline:
                self.conn.commit()
                time.sleep(0.01)
            self.conn.commit()
            self.denied(
                resolution_request(held, "safe_retry", retry_at=deadline + timedelta(seconds=10)),
                "PZ009",
            )
            call_e31(self.conn, resolution_request(held, "confirmed_success"))
            self.conn.commit()
            self.assertEqual(observe(self.conn, held["work_id"])["state"], "succeeded")
            self.conn.commit()

    def test_cancellation_orderings(self):
        for kind in ("job", "inbox"):
            held = make_held(self.conn, kind)
            stale = resolution_request(held, "confirmed_success")
            _call(
                self.conn,
                "modkit_events.e12",
                (held["work_id"], None, None, "test_cancel"),
                ("uuid", "uuid", "int8", "text"),
            )
            self.conn.commit()
            self.denied(stale, "PZ003")
            current = observe(self.conn, held["work_id"])
            call_e31(self.conn, resolution_request(current, "confirmed_success"))
            self.conn.commit()
            stable = snapshot(self.conn, held["work_id"])
            _call(
                self.conn,
                "modkit_events.e12",
                (held["work_id"], None, None, "later_cancel"),
                ("uuid", "uuid", "int8", "text"),
            )
            self.conn.commit()
            self.assertEqual(snapshot(self.conn, held["work_id"]), stable)
            self.conn.commit()

    def test_guarded_completion_and_expiry_recovery_orderings(self):
        for kind in ("job", "inbox"):
            running = _make_running(self.conn, kind)
            fence = (
                running["work_id"],
                running["token"],
                running["ownership_revision"],
                running["cycle"],
                running["attempt_count"],
            )
            guard = _call(
                self.conn, "modkit_events.e08", fence, ("uuid", "uuid", "int8", "int4", "int4")
            )[0]
            _call(
                self.conn,
                "modkit_events.e10",
                (guard["guard_id"], fence[0], str(guard["root_xid"])) + fence[1:] + (b"guarded",),
                ("uuid", "uuid", "xid8", "uuid", "int8", "int4", "int4", "bytea"),
            )
            self.conn.commit()
            completed = observe(self.conn, running["work_id"])
            self.assertEqual(completed["success_origin"], "guarded")
            # Correct current revision but not held: E31 cannot rewrite E10 success.
            self.denied(resolution_request(completed, "confirmed_rejection"), "PZ004")
            deadline = _clock(self.conn) + timedelta(seconds=5)
            running = _make_running(self.conn, kind, deadline=deadline)
            while _clock(self.conn) < deadline:
                self.conn.commit()
                time.sleep(0.01)
            self.conn.commit()
            after = _target_scan_after(running)
            _record_raw_scan(self.conn, running, after)
            rows = _call(
                self.conn,
                "modkit_events.e13",
                (running["namespace"], kind, 1, after, 1),
                ("bytea", "text", "int4", "uuid", "int4"),
            )
            _check_target_page(rows, running, expected_items=1)
            self.conn.commit()
            held = observe(self.conn, running["work_id"])
            self.assertEqual(held["state"], "held")
            self.assertEqual(held["dispatch_id"], running["dispatch_id"])
            # The fixture's no-effect oracle authorizes terminal rejection.
            call_e31(self.conn, resolution_request(held, "confirmed_rejection"))
            self.conn.commit()
            before = snapshot(self.conn, held["work_id"])
            after = _target_scan_after(running)
            _record_raw_scan(self.conn, running, after)
            rows = _call(
                self.conn,
                "modkit_events.e13",
                (running["namespace"], kind, 1, after, 1),
                ("bytea", "text", "int4", "uuid", "int4"),
            )
            _check_target_page(rows, running, expected_items=0)
            self.conn.commit()
            self.assertEqual(snapshot(self.conn, held["work_id"]), before)
            self.conn.commit()

    def test_lost_application_ack_both_commit_branches(self):
        # Deliberate child death is only at the declared before/after-COMMIT
        # application boundary. Unexpected timeouts retain the child and request.
        for committed in (False, True):
            held = make_held(self.conn, "job")
            request = resolution_request(held, "confirmed_success")
            directory = tempfile.mkdtemp(
                prefix="e31-request-", dir=os.environ.get("MODKIT_E31_EVIDENCE_DIR")
            )
            path = Path(directory) / "request.json"
            _persist_request(path, request)  # Fsynced BEFORE any child/issuance.
            code = (
                "import os,sys; sys.path.insert(0,sys.argv[1]); "
                "from test_e31_resolution_sql_integration import connect,_load_request,call_e31; "
                "c=connect(); r=call_e31(c,_load_request(__import__('pathlib').Path(sys.argv[2]))); "
                + ("c.commit(); " if committed else "")
                + "os._exit(0)"
            )
            outcome = _run_retained_child(
                [sys.executable, "-B", "-c", code, str(Path(__file__).parent), str(path)],
                path,
                committed=committed,
            )
            self.assertEqual(outcome["returncode"], 0)
            self.assertEqual(outcome["stdout_hex"], "")
            self.assertEqual(outcome["stderr_hex"], "")
            retained = _load_request(path)
            self.assertEqual(retained, request)
            observed = observe(self.conn, held["work_id"])
            self.assertEqual(observed["state"], "succeeded" if committed else "held")
            self.conn.commit()
            with connect() as fresh:
                receipt = call_e31(fresh, retained)
            self.assertEqual(receipt["operation_id"], request[5])
            self.assertEqual(observe(self.conn, held["work_id"])["state"], "succeeded")
            self.conn.commit()
            # Provenance intentionally survives both success and any assertion failure.


class E31FixtureControls(unittest.TestCase):
    """Connection-free control checks; not a database simulation."""

    def test_fixture_identity(self):
        self.assertTrue(callable(globals().get("_fixture_identity")), "identity helper missing")
        a, b = UUID(int=17), UUID(int=91)
        job, other, inbox = (
            _fixture_identity("job", a),
            _fixture_identity("job", b),
            _fixture_identity("inbox", a),
        )
        self.assertEqual(job[:2], (b"jobs", None))
        self.assertEqual(other[:2], (b"jobs", None))
        self.assertNotEqual(job[2:], other[2:])
        self.assertEqual(inbox[0], inbox[1])
        self.assertNotEqual(inbox[0], _fixture_identity("inbox", b)[0])
        self.assertLessEqual(len(job[2]), 256)

    def test_raw_target_cursor(self):
        self.assertTrue(callable(globals().get("_target_scan_after")), "cursor helper missing")
        retained = tuple(UUID(int=n) for n in (1, 16, 17, 90, 91))
        for target in (UUID(int=17), UUID(int=91)):
            after = _target_scan_after({"work_id": target})
            self.assertEqual(after.int, target.int - 1)
            self.assertEqual(tuple(v for v in retained if v > after)[:1], (target,))
        self.assertEqual(len(retained), 5)
        with self.assertRaises(AssertionError):
            _target_scan_after({"work_id": UUID(int=0)})

    def test_exact_page_validation(self):
        self.assertTrue(callable(globals().get("_check_target_page")), "page checker missing")
        target = UUID(int=17)
        work = {"work_id": target}
        header = dict(
            record_type="header", visited=1, next_cursor=target, pass_exhausted=False, work_id=None
        )
        item = dict(
            record_type="item", visited=None, next_cursor=None, pass_exhausted=None, work_id=target
        )
        self.assertEqual(_check_target_page([header, item], work, expected_items=1), [item])
        self.assertEqual(_check_target_page([header], work, expected_items=0), [])
        for change in (
            {"visited": 0},
            {"visited": 2},
            {"next_cursor": UUID(int=16)},
            {"pass_exhausted": True},
            {"work_id": target},
        ):
            with self.assertRaises(AssertionError):
                _check_target_page([dict(header, **change), item], work, expected_items=1)
        for bad in (
            [header, dict(item, work_id=UUID(int=18))],
            [header, item, item],
            [header, dict(item, visited=1)],
            [item, header],
            [header],
        ):
            with self.assertRaises(AssertionError):
                _check_target_page(bad, work, expected_items=1)

    def test_raw_evidence_retains_earlier_terminal_and_incompatible_live_rows(self):
        target = {
            "work_id": UUID(int=91),
            "kind": "job",
            "namespace": b"jobs",
            "command_type": b"target_command",
        }
        earlier_terminal = dict(
            target, work_id=UUID(int=17), command_type=b"old", state="succeeded"
        )
        earlier_live = dict(
            target, work_id=UUID(int=90), command_type=b"other_live", state="running"
        )
        wanted = dict(target, state="queued")
        raw = [earlier_terminal, earlier_live, wanted]
        before = [dict(row) for row in raw]
        after = _target_scan_after(target)
        self.assertIs(_validate_raw_scan(raw, target, after), raw)
        self.assertEqual(raw, before)
        self.assertEqual(
            [row["work_id"] for row in raw if row["work_id"] > after], [target["work_id"]]
        )
        # Changing target to terminal still consumes that exact raw identity;
        # E13 then returns zero items with visited=1 and next_cursor=target.
        raw[-1] = dict(wanted, state="failed")
        self.assertIs(_validate_raw_scan(raw, target, after), raw)
        with self.assertRaises(AssertionError):
            _validate_raw_scan(raw[:-1], target, after)
        with self.assertRaises(AssertionError):
            _validate_raw_scan(raw, target, None)
        with self.assertRaises(AssertionError):
            _validate_raw_scan(raw[::-1], target, after)

    def test_actual_admission_and_intent_frames_agree(self):
        self.assertTrue(
            callable(globals().get("_admission_fields")), "pure admission helper missing"
        )

        def fields(raw):
            self.assertEqual(raw[:5], b"MKPF\x01")
            pos = 5

            def take():
                nonlocal pos
                size = int.from_bytes(raw[pos : pos + 8], "big")
                pos += 8
                value = raw[pos : pos + size]
                pos += size
                return value

            tag = take()
            count = int.from_bytes(raw[pos : pos + 4], "big")
            pos += 4
            values = tuple(take() for _ in range(count))
            self.assertEqual(pos, len(raw))
            return tag, values

        for kind in ("job", "inbox"):
            packet = _admission_fields(
                UUID(int=91),
                kind,
                datetime(2026, 11, 9, tzinfo=timezone.utc),
                replay_policy="application_safe",
                max_attempts=3,
                deadline=None,
            )
            args, types, event_id, envelope, replay = packet
            self.assertEqual(len(args), len(types))
            self.assertEqual(args[3], b"jobs" if kind == "job" else args[2])
            tag, intent = fields(args[12])
            self.assertEqual(tag, b"work-intent")
            self.assertEqual(intent[0], kind.encode())
            self.assertEqual(intent[1], _optional(args[2]))
            self.assertEqual(intent[2:4], (args[3], args[4]))
            self.assertEqual(intent[7], _optional(args[6]))
            self.assertEqual(intent[8], args[13])
            tag, event = fields(envelope)
            self.assertEqual(tag, b"event-envelope")
            self.assertEqual(event[:3], (event_id, args[4], b"1"))
            self.assertEqual(json.loads(replay)["name"].encode(), args[4])
            self.assertEqual(json.loads(replay)["event_id"].encode(), event_id)
            if kind == "inbox":
                self.assertEqual(args[13:15], (envelope, replay))

    def test_call_sites_and_coherent_identity(self):
        source = Path(__file__).read_text()
        claim = source.split("def claim_dispatch(", 1)[1].split("def _make_running(", 1)[0]
        self.assertIn("_target_scan_after(work)", claim)
        self.assertIn("_check_target_page(rows, work, expected_items=1)", claim)
        recovery = source.split("def test_guarded_completion_and_expiry_recovery_orderings(", 1)[1]
        recovery = recovery.split("def test_lost_application_ack_both_commit_branches(", 1)[0]
        self.assertEqual(recovery.count("_target_scan_after(running)"), 2)
        self.assertIn("_check_target_page(rows, running, expected_items=1)", recovery)
        self.assertIn("_check_target_page(rows, running, expected_items=0)", recovery)
        admission = source.split("def _admission_fields(", 1)[1].split("def _make_running(", 1)[0]
        self.assertIn("_fixture_identity(kind, work_id)", admission)
        self.assertIn("name=command_type.decode()", admission)
        self.assertNotIn('b"run"', admission)


class E31RetentionControls(unittest.TestCase):
    """Mocks record process calls; these cases never create an actual process."""

    def _exercise(self, *, returncode=0, timeout=False):
        from unittest.mock import Mock

        self.assertTrue(callable(globals().get("_run_retained_child")), "retained launcher missing")
        directory = Path(tempfile.mkdtemp(prefix="e31-retention-control-"))
        path = directory / "request.json"
        request = (
            UUID(int=1),
            3,
            1,
            1,
            UUID(int=2),
            UUID(int=3),
            "confirmed_success",
            None,
            b"result",
            b"evidence",
            b"binding",
        )
        _persist_request(path, request)
        child = Mock(pid=4271, returncode=None if timeout else returncode)
        original = subprocess.TimeoutExpired(
            ["fixture-child"], 25, output=b"partial-out", stderr=b"partial-err"
        )
        if timeout:
            child.communicate.side_effect = original
        else:
            child.communicate.return_value = (None, None)
        factory = Mock(return_value=child)

        def launch(*args, **kwargs):
            self.assertNotEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertNotEqual(kwargs["stderr"], subprocess.PIPE)
            kwargs["stdout"].write(b"file-out")
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"file-err")
            kwargs["stderr"].flush()
            return factory(*args, **kwargs)

        return directory, path, request, child, factory, launch, original

    def test_normal_zero_retains_provenance_and_checks_exit(self):
        directory, path, request, child, factory, launch, _ = self._exercise()
        result = _run_retained_child(["fixture-child"], path, committed=True, popen=launch)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout_hex"], b"file-out".hex())
        self.assertEqual(_load_request(path), request)
        self.assertTrue((directory / "child-status.json").is_file())
        factory.assert_called_once()
        child.communicate.assert_called_once_with(timeout=25)
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_nonzero_keeps_request_and_diagnostics_without_cleanup(self):
        directory, path, request, child, factory, launch, _ = self._exercise(returncode=7)
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            _run_retained_child(["fixture-child"], path, committed=False, popen=launch)
        self.assertEqual(caught.exception.returncode, 7)
        self.assertEqual(_load_request(path), request)
        status = json.loads((directory / "child-status.json").read_text())
        self.assertEqual(status["stage"], "nonzero_exit")
        self.assertEqual(status["stderr_hex"], b"file-err".hex())
        factory.assert_called_once()
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_timeout_keeps_original_exception_pid_identity_and_files(self):
        directory, path, request, child, factory, launch, original = self._exercise(timeout=True)
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            _run_retained_child(["fixture-child"], path, committed=True, popen=launch)
        self.assertIs(caught.exception, original)
        self.assertEqual(_load_request(path), request)
        status = json.loads((directory / "child-status.json").read_text())
        self.assertEqual(status["pid"], 4271)
        self.assertEqual(status["stage"], "communicate_timeout")
        self.assertEqual(status["mode"], "after_commit")
        self.assertEqual(status["request_path"], str(path.resolve()))
        self.assertEqual(status["operation_id"], str(request[5]))
        self.assertEqual(status["work_id"], str(request[0]))
        self.assertEqual(status["request_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(status["timeout_stdout_hex"], b"partial-out".hex())
        self.assertEqual(status["timeout_stderr_hex"], b"partial-err".hex())
        self.assertTrue((directory / "child.stdout").exists())
        self.assertTrue((directory / "child.stderr").exists())
        factory.assert_called_once()
        child.communicate.assert_called_once_with(timeout=25)
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_timeout_diagnostic_error_does_not_mask_original(self):
        from unittest.mock import patch

        directory, path, request, child, factory, launch, original = self._exercise(timeout=True)
        real_save = _save_child_status

        def save(status_path, status):
            if status["stage"] == "communicate_timeout":
                raise OSError("synthetic diagnostic failure")
            return real_save(status_path, status)

        with patch(__name__ + "._save_child_status", side_effect=save):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                _run_retained_child(["fixture-child"], path, committed=False, popen=launch)
        self.assertIs(caught.exception, original)
        self.assertTrue(any("diagnostic capture failed" in note for note in original.__notes__))
        self.assertEqual(_load_request(path), request)
        self.assertEqual(
            json.loads((directory / "child-status.json").read_text())["pid"], child.pid
        )
        self.assertTrue(any(item[0] is child for item in _RETAINED_ACK_CHILDREN))
        factory.assert_called_once()
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_unknown_exit_retains_without_extra_wait(self):
        directory, path, request, child, factory, launch, _ = self._exercise(returncode=None)
        with self.assertRaisesRegex(RuntimeError, "exit unconfirmed"):
            _run_retained_child(["fixture-child"], path, committed=False, popen=launch)
        self.assertEqual(_load_request(path), request)
        self.assertEqual(
            json.loads((directory / "child-status.json").read_text())["stage"], "unknown_exit"
        )
        factory.assert_called_once()
        child.communicate.assert_called_once_with(timeout=25)
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_authored_ack_case_has_no_temporary_cleanup_or_run(self):
        source = Path(__file__).read_text()
        case = source.split("    def test_lost_application_ack_both_commit_branches(", 1)[1]
        case = case.split("class E31FixtureControls", 1)[0]
        self.assertNotIn("subprocess.run(", case)
        self.assertNotIn("TemporaryDirectory", case)
        self.assertIn("_run_retained_child(", case)
        self.assertIn("tempfile.mkdtemp(", case)


class E31LockObservationControls(unittest.TestCase):
    """Connection-free controls, excluded from native case selection."""

    def invoke(self, blockers, *, alive=True, result=None, elapsed=0.1, error=None):
        from unittest.mock import Mock, patch

        observer = Mock()
        observer.execute.return_value.fetchone.return_value = {
            "blockers": blockers,
            "session_user": "postgres",
            "current_user": "modkit_w01_owner",
        }
        if error is not None:
            observer.execute.side_effect = error
        thread = Mock()
        if isinstance(alive, list):
            thread.is_alive.side_effect = alive
        else:
            thread.is_alive.return_value = alive
        thread.e31_error = None
        with (
            patch.object(time, "monotonic", side_effect=[0, 0, elapsed, 6]),
            patch.object(time, "sleep"),
            patch("builtins.print") as emit,
        ):
            try:
                value = _wait_for_lock(observer, 101, 202, thread, result or {}, timeout=5)
            except BaseException as exc:
                self.assertTrue(emit.called)
                self.assertEqual(exc.lock_observation["contender_pid"], 101)
                raise
            finally:
                observer.commit.assert_not_called()
                observer.rollback.assert_not_called()
        self.assertTrue(emit.called)
        observer.execute.assert_called_once()
        self.assertIn("pg_blocking_pids", observer.execute.call_args.args[0])
        self.assertNotIn("pg_stat_activity", observer.execute.call_args.args[0])
        self.assertEqual(observer.execute.call_args.args[1], (101,))
        return value

    def test_exact_expected_blocker(self):
        evidence = self.invoke([303, 202])
        self.assertEqual(evidence["samples"][0]["row"]["blockers"], [303, 202])
        self.assertEqual(evidence["status"], "verified")

    def test_early_contender_failure(self):
        with self.assertRaisesRegex(AssertionError, "contender"):
            self.invoke([202], alive=False, result={"sqlstate": "PZ002"})

    def test_contender_exits_during_observation(self):
        with self.assertRaisesRegex(AssertionError, "during"):
            self.invoke([202], alive=[True, False, False])

    def test_absent_blocker(self):
        with self.assertRaisesRegex(AssertionError, "deadline"):
            self.invoke([])

    def test_wrong_blocker(self):
        with self.assertRaisesRegex(AssertionError, "deadline"):
            self.invoke([303])

    def test_late_observation_rejected(self):
        with self.assertRaisesRegex(AssertionError, "deadline"):
            self.invoke([202], elapsed=5)

    def test_read_error_preserved(self):
        error = PermissionError("denied")
        with self.assertRaises(PermissionError) as caught:
            self.invoke(None, error=error)
        self.assertIs(caught.exception, error)

    def test_null_blocker_result_rejected(self):
        with self.assertRaisesRegex(AssertionError, "invalid"):
            self.invoke(None)

    def test_all_original_callers_supply_exact_holder_and_diagnostics(self):
        import ast

        tree = ast.parse(Path(__file__).read_text())
        integration = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "E31SQLIntegration"
        )
        calls = [
            node
            for node in ast.walk(integration)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_wait_for_lock"
        ]
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(len(call.args), 5)
            self.assertEqual(ast.unparse(call.args[2]), "self.conn.info.backend_pid")
            self.assertEqual(ast.unparse(call.args[3]), "thread")
            self.assertEqual(ast.unparse(call.args[4]), "result")
        calls = [
            node
            for node in ast.walk(integration)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_finalize_lock_race"
        ]
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(ast.unparse(call.args[-1]), "sys.exception()")


class E31RaceFinalizerControls(unittest.TestCase):
    """Only mocks: never launch a thread, process, or database connection."""

    def invoke(self, *, rollback_error=None, join_error=None, alive=False, original=None):
        from unittest.mock import Mock, patch

        holder, thread = Mock(), Mock()
        holder.info.backend_pid = 202
        holder.rollback.side_effect = rollback_error
        thread.join.side_effect = join_error
        thread.is_alive.return_value = alive
        thread.e31_error = "retained contender error"
        thread.e31_outcome = {"status": "sql_error_rollback_acknowledged", "errors": []}
        self.holder, self.thread = holder, thread
        with patch("builtins.print") as emit:
            try:
                return _finalize_lock_race(holder, thread, {"sqlstate": "PZ002"}, 101, original)
            finally:
                holder.rollback.assert_called_once_with()
                holder.commit.assert_not_called()
                thread.join.assert_called_once_with(22)
                thread.kill.assert_not_called()
                thread.terminate.assert_not_called()
                self.assertTrue(emit.called)

    def test_success_retains_actual_outcome(self):
        evidence = self.invoke()
        self.assertEqual(evidence["rollback"], "succeeded")
        self.assertEqual(evidence["join"], "returned")
        self.assertFalse(evidence["alive"])
        self.assertEqual(evidence["result"], {"sqlstate": "PZ002"})

    def test_rollback_error_retains_uncertainty_and_still_joins(self):
        error = RuntimeError("rollback failed")
        with self.assertRaises(BaseExceptionGroup) as caught:
            self.invoke(rollback_error=error)
        self.assertIn(error, caught.exception.exceptions)
        self.assertEqual(caught.exception.race_finalization["rollback"], "failed")

    def test_join_error_retained(self):
        error = RuntimeError("join failed")
        with self.assertRaises(BaseExceptionGroup) as caught:
            self.invoke(join_error=error)
        self.assertIn(error, caught.exception.exceptions)
        self.assertEqual(caught.exception.race_finalization["join"], "failed")

    def test_still_alive_fails_without_signal(self):
        with self.assertRaises(BaseExceptionGroup) as caught:
            self.invoke(alive=True)
        self.assertTrue(caught.exception.race_finalization["alive"])

    def test_original_and_both_errors_preserved(self):
        original = AssertionError("oracle failed")
        rollback = RuntimeError("rollback failed")
        join = RuntimeError("join failed")
        with self.assertRaises(BaseExceptionGroup) as caught:
            self.invoke(original=original, rollback_error=rollback, join_error=join)
        self.assertEqual(caught.exception.exceptions, (original, rollback, join))
        self.assertIs(caught.exception.__cause__, original)

    def test_success_does_not_replace_original(self):
        original = AssertionError("oracle failed")
        try:
            try:
                raise original
            finally:
                self.invoke(original=sys.exception())
        except AssertionError as exc:
            self.assertIs(exc, original)
        else:
            self.fail("original failure suppressed")


class E31ContenderOutcomeControls(unittest.TestCase):
    """Execute AST-extracted real run bodies synchronously with mocks only."""

    def probe(self, method, *, commit_failure=False, rollback_failure=False):
        import ast
        from unittest.mock import Mock, patch

        tree = ast.parse(Path(__file__).read_text())
        integration = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "E31SQLIntegration"
        )
        owner = next(
            n for n in integration.body if isinstance(n, ast.FunctionDef) and n.name == method
        )
        body = next(
            n for n in ast.walk(owner) if isinstance(n, ast.FunctionDef) and n.name == "run"
        )
        result = {}
        contender = Mock()
        contender.info.backend_pid = 101
        thread = Mock()
        thread.is_alive.return_value = False
        commit_error = RuntimeError("commit acknowledgement lost")
        sql_error = RuntimeError("expected conflict")
        sql_error.sqlstate = "PZ002"
        rollback_error = RuntimeError("rollback acknowledgement lost")
        if commit_failure:
            contender.commit.side_effect = commit_error
        if rollback_failure:
            contender.rollback.side_effect = rollback_error
        call = Mock(return_value={"operation_id": "retained"})
        if rollback_failure:
            call.side_effect = sql_error
        scope = dict(
            globals(),
            contender=contender,
            result=result,
            request=(1,),
            request2=(1,),
            rollback=False,
            competing=False,
            expires=False,
            same_target=False,
            expected_sqlstate="PZ002",
            call_e31=call,
        )
        code = compile(ast.Module(body=[body], type_ignores=[]), "<actual-run-body>", "exec")
        exec(code, scope)
        with (
            patch.object(threading, "current_thread", return_value=thread),
            patch.dict(globals(), {"call_e31": call}),
        ):
            scope["run"]()
        self.assertFalse("row" in result or "receipt" in result)
        self.assertNotIn("sqlstate", result)
        holder = Mock()
        holder.info.backend_pid = 202
        with patch("builtins.print"):
            with self.assertRaises(BaseExceptionGroup) as caught:
                _finalize_lock_race(holder, thread, result, 101)
        errors = caught.exception.exceptions
        if commit_failure:
            self.assertIn(commit_error, errors)
            self.assertEqual(thread.e31_outcome["status"], "commit_uncertain")
        else:
            self.assertIn(sql_error, errors)
            self.assertIn(rollback_error, errors)
            self.assertEqual(thread.e31_outcome["status"], "rollback_uncertain")
        self.assertEqual(thread.e31_outcome["request"], (1,))
        contender.rollback.assert_called_once_with()
        thread.join.assert_called_once_with(22)

    def test_success_published_only_after_commit_acknowledgement(self):
        from unittest.mock import Mock, patch

        thread, contender = Mock(), Mock()
        result = {}
        contender.commit.side_effect = lambda: self.assertEqual(result, {})
        with patch.object(threading, "current_thread", return_value=thread), patch.dict(
            globals(), {"call_e31": Mock(return_value={"receipt": 1})}
        ):
            _run_lock_contender(contender, (1,), result, "row", None)
        self.assertEqual(result, {"row": {"receipt": 1}})
        self.assertEqual(thread.e31_outcome["status"], "commit_acknowledged")
        contender.rollback.assert_not_called()

    def test_expected_sqlstate_published_only_after_rollback_acknowledgement(self):
        from unittest.mock import Mock, patch

        thread, contender = Mock(), Mock()
        result = {}
        error = RuntimeError("conflict")
        error.sqlstate = "PZ002"
        contender.rollback.side_effect = lambda: self.assertEqual(result, {})
        with patch.object(threading, "current_thread", return_value=thread), patch.dict(
            globals(), {"call_e31": Mock(side_effect=error)}
        ):
            _run_lock_contender(contender, (1,), result, "receipt", "PZ002")
        self.assertEqual(result, {"sqlstate": "PZ002"})
        self.assertIs(thread.e31_outcome["primary_error"], error)
        contender.commit.assert_not_called()

    def test_dead_thread_without_acknowledged_outcome_is_failure(self):
        from unittest.mock import Mock, patch

        holder, thread = Mock(), Mock()
        thread.is_alive.return_value = False
        with patch("builtins.print"), self.assertRaises(BaseExceptionGroup):
            _finalize_lock_race(holder, thread, {}, 101)

    def test_race_commit_failure(self):
        self.probe("_race", commit_failure=True)

    def test_e32_commit_failure(self):
        self.probe("test_cross_kind_e32_unique_commit_and_rollback", commit_failure=True)

    def test_e27_commit_failure(self):
        self.probe("test_cross_kind_e27_unique_commit_and_rollback", commit_failure=True)

    def test_race_rollback_failure(self):
        self.probe("_race", rollback_failure=True)

    def test_e32_rollback_failure(self):
        self.probe("test_cross_kind_e32_unique_commit_and_rollback", rollback_failure=True)

    def test_e27_rollback_failure(self):
        self.probe("test_cross_kind_e27_unique_commit_and_rollback", rollback_failure=True)


if __name__ == "__main__":
    unittest.main()
