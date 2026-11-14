"""Pure shared metadata validation and first-slice identity, not SQL proof."""

import sys
from contextlib import contextmanager
from dataclasses import replace

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import catalog as C
from modkit_events.persistence import errors as E


def capture(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("invalid metadata was admitted")


def raw_shape(value):
    function = getattr(B, "_statement_shape_raw", None)
    assert callable(function), "raw statement metadata seam is missing"
    return function(value)


def raw_fields(kind, value):
    function = getattr(C, f"_validate_{kind}_spec", None)
    assert callable(function), "shared metadata validation seam is missing"
    return function(value, _reject=E._reject_validation)


def sample(kind):
    column = C.ColumnSpec(name="field", wire_type=C.WireType.INT8, nullable=False)
    result = C.ResultSpec(
        record=C.RecordKind.XID, cardinality=C.CardinalityKind.EXACT_ONE, columns=(column,)
    )
    return {
        "parameter": lambda: C.ParameterSpec(
            name="field",
            wire_type=C.WireType.BYTEA,
            nullable=False,
            constraint=C.ConstraintId.EVENT_ID,
        ),
        "column": lambda: column,
        "result": lambda: result,
        "statement": lambda: C.StatementSpec(
            key="E14", contract_id="modkit-pg-ab-2", parameters=(), result=result, mutation=True
        ),
    }[kind]()


@contextmanager
def fault_at(name, primary):
    function = getattr(C, name, None)
    assert callable(function), "shared metadata validation seam is missing"
    code, original = function.__code__, sys.gettrace()
    assert original is None

    def inject(frame, event, arg):
        if frame.f_code is code and event == "line":
            raise primary
        return inject

    try:
        sys.settrace(inject)
        yield
    finally:
        sys.settrace(original)


@pytest.mark.parametrize("key", ["E05", "E14", "E28"])
def test_raw_shape_accepts_only_actual_selected_catalog_instances(key):
    actual = C.get_statement(key)
    assert raw_shape(actual) is None
    assert B._statement_shape(actual) is None
    assert type(capture(lambda: raw_shape(replace(actual)))) is E._ValidationReject


@pytest.mark.parametrize("key", ["E01", "E02", "E04", "E34"])
def test_unselected_canonical_statement_fails_before_raw_field_validation(key):
    primary = RuntimeError("unselected metadata was traversed")
    with fault_at("_validate_statement_spec", primary):
        error = capture(lambda: raw_shape(C.get_statement(key)))
    assert type(error) is E._ValidationReject


def test_forged_or_foreign_object_fails_before_field_callbacks():
    class Hostile:
        def __getattribute__(self, name):
            raise AssertionError("foreign metadata was inspected")

    for value in (None, {}, Hostile(), replace(C.get_statement("E28"))):
        assert type(capture(lambda: raw_shape(value))) is E._ValidationReject


@pytest.mark.parametrize("kind", ["parameter", "column", "result", "statement"])
def test_shared_fields_validate_complete_valid_public_carriers(kind):
    value = sample(kind)
    assert raw_fields(kind, value) is None
    assert value.__post_init__() is None


@pytest.mark.parametrize(
    "kind, field, bad, error_type, message",
    [
        ("parameter", "name", "", ValueError, "invalid metadata name"),
        ("parameter", "wire_type", "bytea", TypeError, "invalid parameter metadata"),
        ("parameter", "nullable", 1, TypeError, "invalid parameter metadata"),
        ("parameter", "constraint", "event_id", TypeError, "invalid parameter metadata"),
        ("column", "name", "not-ascii-é", ValueError, "invalid metadata name"),
        ("column", "wire_type", None, TypeError, "invalid column metadata"),
        ("column", "nullable", None, TypeError, "invalid column metadata"),
        ("result", "record", "xid", TypeError, "invalid result metadata"),
        ("result", "cardinality", None, TypeError, "invalid result metadata"),
        ("result", "columns", (), TypeError, "invalid metadata sequence"),
        ("result", "columns", [], TypeError, "invalid metadata sequence"),
        ("result", "columns", (None,), TypeError, "invalid metadata sequence"),
        ("statement", "contract_id", "other", ValueError, "invalid contract identifier"),
        ("statement", "parameters", [], TypeError, "invalid metadata sequence"),
        ("statement", "parameters", (None,), TypeError, "invalid metadata sequence"),
        ("statement", "result", None, TypeError, "invalid statement metadata"),
        ("statement", "mutation", 1, TypeError, "invalid statement metadata"),
    ],
    ids=[f"field-{i}" for i in range(17)],
)
def test_raw_deliberate_field_rejections_preserve_public_type_message_and_context(
    kind, field, bad, error_type, message
):
    value = sample(kind)
    object.__setattr__(value, field, bad)
    error = capture(lambda: raw_fields(kind, value))
    assert type(error) is E._ValidationReject and error.args == ()
    ambient = RuntimeError("ambient")
    try:
        raise ambient
    except RuntimeError:
        public = capture(value.__post_init__)
    assert type(public) is error_type and public.args == (message,)
    assert public.__context__ is ambient
    assert public.__cause__ is None and public.__suppress_context__ is False


@pytest.mark.parametrize("key", ["E00", "E35", "W00", "W06", "E-1", "X14", "E١٤", None, 14])
def test_statement_key_domains_keep_original_public_errors(key):
    value = sample("statement")
    object.__setattr__(value, "key", key)
    assert type(capture(lambda: raw_fields("statement", value))) is E._ValidationReject
    public = capture(value.__post_init__)
    assert type(public) is ValueError and public.args == ("invalid statement key",)


@pytest.mark.parametrize(
    "kind, field, child",
    [
        ("result", "columns", "column"),
        ("statement", "parameters", "parameter"),
    ],
)
def test_duplicate_names_are_rejected_by_the_single_sequence_authority(kind, field, child):
    value, item = sample(kind), sample(child)
    object.__setattr__(value, field, (item, replace(item)))
    assert type(capture(lambda: raw_fields(kind, value))) is E._ValidationReject
    public = capture(value.__post_init__)
    assert type(public) is ValueError and public.args == ("duplicate metadata name",)


@pytest.mark.parametrize(
    "helper, kind",
    [
        ("_validate_statement_spec", "statement"),
        ("_validate_result_spec", "result"),
        ("_validate_parameter_spec", "parameter"),
        ("_validate_column_spec", "column"),
        ("_name", "parameter"),
        ("_tuple", "result"),
    ],
)
@pytest.mark.parametrize(
    "error_type", [MemoryError, RuntimeError, ValueError, TypeError, BaseException]
)
def test_raw_and_public_shared_metadata_faults_keep_the_exact_primary(helper, kind, error_type):
    primary = error_type("opaque")
    received = capture(lambda: (_ for _ in ()).throw(primary)).__traceback__
    cause, context = LookupError("cause"), OSError("context")
    primary.__cause__, primary.__context__ = cause, context
    primary.__suppress_context__ = False
    public_value = sample(kind)
    with fault_at(helper, primary):
        error = capture(lambda: raw_shape(C.get_statement("E28")))
    assert error is primary
    assert error.__cause__ is cause and error.__context__ is context
    assert error.__suppress_context__ is False
    trace = error.__traceback__
    while trace is not None and trace is not received:
        trace = trace.tb_next
    assert trace is received
    with fault_at(helper, primary):
        assert capture(public_value.__post_init__) is primary


@pytest.mark.parametrize("fields", [{}, {"key": "E14"}, {"key": "E28"}, {"result": None}])
def test_exact_but_uninitialized_carrier_is_rejected_before_reading_slots(fields):
    # Reading key before proving identity would turn this into AttributeError.
    value = object.__new__(C.StatementSpec)
    for name, content in fields.items():
        object.__setattr__(value, name, content)
    assert type(capture(lambda: raw_shape(value))) is E._ValidationReject


def test_selected_identity_must_still_match_its_catalog_key(monkeypatch):
    # Controlled registry fault, without changing any canonical descriptor.
    original = C.get_statement
    misplaced = replace(original("E28"))

    def inconsistent_lookup(key):
        return misplaced if key == "E14" else original(key)

    monkeypatch.setattr(C, "get_statement", inconsistent_lookup)
    assert type(capture(lambda: raw_shape(misplaced))) is E._ValidationReject
