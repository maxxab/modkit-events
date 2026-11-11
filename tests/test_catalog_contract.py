"""Pure metadata contracts; these tests do not qualify PostgreSQL behavior."""

from dataclasses import FrozenInstanceError

from modkit_events.persistence import catalog as c


def test_lookup_identity_and_closed_keys():
    # Wrong routing/extra key must never select executable metadata.
    for key in ("E01", "E14", "E34"):
        assert c.get_statement(key) is c.get_statement(key)
    for key in ("E00", "E35", "W01", "read_work", "E01 ", 1, None):
        try:
            c.get_statement(key)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("unregistered key accepted")


def test_admission_parameter_positions_and_scope_nullability():
    s = c.get_statement("E03")
    assert tuple(p.name for p in s.parameters) == (
        "work_id",
        "kind",
        "subscription_id",
        "namespace",
        "command_type",
        "scope_evidence",
        "idempotency_key",
        "canonical_version",
        "schema_version_decimal",
        "scope_application",
        "scope_tenant",
        "scope_owner",
        "intent_evidence",
        "semantic_input",
        "replay_input",
        "protected_binding",
        "replay_policy",
        "max_attempts",
        "deadline",
        "original_available_at",
        "event_id",
        "event_canonical_version",
        "envelope_evidence",
        "event_replay_input",
        "supported",
        "broker_reference",
        "transport_observation",
    )
    assert [s.parameters[i].nullable for i in (2, 6, 9, 10, 11, 18)] == [
        True,
        True,
        False,
        True,
        True,
        True,
    ]
    assert s.parameters[10].wire_type is c.WireType.BYTEA
    assert s.parameters[21].constraint is c.ConstraintId.CANONICAL_VERSION
    assert s.parameters[23].constraint is c.ConstraintId.REPLAY_INPUT


def test_work_and_inbox_protected_suffix_shapes():
    work = c.get_statement("E15").result.columns
    assert len(work) == 56
    assert [work[i].name for i in (2, 14, 20, 26, 29, 33, 38, 39, 40, 55)] == [
        "subscription_id",
        "semantic_input",
        "original_available_at",
        "available_at",
        "dispatch_id",
        "success_origin",
        "terminal_resolution_operation_id",
        "resolution_present",
        "resolution_record_operation_id",
        "resolution_record_recorded_at",
    ]
    assert len({col.name for col in work}) == 56
    assert all(col.nullable for col in work[40:])
    assert not work[39].nullable
    assert len(c.get_statement("E16").result.columns) == 60
    assert len(c.get_statement("E34").result.columns) == 61
    assert c.get_statement("E34").result.cardinality is c.CardinalityKind.FIND_THREE
    assert c.get_statement("E17").result.cardinality is c.CardinalityKind.FIND_TWO


def test_scan_readiness_and_mutation_metadata():
    for key, width, cursor in (
        ("E04", 60, c.WireType.UUID),
        ("E13", 60, c.WireType.UUID),
        ("E22", 17, c.WireType.BYTEA),
        ("E26", 17, c.WireType.BYTEA),
    ):
        spec = c.get_statement(key)
        assert spec.result.cardinality is c.CardinalityKind.SCAN
        assert len(spec.result.columns) == width
        assert tuple(col.name for col in spec.result.columns[:4]) == (
            "record_type",
            "visited",
            "next_cursor",
            "pass_exhausted",
        )
        assert spec.result.columns[2].wire_type is cursor
        assert all(col.nullable for col in spec.result.columns[4:])
        assert [p.name for p in spec.parameters[-2:]] == ["scan_after", "discovery_budget"]
    assert c.get_statement("E33").result.cardinality is c.CardinalityKind.READINESS
    assert c.get_statement("E14").mutation is True
    assert c.get_statement("E33").mutation is False
    assert len(c.get_statement("E31").result.columns) == 16
    assert len(c.get_statement("E32").result.columns) == 13
    assert len(c.get_statement("E27").result.columns) == 9


def test_metadata_rejects_mutability_and_duplicate_names():
    s = c.get_statement("E15")
    try:
        s.key = "E99"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("descriptor mutable")
    kwargs = dict(
        key="E15",
        contract_id="modkit-pg-ab-2",
        parameters=s.parameters,
        result=s.result,
        mutation=False,
    )
    for bad in ([*s.parameters], s.parameters + s.parameters):
        try:
            c.StatementSpec(**(kwargs | {"parameters": bad}))
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("mutable/duplicate parameters accepted")
    try:
        c.ParameterSpec(
            name="x", wire_type="uuid", nullable=False, constraint=c.ConstraintId.WORK_ID
        )
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("untyped metadata accepted")


def test_receipt_limit_has_distinct_constraint_from_megabyte_evidence():
    # Mapping receipt to generic evidence would incorrectly allow >4096 bytes.
    for key in ("E25", "E27"):
        receipt = next(p for p in c.get_statement(key).parameters if p.name == "receipt")
        assert receipt.constraint.value == "receipt"


def test_transition_specs_preserve_uncertainty_and_retry_pointer():
    from modkit_events.persistence import transitions as t

    rules = {rule.rule_id: rule for rule in t._WORK_RULES}
    for name in ("failure_retry", "reconcile_safe_retry"):
        assert rules[name].target == "retry_waiting"
        assert rules[name].dispatch_pointer == "clear_resolved"
        assert rules[name].attempt_delta == 0
        assert not rules[name].release_capacity
    for name in ("hold_uncertain", "recover_dispatched", "cancel_running"):
        assert rules[name].target == "held"
        assert rules[name].dispatch_pointer == "retain"
        assert rules[name].attempt_delta == 0
        assert not rules[name].release_capacity
    assert rules["dispatch"].attempt_delta == 1
    assert sum(rule.attempt_delta for rule in rules.values()) == 1
    assert rules["complete"].success_origin == "guarded"
    assert rules["reconcile_success"].success_origin == "reconciled"
    assert all(rule.guard for rule in rules.values())
    pub = {rule.rule_id: rule for rule in t._PUBLICATION_RULES}
    assert pub["recover_publication_intent"].target == "held"
    assert not any(rule.source == "held" and rule.target == "pending" for rule in pub.values())


def test_operation_kind_discriminators_are_authoritative_and_immutable():
    assert getattr(c, "MUTATION_OPERATION_KINDS", None) is not None, "operation mapping missing"
    assert {key: value.value for key, value in c.MUTATION_OPERATION_KINDS.items()} == {
        "E27": "repair_publication",
        "E31": "reconcile_work",
        "E32": "hold_uncertain",
    }
    try:
        c.MUTATION_OPERATION_KINDS["E31"] = c.OperationKind.HOLD_UNCERTAIN
    except TypeError:
        pass
    else:
        raise AssertionError("operation mapping mutable")


def test_record_code_work_domain_exact():
    from modkit_events.persistence import transitions as t

    expected = frozenset(
        {
            "intake_runnable",
            "intake_blocked",
            "claim",
            "renew",
            "dispatch",
            "defer",
            "complete",
            "failure_terminal",
            "failure_cancelled",
            "failure_retry",
            "cancel_predispatch",
            "cancel_running",
            "cancel_held",
            "recover_expired_predispatch",
            "recover_exhausted_predispatch",
            "recover_claim",
            "recover_dispatched",
            "reconcile_success",
            "reconcile_rejection",
            "reconcile_cancelled",
            "reconcile_safe_retry",
            "hold_uncertain",
        }
    )
    assert t._WORK_HISTORY_CODES == expected
    assert "arm_guard" not in t._WORK_HISTORY_CODES
    assert "cancel_terminal" not in t._WORK_HISTORY_CODES


def test_record_code_publication_domain_exact():
    from modkit_events.persistence import transitions as t

    expected = frozenset(
        {
            "enqueue",
            "claim_publication",
            "renew_publication",
            "publication_intent",
            "publication_confirmed",
            "publication_rejected",
            "publication_uncertain",
            "recover_publication_preintent",
            "recover_publication_intent",
            "repair_published",
            "repair_rejected",
        }
    )
    assert t._PUBLICATION_HISTORY_CODES == expected
    for request_or_state in ("confirmed", "rejected", "uncertain", "pending", "held"):
        assert request_or_state not in t._PUBLICATION_HISTORY_CODES


def test_record_code_attempt_domain_exact():
    from modkit_events.persistence import transitions as t

    assert t._ATTEMPT_OUTCOME_CODES == frozenset(
        {
            "dispatched",
            "succeeded",
            "failed",
            "cancelled",
            "uncertain",
            "cancelled_unresolved",
            "safe_retry",
        }
    )
    for scheduler_code in ("queued", "claimed", "running", "held", "retry_waiting"):
        assert scheduler_code not in t._ATTEMPT_OUTCOME_CODES


def test_record_code_types_immutable_and_private():
    from modkit_events.persistence import transitions as t

    assert t.__all__ == ()
    for domain in (t._WORK_HISTORY_CODES, t._PUBLICATION_HISTORY_CODES, t._ATTEMPT_OUTCOME_CODES):
        assert type(domain) is frozenset
        assert all(type(code) is str for code in domain)
        assert "not_a_protocol_code" not in domain
        assert "" not in domain
        assert not any(code.upper() in domain for code in domain)
        try:
            domain.add("not_a_protocol_code")
        except AttributeError:
            pass
        else:
            raise AssertionError("record code domain mutable")
