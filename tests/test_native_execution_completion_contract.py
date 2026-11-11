"""Pure selected completion contracts; no driver or database execution."""

from sys import getsizeof
from uuid import UUID

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import managed_lifecycle as M
from modkit_events.persistence import rows as R
from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.models import Fence, GuardRef
from modkit_events.persistence.observations import GuardRow

U = UUID(int=2**128 - 1)
F = Fence(work_id=U, token=U, ownership_revision=2**63 - 1, cycle=1, expected_attempt=999)
G = GuardRef(
    guard_id=U,
    work_id=U,
    root_xid=2**64 - 1,
    token=U,
    ownership_revision=2**63 - 1,
    cycle=1,
    expected_attempt=999,
)


def request(key, *, large=False):
    expected = G if key == "E10" else F
    params = tuple(getattr(expected, name) for name in expected.__dataclass_fields__)
    if key == "E06":
        params += (U, b"x" * 256, b"e" * (1048576 if large else 1), b"y" * 256)
    elif key == "E10":
        params += (b"r" * (1048576 if large else 1),)
    return B._freeze_request_raw(
        get_statement(key), params, context=B._return_context_raw(expected=(expected,))
    )


def guard():
    return (U, U, 2**64 - 1, U, 2**63 - 1, 1, 999, False, None, None, None)


@pytest.mark.parametrize(
    "key,rows,expected", [("E06", ((1000,),), 1000), ("E09", (), None), ("E10", ((True,),), True)]
)
def test_complete_selected_scalar_and_absence(key, rows, expected):
    req = request(key)
    original = req.parameters
    assert R._decode_native_event_result_raw(req, rows) == expected
    assert req.parameters is original


@pytest.mark.parametrize("key", ["E08", "E09"])
def test_complete_guard_and_finite_retained_graph(key):
    req = request(key)
    result = R._decode_native_event_result_raw(req, (guard(),))
    assert type(result) is GuardRow
    assert tuple(getattr(result, c.name) for c in req.statement.result.columns) == guard()
    assert M._typed_result_size(req, result) <= 4096


@pytest.mark.parametrize("key,cap", [("E06", 1053184), ("E10", 1052672)])
def test_maximum_request_domain_and_occurrence_accounting(key, cap):
    req = request(key, large=True)
    expected = req.context.expected[0]

    def size(value):
        return getsizeof(value) + (getsizeof(value.int) if type(value) is UUID else 0)

    want = (
        getsizeof(req)
        + getsizeof(req.parameters)
        + sum(map(size, req.parameters))
        + getsizeof(req.context)
        + getsizeof(req.context.expected)
        + getsizeof(expected)
        + sum(size(getattr(expected, n)) for n in expected.__dataclass_fields__)
    )
    assert M._preparation_size(req) == want
    assert want <= cap


@pytest.mark.parametrize(
    "key,rows",
    [
        ("E06", ()),
        ("E06", ((999,),)),
        ("E06", ((True,),)),
        ("E10", ((False,),)),
        ("E10", ((1,),)),
        ("E10", ()),
        ("E08", ()),
        ("E09", (guard(), guard())),
    ],
)
def test_rejects_incomplete_or_uncoupled_result(key, rows):
    req = request(key)
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, rows)


@pytest.mark.parametrize(
    "index,value",
    [
        (2, 0),
        (4, 0),
        (5, True),
        (6, 0),
        (7, True),
        (8, 1),
        (9, "succeeded"),
        (10, b"d" * 32),
        (0, UUID(int=1)),
    ],
)
def test_guard_field_validation_and_coupling(index, value):
    req = request("E08")
    row = list(guard())
    row[index] = value
    if index == 0:  # guard_id has no requested value and may legitimately differ.
        row[1] = value
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize(
    "key,rows,cap", [("E06", ((1000,),), 64), ("E10", ((True,),), 64), ("E09", (), 64)]
)
def test_scalar_result_recommendations(key, rows, cap):
    req = request(key)
    result = R._decode_native_event_result_raw(req, rows)
    assert M._typed_result_size(req, result) <= cap


@pytest.mark.parametrize("key", ["E06", "E08", "E09", "E10"])
def test_raw_entrypoint_supports_selected_contract(key):
    req = request(key)
    rows = ((1000,),) if key == "E06" else ((True,),) if key == "E10" else (guard(),)
    assert R._decode_event_rows_raw(req, rows) == R._decode_native_event_result_raw(req, rows)


def test_selected_path_avoids_public_constructors(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("public boundary reached")

    for cls in (Fence, GuardRef, GuardRow, B.ReturnContext, B.FrozenRequest):
        monkeypatch.setattr(cls, "__post_init__", forbidden)
    for key, rows in (("E06", ((1000,),)), ("E08", (guard(),)), ("E09", ()), ("E10", ((True,),))):
        req = request(key)
        result = R._decode_native_event_result_raw(req, rows)
        M._preparation_size(req)
        M._typed_result_size(req, result)


@pytest.mark.parametrize("key", ["E06", "E10"])
def test_paid_preparation_capacity_equality_and_one_byte_short(key):
    from test_managed_statement_lifecycle import run

    run(
        """
    from pathlib import Path
    sys.path.insert(0,str(Path(SOURCE).parent/'tests'))
    from test_native_execution_completion_contract import request as completion_request
    L,x,actual,c=setup_physical()
    req=completion_request(KEY,large=True)
    size=m._preparation_size(req)
    a=m.reserve_preparation(x,size-1,execution_ledger=L)
    expect(E.CAPACITY_EXCEEDED,lambda:m.set_preparation(a,req,execution_ledger=L))
    m.release_preparation(a,execution_ledger=L)
    a=m.reserve_preparation(x,size,execution_ledger=L)
    m.set_preparation(a,req,execution_ledger=L)
    assert m.capacity_snapshot(execution_ledger=L)['AB']==size
    assert not L.uncertainty.present
    print('MANAGED_BODY_COMPLETE')
    """.replace("KEY", repr(key))
    )


@pytest.mark.parametrize(
    "key,absent", [("E06", False), ("E08", False), ("E09", False), ("E09", True), ("E10", False)]
)
def test_paid_result_capacity_equality_and_one_byte_short(key, absent):
    from test_managed_statement_lifecycle import run

    for short in (False, True):
        run(
            """
        from pathlib import Path
        sys.path.insert(0,str(Path(SOURCE).parent/'tests'))
        from test_native_execution_completion_contract import request as completion_request,guard
        from modkit_events.persistence.rows import _decode_native_event_result_raw
        L,x,actual,c=setup_physical()
        req=completion_request(KEY)
        rows=() if ABSENT else ((1000,),) if KEY=='E06' else ((True,),) if KEY=='E10' else (guard(),)
        result=_decode_native_event_result_raw(req,rows)
        a=m.reserve_preparation(x,4096,execution_ledger=L)
        m.set_preparation(a,req,execution_ledger=L)
        r=active_root(c,L)
        t=m.admit(r,a,execution_ledger=L)
        size=m._typed_result_size(req,result)
        b=m.reserve_result(t,size-int(SHORT),execution_ledger=L)
        m._start_operation(t,b,L)
        if SHORT:
            expect(E.CAPACITY_EXCEEDED,lambda:m.set_result(b,result,execution_ledger=L))
        else:
            m.set_result(b,result,execution_ledger=L)
            m._complete_operation(t,L,known=True)
            assert m.read_result(b,execution_ledger=L) is result
        print('MANAGED_BODY_COMPLETE')
        """.replace("KEY", repr(key))
            .replace("ABSENT", repr(absent))
            .replace("SHORT", repr(short))
        )


@pytest.mark.parametrize("key", ["E06", "E08", "E09", "E10"])
def test_revalidates_exact_context_and_scalar_graph(key):
    from dataclasses import replace

    req = request(key)
    for name, value in (
        ("statement", replace(req.statement)),
        ("parameters", list(req.parameters)),
    ):
        bad = object.__new__(B.FrozenRequest)
        for attr in ("statement", "parameters", "context"):
            object.__setattr__(bad, attr, value if name == attr else getattr(req, attr))
        with pytest.raises(_ValidationReject):
            M._preparation_size(bad)
    expected = req.context.expected[0]
    for name, value in (
        ("cycle", True),
        ("expected_attempt", 1001),
        ("ownership_revision", 0),
        ("work_id", "invalid"),
    ):
        bad = object.__new__(type(expected))
        for attr in expected.__dataclass_fields__:
            object.__setattr__(bad, attr, value if name == attr else getattr(expected, attr))
        with pytest.raises(_ValidationReject):
            B._return_context_raw(expected=(bad,))


@pytest.mark.parametrize("key", ["E06", "E10"])
def test_request_bytes_are_immutable_and_bounded(key):
    req = request(key)
    index = 7
    for value in (bytearray(b"x"), memoryview(b"x"), b"x" * 1048577):
        params = list(req.parameters)
        params[index] = value
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(req.statement, tuple(params), context=req.context)


def test_context_coupling_and_attempt_overflow():
    from dataclasses import replace

    req = request("E06")
    params = (UUID(int=1),) + req.parameters[1:]
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, params, context=req.context)
    fence = replace(F, expected_attempt=1000)
    params = req.parameters[:4] + (1000,) + req.parameters[5:]
    overflow = B._freeze_request_raw(
        req.statement, params, context=B._return_context_raw(expected=(fence,))
    )
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(overflow, ((1001,),))


def test_uuid_backing_is_validated_before_sizing():
    for value in (True, -1, 2**128):
        bad_uuid = object.__new__(UUID)
        object.__setattr__(bad_uuid, "int", value)
        object.__setattr__(bad_uuid, "is_safe", U.is_safe)
        bad_fence = object.__new__(Fence)
        for name in F.__dataclass_fields__:
            object.__setattr__(bad_fence, name, bad_uuid if name == "work_id" else getattr(F, name))
        with pytest.raises(_ValidationReject):
            B._return_context_raw(expected=(bad_fence,))


def test_result_revalidation_rejects_mutated_retained_guard():
    req = request("E08")
    for name, value in (("work_id", UUID(int=1)), ("satisfied", True), ("root_xid", "7")):
        result = R._decode_native_event_result_raw(req, (guard(),))
        object.__setattr__(result, name, value)
        with pytest.raises(_ValidationReject):
            M._typed_result_size(req, result)
