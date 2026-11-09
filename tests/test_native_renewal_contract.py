"""E05 canonical scalar/row/accounting contracts, not native qualification."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import nextafter
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
STAMP = datetime(2000, 1, 1, tzinfo=timezone.utc)


def request(seconds=3600, *, fence=F):
    return B._freeze_request_raw(
        get_statement("E05"),
        (fence.work_id, fence.token, fence.ownership_revision, 1, fence.expected_attempt, seconds),
        context=B._return_context_raw(expected=(fence,)),
    )


def occurrence_size(req):
    def scalar(value):
        return getsizeof(value) + (getsizeof(value.int) if type(value) is UUID else 0)

    return (
        getsizeof(req)
        + getsizeof(req.parameters)
        + sum(scalar(v) for v in req.parameters)
        + getsizeof(req.context)
        + getsizeof(req.context.expected)
        + getsizeof(F)
        + sum(scalar(getattr(F, n)) for n in F.__dataclass_fields__)
    )


@pytest.mark.parametrize("seconds", [1, 3600, 0.1, 5e-324, nextafter(3600.0, 0.0)])
def test_constructor_normalizes_canonical_domain_without_rounding(seconds):
    req = request(seconds)
    assert type(req.parameters[5]) is float
    assert req.parameters[5].hex() == float(seconds).hex()
    public = B.freeze_request(req.statement, req.parameters[:5] + (seconds,), context=req.context)
    assert req == public
    assert R._decode_native_event_result_raw(req, ((STAMP,),)) == STAMP
    assert R._decode_event_rows_raw(req, ((STAMP,),)) == R.decode_event_rows(public, ((STAMP,),))
    assert M._typed_result_size(req, STAMP) == getsizeof(STAMP)


class FloatSubclass(float):
    pass


class IntSubclass(int):
    pass


@pytest.mark.parametrize(
    "seconds",
    [
        True,
        False,
        0,
        -0.0,
        -1,
        3601,
        nextafter(3600.0, float("inf")),
        float("nan"),
        float("inf"),
        -float("inf"),
        10**1000,
        "1",
        None,
        FloatSubclass(1),
        IntSubclass(1),
    ],
)
def test_invalid_duration_rejects_privately_before_io(seconds):
    with pytest.raises(_ValidationReject):
        request(seconds)


@pytest.mark.parametrize("index", range(5))
def test_all_fence_fields_remain_coupled(index):
    req = request()
    p = list(req.parameters)
    p[index] = UUID(int=1) if index < 2 else p[index] - 1
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, tuple(p), context=req.context)


def test_selected_identity_context_and_tuple_are_required():
    req = request()
    for spec, params, context in [
        (replace(req.statement), req.parameters, req.context),
        (req.statement, list(req.parameters), req.context),
        (req.statement, req.parameters[:-1], req.context),
        (req.statement, req.parameters, B._return_context_raw()),
    ]:
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(spec, params, context=context)


def test_forged_retained_integer_is_not_renormalized():
    req = request(1)
    object.__setattr__(req, "parameters", req.parameters[:5] + (1,))
    for check in (
        lambda: M._preparation_size(req),
        lambda: R._decode_native_event_result_raw(req, ((STAMP,),)),
        lambda: M._typed_result_size(req, STAMP),
    ):
        with pytest.raises(_ValidationReject):
            check()


@pytest.mark.parametrize("rows", [(), ((),), ((STAMP, STAMP),), ((STAMP,), (STAMP,)), []])
def test_exact_one_timestamp_cardinality(rows):
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(request(), rows)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        "2000-01-01",
        datetime(2000, 1, 1),
        datetime(2000, 1, 1, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_noncanonical_return_timestamp_rejected(value):
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(request(), ((value,),))


def test_maximum_graph_counts_alias_occurrences():
    req = request()
    assert req.parameters[0] is req.parameters[1] is F.work_id is F.token
    assert M._preparation_size(req) == occurrence_size(req)
    assert M._typed_result_size(req, STAMP) == getsizeof(STAMP)
    assert occurrence_size(req) <= 1024
    assert getsizeof(STAMP) <= 64


def test_public_sanitizers_are_not_nested(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("public constructor used")

    for cls in (Fence, B.ReturnContext, B.FrozenRequest):
        monkeypatch.setattr(cls, "__post_init__", forbidden)
    req = request()
    assert R._decode_native_event_result_raw(req, ((STAMP,),)) is STAMP
