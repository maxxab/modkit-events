"""Persistence decorators preserve calls while translating ordinary exceptions."""

from functools import partial
from inspect import signature

import pytest

from modkit_events.persistence.errors import (
    ErrorCode,
    PersistenceError,
    _boundary,
    _decorate,
    _observation_boundary,
)


@pytest.fixture(
    params=[
        (_boundary, ErrorCode.LOCAL_INVALID_ARGUMENT, False),
        (_observation_boundary, ErrorCode.INVALID_OBSERVATION, True),
        (
            partial(_decorate, code=ErrorCode.DATABASE_FAILURE, unconfirmed=True),
            ErrorCode.DATABASE_FAILURE,
            True,
        ),
    ]
)
def boundary(request):
    return request.param


def test_boundary_preserves_result_identity_arguments_and_metadata(boundary):
    decorate, _, _ = boundary
    value = object()
    marker = object()
    calls = []

    def original(item: object, /, *, marker: object) -> object:
        """Original callable documentation."""
        calls.append((item, marker))
        return item

    checked = decorate(original)
    assert checked is not original
    assert checked.__wrapped__ is original
    assert checked.__name__ == original.__name__
    assert checked.__qualname__ == original.__qualname__
    assert checked.__doc__ == original.__doc__
    assert checked.__annotations__ == original.__annotations__
    assert signature(checked) == signature(original)
    assert checked(value, marker=marker) is value
    assert calls == [(value, marker)]


def test_boundary_detaches_translated_exception_from_ambient_context(boundary):
    decorate, code, unconfirmed = boundary

    def original():
        raise ValueError("private failure detail")

    checked = decorate(original)
    try:
        raise RuntimeError("private ambient detail")
    except RuntimeError:
        with pytest.raises(PersistenceError) as caught:
            checked()
    assert caught.value.code is code
    assert caught.value.unconfirmed is unconfirmed
    assert str(caught.value) == code.value
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert caught.value.__suppress_context__ is True


def test_boundary_preserves_baseexception_identity(boundary):
    decorate, _, _ = boundary
    failure = KeyboardInterrupt()

    def original():
        raise failure

    with pytest.raises(KeyboardInterrupt) as caught:
        decorate(original)()
    assert caught.value is failure
