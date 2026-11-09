"""E33 raw entry gates; no driver or database."""

from dataclasses import replace

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import observations as O
from modkit_events.persistence import rows as R
from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.errors import _ValidationReject


def expectation(profile="workers"):
    return B.ReadinessExpectation(
        components=tuple(
            O.SchemaStatus(
                component=name,
                version=1,
                migration_digest=b"x" * 32,
                catalog_contract_id="modkit-pg-ab-2",
                scope_format_id="MKSC-1",
                intent_format_id="MKPF-1",
            )
            for name in (("events",) if profile == "events" else ("events", "workers"))
        )
    )


def request(profile="workers"):
    exp = expectation(profile)
    return B._freeze_request_raw(
        get_statement("E33"), (profile,), context=B._return_context_raw(readiness=exp)
    )


@pytest.mark.parametrize("profile", ["events", "workers"])
def test_e33_raw_freeze_accepts_both_profiles_without_public_boundaries(profile, monkeypatch):
    exp = expectation(profile)

    def forbidden(*args, **kwargs):
        raise AssertionError("public boundary")

    monkeypatch.setattr(O.SchemaStatus, "__post_init__", forbidden)
    monkeypatch.setattr(B.ReadinessExpectation, "__post_init__", forbidden)
    ctx = B._return_context_raw(readiness=exp)
    req = B._freeze_request_raw(get_statement("E33"), (profile,), context=ctx)
    assert req.context is ctx and ctx.readiness is exp
    assert ctx.readiness.components is exp.components
    assert req.parameters == (profile,)
    B._freeze_parameters(req.statement, req.parameters, ctx, _reject=B._reject_validation)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 0),
        ("version", 2**31),
        ("migration_digest", bytearray(32)),
        ("migration_digest", b"x" * 31),
        ("component", "worker"),
        ("catalog_contract_id", "wrong"),
        ("scope_format_id", "wrong"),
        ("intent_format_id", "wrong"),
    ],
)
def test_e33_tampered_expectation_rejected(field, value):
    exp = expectation()
    object.__setattr__(exp.components[0], field, value)
    with pytest.raises(_ValidationReject):
        B._return_context_raw(readiness=exp)


def test_e33_missing_field_rejected():
    exp = expectation()
    object.__delattr__(exp.components[0], "version")
    with pytest.raises(_ValidationReject):
        B._return_context_raw(readiness=exp)


@pytest.mark.parametrize("profile", [None, "", "EVENTS", "jobs", 1])
def test_e33_raw_required_profile_gate(profile):
    ctx = B.ReturnContext(expected=(), readiness=expectation())
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(get_statement("E33"), (profile,), context=ctx)


def test_e33_raw_identity_and_profile_coupling():
    req = request()
    for spec, params in [
        (replace(get_statement("E33")), ("workers",)),
        (get_statement("E33"), ("events",)),
        (get_statement("E14"), ()),
    ]:
        with pytest.raises(_ValidationReject):
            B._freeze_request_raw(spec, params, context=req.context)
    values = ("events", 1, b"x" * 32, "modkit-pg-ab-2", "MKSC-1", "MKPF-1")
    assert R._decode_columns_raw(get_statement("E33").result.columns, values) == values
    with pytest.raises(_ValidationReject):
        R._decode_columns_raw(
            tuple(replace(c) for c in get_statement("E33").result.columns), values
        )


def test_e33_raw_result_order_and_semantics():
    req = request()
    vals = tuple(
        tuple(getattr(v, c.name) for c in req.statement.result.columns)
        for v in req.context.readiness.components
    )
    assert R._decode_native_readiness_result_raw(req, vals) == req.context.readiness.components
    for bad in ((), vals[:1], vals[::-1], vals + vals[:1], (vals[0], vals[0])):
        with pytest.raises(_ValidationReject):
            R._decode_native_readiness_result_raw(req, bad)
    # Valid differing observation remains observable, for issuer mismatch classification.
    changed = (("events", 2, b"y" * 32, "different", "scope", "intent"), vals[1])
    assert R._decode_native_readiness_result_raw(req, changed)[0].version == 2


def test_e33_raw_subclasses_and_collection_hooks_are_never_called():
    class Hooked(str):
        def __eq__(self, other):
            raise AssertionError("equality hook")

        def encode(self, *args, **kwargs):
            raise AssertionError("encoding hook")

    class HookedTuple(tuple):
        def __iter__(self):
            raise AssertionError("iterator hook")

    class HookedBytes(bytes):
        def __len__(self):
            raise AssertionError("length hook")

    for field, value in (
        ("component", Hooked("events")),
        ("catalog_contract_id", Hooked("modkit-pg-ab-2")),
        ("migration_digest", HookedBytes(b"x" * 32)),
    ):
        exp = expectation()
        object.__setattr__(exp.components[0], field, value)
        with pytest.raises(_ValidationReject):
            B._return_context_raw(readiness=exp)
    exp = expectation()
    object.__setattr__(exp, "components", HookedTuple(exp.components))
    with pytest.raises(_ValidationReject):
        B._return_context_raw(readiness=exp)
    ctx = B._return_context_raw(readiness=expectation())
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(get_statement("E33"), (Hooked("workers"),), context=ctx)


def test_e33_raw_nonreadiness_gates_still_reject_expansion():
    exp = expectation()
    for expected in ((object(),), [], (exp.components[0],)):
        with pytest.raises(_ValidationReject):
            B._return_context_raw(expected=expected, readiness=exp)
    ctx = B._return_context_raw()
    req = B._freeze_request_raw(get_statement("E14"), (), context=ctx)
    assert req.context.readiness is None
    with pytest.raises(_ValidationReject):
        B._freeze_request_raw(get_statement("E31"), (), context=ctx)
