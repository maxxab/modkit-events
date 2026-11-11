"""Pure E32 contracts and occurrence graphs; no native/database proof."""

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
from modkit_events.persistence.observations import SettlementObservation

U = UUID(int=2**128 - 1)
F = Fence(work_id=U, token=U, ownership_revision=2**63 - 2, cycle=1, expected_attempt=1000)


def request(*, large=False, alias=False, xid=2**64 - 1):
    evidence = b"e" * (1048576 if large else 1)
    binding = evidence if alias else b"b" * len(evidence)
    return B._freeze_request_raw(
        get_statement("E32"),
        (
            U,
            U,
            F.ownership_revision,
            1,
            1000,
            xid,
            U,
            "r" * (256 if large else 1),
            evidence,
            binding,
        ),
        context=B._return_context_raw(expected=(F,)),
    )


def values(req):
    p = req.parameters
    return (
        p[6],
        p[0],
        p[1],
        p[2],
        p[3],
        p[4],
        U,
        p[5],
        p[7],
        p[8],
        p[9],
        p[2] + 1,
        datetime(9999, 12, 31, tzinfo=timezone.utc),
    )


def scalar_size(value):
    return getsizeof(value) + (getsizeof(value.int) if type(value) is UUID else 0)


def occurrence_sizes(req, result):
    a = (
        getsizeof(req)
        + getsizeof(req.parameters)
        + sum(map(scalar_size, req.parameters))
        + getsizeof(req.context)
        + getsizeof(req.context.expected)
    )
    for fence in req.context.expected:
        a += getsizeof(fence) + sum(
            scalar_size(getattr(fence, n)) for n in fence.__dataclass_fields__
        )
    b = getsizeof(result) + sum(
        scalar_size(getattr(result, n)) for n in result.__dataclass_fields__
    )
    return a, b


def test_exact_settlement_decoding_and_request_identity():
    req = request()
    params, context = req.parameters, req.context
    row = R._decode_native_event_result_raw(req, (values(req),))
    assert type(row) is SettlementObservation
    assert tuple(getattr(row, n) for n in row.__dataclass_fields__) == values(req)
    assert R._decode_event_rows_raw(req, (values(req),)) == row
    assert req.parameters is params and req.context is context
    assert row == R.decode_event_rows(req, (values(req),))


@pytest.mark.parametrize("index", range(10))
def test_every_request_field_is_coupled(index):
    req = request()
    row = list(values(req))
    target = (1, 2, 3, 4, 5, 7, 0, 8, 9, 10)[index]
    value = row[target]
    row[target] = (
        UUID(int=1)
        if type(value) is UUID
        else value + 1
        if type(value) is int
        else value + "x"
        if type(value) is str
        else value + b"x"
    )
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize(
    "index,value",
    [
        (0, UUID(int=1)),
        (2, 0),
        (3, True),
        (4, 1001),
        (5, 0),
        (5, -1),
        (5, True),
        (5, 2**64),
        (6, None),
        (7, ""),
        (7, "A"),
        (7, "a-b"),
        (7, "é"),
        (7, "a" * 257),
        (8, bytearray(b"x")),
        (8, b"x" * 1048577),
        (9, memoryview(b"x")),
        (9, b"x" * 1048577),
    ],
)
def test_raw_request_invalid_domain(index, value):
    req = request()
    params = list(req.parameters)
    params[index] = value
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, tuple(params), context=req.context)


@pytest.mark.parametrize(
    "index,value",
    [
        (6, None),
        (6, "uuid"),
        (11, 2**63),
        (11, 2**63 - 2),
        (11, True),
        (12, datetime(2026, 1, 1)),
        (12, None),
    ],
)
def test_return_only_fields_are_validated(index, value):
    req = request()
    row = list(values(req))
    row[index] = value
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize("rows", [(), ((),), ((1,),), ((), ()), []])
def test_exact_row_cardinality(rows):
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(request(), rows)


def test_canonical_revision_parity_and_historical_dispatch():
    req = request()
    params = req.parameters[:2] + (3,) + req.parameters[3:]
    fence = replace(F, ownership_revision=3)
    req = B._freeze_request_raw(
        req.statement, params, context=B._return_context_raw(expected=(fence,))
    )
    row = list(values(req))
    row[6] = UUID(int=123)
    row[11] = 9
    decoded = R._decode_native_event_result_raw(req, (tuple(row),))
    assert decoded.dispatch_id == UUID(int=123) and decoded.resulting_revision == 9


def test_exact_selected_request_and_context():
    req = request()
    for spec, params, context in [
        (replace(req.statement), req.parameters, req.context),
        (req.statement, list(req.parameters), req.context),
        (req.statement, req.parameters[:-1], req.context),
        (req.statement, req.parameters, B._return_context_raw()),
    ]:
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(spec, params, context=context)


@pytest.mark.parametrize("alias", [False, True])
def test_maximum_occurrence_graph_sizes(alias):
    req = request(large=True, alias=alias)
    result = R._decode_native_event_result_raw(req, (values(req),))
    a, b = occurrence_sizes(req, result)
    assert M._preparation_size(req) == a
    assert M._typed_result_size(req, result) == b
    assert a > 2 * 1048576 and b > 2 * 1048576
    if alias:
        assert req.parameters[8] is req.parameters[9]
        assert result.evidence is result.binding


def test_public_constructor_boundaries_not_nested(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("public constructor used")

    for cls in (Fence, B.ReturnContext, B.FrozenRequest, SettlementObservation):
        monkeypatch.setattr(cls, "__post_init__", forbidden)
    req = request()
    row = R._decode_native_event_result_raw(req, (values(req),))
    M._typed_result_size(req, row)
