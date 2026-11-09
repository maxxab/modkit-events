"""Pure E31 contracts; no driver or durable-outcome claim."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from sys import getsizeof
from uuid import UUID

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import rows as R
from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.observations import ResolutionObservation

OUTCOMES = ("confirmed_success", "confirmed_rejection", "confirmed_cancelled", "safe_retry")
NOW = datetime(2000, 1, 1, tzinfo=timezone.utc)
U = UUID(int=2**128 - 1)


def request(outcome="confirmed_success", *, large=False, alias=False):
    evidence = b"e" * (1048576 if large else 1)
    binding = evidence if alias else b"b" * len(evidence)
    result = evidence if alias else b"r" * len(evidence)
    return B._freeze_request_raw(
        get_statement("E31"),
        (
            U,
            2**63 - 2,
            1,
            999,
            U,
            U,
            outcome,
            NOW if outcome == "safe_retry" else None,
            result if outcome == "confirmed_success" else None,
            evidence,
            binding,
        ),
        context=B._return_context_raw(),
    )


def values(req, *, root=2**64 - 1):
    p = req.parameters
    return (
        p[5],
        "reconcile_work",
        p[0],
        p[1],
        p[2],
        p[3],
        p[4],
        p[6],
        p[7],
        p[8],
        sha256(p[8]).digest() if p[8] is not None else None,
        None,
        p[9],
        p[10],
        root,
        NOW,
    )


def occurrence_sizes(req, value):
    def size(v):
        return getsizeof(v) + (getsizeof(v.int) if type(v) is UUID else 0)

    return (
        getsizeof(req)
        + getsizeof(req.parameters)
        + sum(map(size, req.parameters))
        + getsizeof(req.context)
        + getsizeof(req.context.expected),
        getsizeof(value) + sum(size(getattr(value, n)) for n in value.__dataclass_fields__),
    )


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_all_four_outcomes_raw(outcome):
    req = request(outcome)
    params = req.parameters
    result = R._decode_native_event_result_raw(req, (values(req),))
    assert type(result) is ResolutionObservation
    assert result == R._decode_event_rows_raw(req, (values(req),))
    assert req.parameters is params
    public_request = request(outcome)
    assert result == R.decode_event_rows(public_request, (values(public_request),))
    assert result.reason is None


@pytest.mark.parametrize("index", range(11))
def test_each_request_field_coupled(index):
    req = request("safe_retry" if index == 7 else "confirmed_success")
    row = list(values(req))
    target = (2, 3, 4, 5, 6, 0, 7, 8, 9, 12, 13)[index]
    old = row[target]
    row[target] = (
        UUID(int=1)
        if type(old) is UUID
        else old + 1
        if type(old) is int
        else old + timedelta(seconds=1)
        if type(old) is datetime
        else old + old
    )
    if target == 9:
        row[10] = sha256(row[9]).digest()
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize("root", [1, 2**63 - 1, 2**63, 2**64 - 1])
def test_historical_root_is_preserved(root):
    req = request()
    assert (
        R._decode_native_event_result_raw(req, (values(req, root=root),)).resolution_root_xid
        == root
    )


@pytest.mark.parametrize(
    "index,value",
    [
        (1, True),
        (1, -1),
        (1, 2**63),
        (2, 2),
        (3, 0),
        (3, 1001),
        (0, "uuid"),
        (6, "success"),
        (7, datetime(2000, 1, 1)),
        (9, bytearray(b"x")),
        (10, memoryview(b"x")),
        (9, b"x" * 1048577),
    ],
)
def test_raw_hostile_inputs(index, value):
    req = request("safe_retry" if index == 7 else "confirmed_success")
    p = list(req.parameters)
    p[index] = value
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, tuple(p), context=req.context)


@pytest.mark.parametrize(
    "index,value",
    [
        (1, "hold_uncertain"),
        (10, b"x" * 31),
        (10, b"x" * 32),
        (11, "reason"),
        (14, 0),
        (14, 2**64),
        (14, True),
        (15, datetime(2000, 1, 1)),
    ],
)
def test_invalid_return_fields(index, value):
    req = request()
    row = list(values(req))
    row[index] = value
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize("rows", [(), ((),), ((), ()), []])
def test_exact_cardinality(rows):
    with pytest.raises(_ValidationReject):
        R._decode_native_event_result_raw(request(), rows)


def test_empty_success_and_outcome_null_coupling():
    req = request()
    p = list(req.parameters)
    p[8] = b""
    req = B._freeze_request_raw(req.statement, tuple(p), context=req.context)
    assert (
        R._decode_native_event_result_raw(req, (values(req),)).result_digest == sha256(b"").digest()
    )
    for outcome in OUTCOMES:
        req = request(outcome)
        row = list(values(req))
        row[8] = None if outcome == "safe_retry" else NOW
        with pytest.raises(_ValidationReject):
            R._decode_native_event_result_raw(req, (tuple(row),))


@pytest.mark.parametrize("revision,attempt", [(0, 1), (2**63 - 1, 1000)])
def test_raw_e31_inclusive_integer_boundaries(revision, attempt):
    req = request()
    p = list(req.parameters)
    p[1] = revision
    p[3] = attempt
    frozen = B._freeze_request_raw(req.statement, tuple(p), context=req.context)
    assert frozen.parameters[1] == revision and frozen.parameters[3] == attempt


def test_raw_rejects_lookalike_metadata_sequences_and_hooks():
    from dataclasses import replace
    from datetime import tzinfo

    class IntSubclass(int):
        pass

    class StrSubclass(str):
        pass

    class HostileZone(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("timezone hook invoked")

    req = request()
    for spec, params, context in [
        (replace(req.statement), req.parameters, req.context),
        (req.statement, list(req.parameters), req.context),
        (req.statement, req.parameters[:-1], req.context),
        (req.statement, req.parameters, object()),
    ]:
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(spec, params, context=context)
    for index, v in [
        (1, IntSubclass(1)),
        (3, True),
        (6, StrSubclass("confirmed_success")),
        (7, datetime(2000, 1, 1, tzinfo=HostileZone())),
    ]:
        p = list(request("safe_retry" if index == 7 else "confirmed_success").parameters)
        p[index] = v
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(req.statement, tuple(p), context=req.context)
    bad = UUID(int=1)
    object.__setattr__(bad, "int", True)
    p = list(req.parameters)
    p[0] = bad
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(req.statement, tuple(p), context=req.context)


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_raw_request_outcome_cross_fields(outcome):
    req = request(outcome)
    for index, replacement in [
        (7, None if outcome == "safe_retry" else NOW),
        (8, None if outcome == "confirmed_success" else b"result"),
    ]:
        p = list(req.parameters)
        p[index] = replacement
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(req.statement, tuple(p), context=req.context)


def test_safe_retry_attempt1000_is_structurally_valid_for_sql_policy_decision():
    req = request("safe_retry")
    parameters = req.parameters[:3] + (1000,) + req.parameters[4:]
    frozen = B._freeze_request_raw(req.statement, parameters, context=req.context)
    assert frozen.parameters[3] == 1000
    assert frozen.parameters[6] == "safe_retry"
