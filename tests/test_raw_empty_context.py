"""Pure selected empty ReturnContext construction without sanitizing faults."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import errors as E


def capture(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


def raw(*, expected=(), readiness=None):
    function = getattr(B, "_return_context_raw", None)
    assert callable(function), "raw empty context factory is missing"
    return function(expected=expected, readiness=readiness)


def test_raw_empty_context_has_exact_type_fields_and_frozen_contract():
    context = raw()
    assert type(context) is B.ReturnContext
    assert context.expected == () and type(context.expected) is tuple and context.readiness is None
    assert context == B.ReturnContext(expected=(), readiness=None)
    with pytest.raises(FrozenInstanceError):
        context.expected = (None,)


@pytest.mark.parametrize("expected", [None, [], [None], (None,), (None, None), "", 0])
def test_raw_context_rejects_nonempty_or_non_exact_tuple(expected):
    assert type(capture(lambda: raw(expected=expected))) is E._ValidationReject


def test_raw_context_rejects_tuple_subclass_without_foreign_truthiness():
    class Foreign(tuple):
        def __len__(self):
            raise AssertionError("foreign length")

    assert type(capture(lambda: raw(expected=Foreign()))) is E._ValidationReject


@pytest.mark.parametrize("readiness", [False, 0, (), {}, object()])
def test_raw_context_disallows_all_non_none_readiness(readiness):
    assert type(capture(lambda: raw(readiness=readiness))) is E._ValidationReject


def test_raw_context_does_not_run_foreign_expectation_callbacks():
    class Foreign:
        def __post_init__(self):
            raise AssertionError("foreign callback")

    assert type(capture(lambda: raw(expected=(Foreign(),)))) is E._ValidationReject


@pytest.mark.parametrize(
    "boundary", ["draft", "validator", "allocate", "expected_slot", "readiness_slot"]
)
@pytest.mark.parametrize(
    "error_type", [MemoryError, ValueError, TypeError, RuntimeError, BaseException]
)
def test_raw_context_preserves_unexpected_fault_identity_and_metadata(
    monkeypatch, boundary, error_type
):
    primary = error_type("opaque")
    previous = capture(lambda: (_ for _ in ()).throw(primary)).__traceback__
    cause, context = LookupError("cause"), OSError("context")
    primary.__cause__, primary.__context__, primary.__suppress_context__ = cause, context, False
    primary.add_note("retained note")
    primary.opaque = object()
    opaque = primary.opaque

    def fault(*args, **kwargs):
        raise primary

    def allocate(cls):
        if boundary == "allocate":
            raise primary
        return object.__new__(cls)

    def assign(instance, name, value):
        if (boundary, name) in (("expected_slot", "expected"), ("readiness_slot", "readiness")):
            raise primary
        object.__setattr__(instance, name, value)

    if boundary == "draft":
        monkeypatch.setattr(B, "_ReturnContextDraft", fault, raising=False)
    elif boundary == "validator":
        monkeypatch.setattr(B, "_validate_return_context", fault, raising=False)
    else:
        monkeypatch.setattr(
            B, "object", SimpleNamespace(__new__=allocate, __setattr__=assign), raising=False
        )
    caught = capture(lambda: raw())
    assert caught is primary
    assert (
        caught.__cause__ is cause
        and caught.__context__ is context
        and caught.__suppress_context__ is False
    )
    assert caught.__notes__ == ["retained note"] and caught.opaque is opaque
    trace = caught.__traceback__
    while trace is not None and trace is not previous:
        trace = trace.tb_next
    assert trace is previous


@pytest.mark.parametrize("expected,readiness", [([], None), ((None,), None), ((), object())])
def test_public_context_invalid_policy_remains_detached(expected, readiness):
    caught = capture(lambda: B.ReturnContext(expected=expected, readiness=readiness))
    assert type(caught) is E.PersistenceError
    assert caught.code is E.ErrorCode.LOCAL_INVALID_ARGUMENT
    assert (
        caught.__cause__ is None
        and caught.__context__ is None
        and caught.__suppress_context__ is True
    )


def test_raw_shared_validator_accepts_trusted_fence_without_constructor_callback(monkeypatch):
    from uuid import UUID

    fence = B.Fence(
        work_id=UUID(int=1), token=UUID(int=2), ownership_revision=1, cycle=1, expected_attempt=0
    )
    context = B.ReturnContext(expected=(fence,), readiness=None)

    def fault(*args, **kwargs):
        raise AssertionError("expectation callback reached")

    monkeypatch.setattr(B.Fence, "__post_init__", fault)
    assert B._validate_return_context(context, _reject=E._reject_validation) is None


def test_raw_factory_never_enters_public_context_validation(monkeypatch):
    original = B._validate_return_context

    def validate(context, *, _reject=None):
        if _reject is None:
            raise RuntimeError("public validation reached")
        return original(context, _reject=_reject)

    monkeypatch.setattr(B, "_validate_return_context", validate)
    assert type(raw()) is B.ReturnContext
