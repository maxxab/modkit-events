"""Public canonical output caps under callback-driven array mutation."""

from collections.abc import Mapping

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import errors as E


def mutable_input(operation):
    outer = []

    class Mutator(Mapping):
        def __len__(self):
            return 0

        def __iter__(self):
            return iter(())

        def __getitem__(self, key):
            raise KeyError(key)

        def items(self):
            operation(outer)
            return ()

    outer.append(Mutator())
    return outer


@pytest.mark.parametrize(
    "count,item",
    [(65536, None), (40000, "x" * 16), (131072, None)],
    ids=["member-cap", "byte-cap", "both-caps"],
)
def test_public_canonical_encoder_rejects_actual_output_beyond_declared_caps(count, item):
    value = mutable_input(lambda outer: outer.extend([item] * count))
    ambient = RuntimeError("ambient")
    try:
        raise ambient
    except RuntimeError:
        try:
            result = B.canonical_json(value)
        except E.PersistenceError as error:
            assert error.code is E.ErrorCode.LOCAL_INVALID_ARGUMENT
            assert error.unconfirmed is False
            assert error.__cause__ is None and error.__context__ is None
            assert error.__suppress_context__ is True
        else:
            pytest.fail(
                f"public admitted {int.from_bytes(result[1:5], 'big')} members and {len(result)} bytes"
            )


def test_public_valid_growth_retains_literal_output():
    value = mutable_input(lambda outer: outer.extend([None, None]))
    assert B.canonical_json(value) == (
        b"a\0\0\0\x03\0\0\0\0\0\0\0\x05o\0\0\0\0\0\0\0\0\0\0\0\x01n\0\0\0\0\0\0\0\x01n"
    )


def test_public_valid_shrink_retains_output():
    def shrink(outer):
        del outer[1:]

    value = mutable_input(shrink)
    value.extend([None, None])
    assert B.canonical_json(value) == b"a\0\0\0\x01\0\0\0\0\0\0\0\x05o\0\0\0\0"


def test_public_exact_emitted_member_limit_remains_valid():
    value = mutable_input(lambda outer: outer.extend([None] * 65535))
    result = B.canonical_json(value)
    assert result[:5] == b"a\0\x01\0\0" and len(result) == 589833


@pytest.mark.parametrize("count,item", [(65535, None), (40000, "x" * 16)], ids=["members", "bytes"])
def test_public_encoder_does_not_call_children_beyond_exhausted_output_budget(count, item):
    calls = []
    tail = mutable_input(lambda outer: calls.append("unexpected"))[0]

    def grow(outer):
        outer.extend([item] * count)
        outer.append(tail)

    value, error = mutable_input(grow), None
    try:
        B.canonical_json(value)
    except E.PersistenceError as received:
        error = received
    assert calls == [], "callback beyond exhausted output budget was executed"
    assert error is not None and error.code is E.ErrorCode.LOCAL_INVALID_ARGUMENT
