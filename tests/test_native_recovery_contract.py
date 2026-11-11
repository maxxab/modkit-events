"""Connection-free complete E13 contract tests."""

import unittest
from dataclasses import replace
from uuid import UUID

from recovery_test_support import requires_recovery_profile

from modkit_events.persistence import bindings as B
from modkit_events.persistence import models as M
from modkit_events.persistence import rows as R
from modkit_events.persistence.catalog import RecordKind, get_statement
from modkit_events.persistence.errors import _ValidationReject


def request(**changes):
    values = dict(namespace=b"jobs", kind="job", limit=1, scan_after=None, discovery_budget=128)
    values.update(changes)
    return B._freeze_request_raw(
        get_statement("E13"), tuple(values.values()), context=B._return_context_raw()
    )


def header(visited=0, cursor=None, exhausted=True):
    return ("header", visited, cursor, exhausted) + (None,) * 56


def wire_item(fields=None):
    fields = work_fields() if fields is None else fields
    return ("item", None, None, None) + tuple(
        False
        if c.name == "resolution_present"
        else None
        if c.name.startswith("resolution_record_")
        else fields[c.name]
        for c in get_statement("E15").result.columns
    )


@requires_recovery_profile
class ContractTests(unittest.TestCase):
    def decoder(self):
        fn = getattr(R, "_decode_native_recovery_result_raw", None)
        self.assertTrue(callable(fn), "E13 raw full-page decoder missing")
        return fn

    def test_complete_job_public_parity(self):
        fn = self.decoder()
        req = request()
        rows = (header(1, UUID(int=1), False), wire_item())
        result = fn(req, rows)
        self.assertEqual(result, R.decode_scan_page(req, rows, item_kind=RecordKind.WORK))
        self.assertEqual(len(result.items[0].__dataclass_fields__), 40)
        self.assertIsNone(result.items[0].resolution)

    def test_empty_and_progress_pages(self):
        fn = self.decoder()
        self.assertEqual(fn(request(), (header(),)).items, ())
        self.assertEqual(fn(request(), (header(1, UUID(int=7), True),)).visited, 1)
        incoming = UUID(int=5)
        self.assertEqual(
            fn(request(scan_after=incoming), (header(0, incoming),)).next_cursor, incoming
        )

    def test_invalid_framing_and_semantics(self):
        fn = self.decoder()
        req = request()
        bad = [
            (),
            (header(), header()),
            (header(0, UUID(int=1)),),
            (header(1, None),),
            (header(128, UUID(int=1), True),),
            (header(1, UUID(int=1), True), wire_item()),
            (header(1, UUID(int=1), False), wire_item({**work_fields(), "namespace": b"other"})),
            (header(1, UUID(int=1), False), wire_item({**work_fields(), "replay_input": b"[]"})),
        ]
        for rows in bad:
            with self.subTest(rows=rows[:1]), self.assertRaises(_ValidationReject):
                fn(req, rows)

    def test_resolution_and_forged_statement(self):
        fn = self.decoder()
        row = list(wire_item())
        row[43] = True
        with self.assertRaises(_ValidationReject):
            fn(request(), (header(1, UUID(int=1), False), tuple(row)))
        req = request()
        object.__setattr__(req, "statement", replace(req.statement))
        with self.assertRaises(_ValidationReject):
            fn(req, (header(),))

    def test_full_abi_limits(self):
        fn = self.decoder()
        for kind in ("job", "inbox"):
            for limit in (1, 256):
                self.assertEqual(
                    fn(request(kind=kind, limit=limit, discovery_budget=4096), (header(),)).items,
                    (),
                )
        for kw in (
            {"limit": True},
            {"limit": 257},
            {"limit": 2, "discovery_budget": 1},
            {"discovery_budget": 4097},
        ):
            with self.assertRaises(_ValidationReject):
                request(**kw)


def work_fields():
    from datetime import datetime, timezone
    from uuid import UUID

    from modkit_events.persistence.scope import Scope, canonical_scope, encode_scope_fields

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scope = Scope("app")
    app, tenant, owner = encode_scope_fields(scope)
    se = M.ScopeEvidence(
        canonical_version=1,
        canonical=canonical_scope(scope),
        application=app,
        tenant=tenant,
        owner=owner,
    )
    ident = M.WorkIdentity(
        work_id=UUID(int=1),
        kind=M.WorkKind.JOB,
        subscription_id=None,
        namespace="jobs",
        command_type="run",
        scope=se,
        idempotency_key=None,
    )
    material = M.ProtectedBindingInput(
        material_state=M.MaterialState.ABSENT,
        codec=None,
        key_version=None,
        expires_at=None,
        cleanup_policy=M.CleanupPolicy.RETAIN,
        sidecar=None,
        reference=None,
        content_binding=b"",
        recovery_metadata=b"",
        projection_metadata={},
    )
    admission = M.AdmissionInput(
        identity=ident,
        schema_version=1,
        semantic_input=B.canonical_json({}),
        replay_input=b"{}",
        protected_binding=B.canonical_protected_binding(material).content,
        replay_policy=M.ReplayPolicy.DISABLED,
        max_attempts=3,
        deadline=None,
        original_available_at=now,
    )
    fields = dict(
        work_id=ident.work_id,
        kind="job",
        subscription_id=None,
        namespace=b"jobs",
        command_type=b"run",
        schema_version_decimal=b"1",
        runnable_version=1,
        canonical_version=1,
        scope_evidence=se.canonical,
        scope_application=app,
        scope_tenant=None,
        scope_owner=None,
        idempotency_key=None,
        intent_evidence=B.canonical_intent(admission).content,
        semantic_input=admission.semantic_input,
        replay_input=admission.replay_input,
        protected_binding=admission.protected_binding,
        replay_policy="disabled",
        max_attempts=3,
        deadline=None,
        original_available_at=now,
        state="queued",
        cancellation_requested=False,
        token=None,
        ownership_revision=0,
        lease_until=None,
        available_at=now,
        cycle=1,
        attempt_count=0,
        dispatch_id=None,
        result=None,
        created_at=now,
        updated_at=now,
        success_origin=None,
        completion_guard_id=None,
        final_fence_at=None,
        completion_result_digest=None,
        resolution_operation_id=None,
        terminal_resolution_operation_id=None,
        resolution=None,
    )
    return fields


class RawRequestTests(unittest.TestCase):
    def test_namespace_cursor_and_exact_scalar_boundaries(self):
        # A valid canonical request must be accepted before negative controls.
        try:
            valid = request(
                namespace=b"x" * 256,
                kind="inbox",
                limit=256,
                scan_after=UUID(int=2**128 - 1),
                discovery_budget=4096,
            )
        except _ValidationReject:
            self.fail("canonical E13 constraint dispatch missing")
        self.assertEqual(valid.parameters[2], 256)

        class HostileInt(int):
            def __int__(self):
                raise AssertionError("coercion")

            def __eq__(self, other):
                raise AssertionError("comparison")

        class HostileBytes(bytes):
            def decode(self, *a, **k):
                raise AssertionError("decode")

        class HostileUUID(UUID):
            def __eq__(self, other):
                raise AssertionError("comparison")

        for kw in (
            {"namespace": b""},
            {"namespace": b"x" * 257},
            {"namespace": b"\xff"},
            {"namespace": HostileBytes(b"jobs")},
            {"kind": "other"},
            {"kind": None},
            {"limit": HostileInt(1)},
            {"limit": True},
            {"discovery_budget": True},
            {"discovery_budget": 0},
            {"limit": 2, "discovery_budget": 1},
            {"scan_after": HostileUUID(int=1)},
        ):
            with self.subTest(kw=kw), self.assertRaises(_ValidationReject):
                request(**kw)
        req = request()
        for spec in (replace(get_statement("E13")), get_statement("E12")):
            with self.assertRaises(_ValidationReject):
                B._freeze_request_raw(spec, req.parameters, context=B._return_context_raw())
        forged = UUID(int=1)
        object.__setattr__(forged, "int", HostileInt(1))
        with self.assertRaises(_ValidationReject):
            request(scan_after=forged)

    def test_e31_selected_raw_behavior_unchanged(self):
        from datetime import datetime, timezone
        from hashlib import sha256

        u = UUID(int=1)
        for outcome in (
            "confirmed_success",
            "confirmed_rejection",
            "confirmed_cancelled",
            "safe_retry",
        ):
            result = b"x" if outcome == "confirmed_success" else None
            retry = datetime(2030, 1, 1, tzinfo=timezone.utc) if outcome == "safe_retry" else None
            params = (u, 1, 1, 1, u, u, outcome, retry, result, b"e", b"b")
            req = B._freeze_request_raw(
                get_statement("E31"), params, context=B._return_context_raw()
            )
            values = (
                u,
                "reconcile_work",
                u,
                1,
                1,
                1,
                u,
                outcome,
                retry,
                result,
                sha256(result).digest() if result is not None else None,
                None,
                b"e",
                b"b",
                2**64 - 1,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            value = R._decode_native_event_result_raw(req, (values,))
            self.assertEqual(value.outcome, outcome)
            self.assertEqual(value.resolution_root_xid, 2**64 - 1)


@requires_recovery_profile
class FullBranchTests(unittest.TestCase):
    def test_inbox_full_canonical_input(self):
        fields = work_fields()
        scope = M.ScopeEvidence(
            canonical_version=1,
            canonical=fields["scope_evidence"],
            application=fields["scope_application"],
            tenant=None,
            owner=None,
        )
        identity = M.WorkIdentity(
            work_id=fields["work_id"],
            kind=M.WorkKind.INBOX,
            subscription_id="subscription",
            namespace="jobs",
            command_type="run",
            scope=scope,
            idempotency_key=None,
        )
        replay = b'{"event_id":"id","name":"run","payload":{},"schema_version":1,"metadata":{}}'
        admission = M.AdmissionInput(
            identity=identity,
            schema_version=1,
            semantic_input=B.canonical_event(B.validate_event_replay(replay)).content,
            replay_input=replay,
            protected_binding=fields["protected_binding"],
            replay_policy=M.ReplayPolicy.DISABLED,
            max_attempts=3,
            deadline=None,
            original_available_at=fields["original_available_at"],
        )
        fields.update(
            kind="inbox",
            subscription_id=b"subscription",
            semantic_input=admission.semantic_input,
            replay_input=replay,
            intent_evidence=B.canonical_intent(admission).content,
        )
        rows = (header(1, UUID(int=1), False), wire_item(fields))
        req = request(kind="inbox")
        self.assertEqual(
            R._decode_native_recovery_result_raw(req, rows),
            R.decode_scan_page(req, rows, item_kind=RecordKind.WORK),
        )

    def test_all_recovery_post_states_and_ordering(self):
        for state in ("queued", "expired", "failed", "cancelled", "held"):
            fields = work_fields()
            fields["state"] = state
            if state == "held":
                fields.update(attempt_count=1, dispatch_id=UUID(int=2))
            rows = (header(1, UUID(int=1), False), wire_item(fields))
            page = R._decode_native_recovery_result_raw(request(), rows)
            self.assertEqual(page.items[0].state, state)
        rows = (header(2, UUID(int=2), False), wire_item(), wire_item())
        with self.assertRaises(_ValidationReject):
            R._decode_native_recovery_result_raw(request(limit=2), rows)
