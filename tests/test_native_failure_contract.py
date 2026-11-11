"""Pure fixed E11 contracts; no driver or database qualification."""

from dataclasses import replace
from datetime import datetime, timezone
from sys import getsizeof
from uuid import UUID

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import managed_lifecycle as M
from modkit_events.persistence import rows as R
from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.models import Fence

U = UUID(int=2**128 - 1)
F = Fence(work_id=U, token=U, ownership_revision=2**63 - 1, cycle=1, expected_attempt=1000)


def request(*, outcome="failed", large=False):
    retry = datetime(9999, 12, 31, tzinfo=timezone.utc) if outcome == "retry_waiting" else None
    parameters = (
        U,
        U,
        2**63 - 1,
        1,
        1000,
        2**64 - 1,
        outcome,
        retry,
        "r" * (256 if large else 1),
        b"e" * (1048576 if large else 1),
    )
    return B._freeze_request_raw(
        get_statement("E11"), parameters, context=B._return_context_raw(expected=(F,))
    )


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "retry_waiting"])
def test_fixed_e11_true_result_preserves_request(outcome):
    req = request(outcome=outcome)
    parameters, context = req.parameters, req.context
    assert R._decode_native_event_result_raw(req, ((True,),)) is True
    assert R._decode_event_rows_raw(req, ((True,),)) is True
    assert req.parameters is parameters and req.context is context


@pytest.mark.parametrize("rows", [(), ((False,),), ((1,),), ((None,),), ((True,), (True,))])
def test_e11_rejects_missing_false_or_multiple_result(rows):
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(request(), rows)


@pytest.mark.parametrize(
    "index,value",
    [
        (0, UUID(int=1)),
        (2, 0),
        (3, True),
        (4, 1001),
        (5, 0),
        (5, 2**64),
        (5, True),
        (6, "safe_retry"),
        (6, "FAILED"),
        (7, datetime.now(timezone.utc)),
        (8, ""),
        (8, "A"),
        (8, "a-b"),
        (8, "a" * 257),
        (8, "é"),
        (9, bytearray(b"x")),
        (9, memoryview(b"x")),
        (9, b"x" * 1048577),
    ],
)
def test_e11_raw_request_rejects_invalid_domain(index, value):
    req = request()
    params = list(req.parameters)
    params[index] = value
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, tuple(params), context=req.context)


def test_retry_requires_timestamp():
    req = request(outcome="retry_waiting")
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(
            req.statement, req.parameters[:7] + (None,) + req.parameters[8:], context=req.context
        )


def test_exact_selected_request_and_context():
    req = request()
    for statement, params, context in (
        (replace(req.statement), req.parameters, req.context),
        (req.statement, list(req.parameters), req.context),
        (req.statement, req.parameters, B._return_context_raw()),
    ):
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(statement, params, context=context)


def test_maximum_request_occurrence_accounting():
    req = request(outcome="retry_waiting", large=True)

    def size(value):
        return getsizeof(value) + (getsizeof(value.int) if type(value) is UUID else 0)

    expected = (
        getsizeof(req)
        + getsizeof(req.parameters)
        + sum(map(size, req.parameters))
        + getsizeof(req.context)
        + getsizeof(req.context.expected)
        + getsizeof(F)
        + sum(size(getattr(F, name)) for name in F.__dataclass_fields__)
    )
    assert M._preparation_size(req) == expected
    # Conservative recommendation, qualified for this interpreter only.
    assert expected <= 1053184


def test_raw_path_does_not_call_public_constructor_boundaries(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("public constructor used")

    for cls in (Fence, B.ReturnContext, B.FrozenRequest):
        monkeypatch.setattr(cls, "__post_init__", forbidden)
    req = request()
    assert R._decode_native_event_result_raw(req, ((True,),)) is True
    M._preparation_size(req)
