"""Static consumers retain return types, positional arguments, and keyword names."""

from typing import assert_type

from modkit_events.persistence.errors import (
    ErrorCode,
    _boundary,
    _decorate,
    _observation_boundary,
    sqlstate_to_error_code,
)


@_boundary
def local_boundary(value: int, /, *, label: str) -> tuple[int, str]:
    return value, label


@_observation_boundary
def observation_boundary(value: bytes, /, *, limit: int = 1) -> bytes:
    return value[:limit]


def raw_boundary(value: int, /, *, label: str) -> tuple[int, str]:
    return value, label


def check_consumers() -> None:
    assert_type(local_boundary(1, label="ready"), tuple[int, str])
    assert_type(observation_boundary(b"ready", limit=2), bytes)
    decorated = _decorate(raw_boundary, ErrorCode.LOCAL_INVALID_ARGUMENT, False)
    assert_type(decorated(1, label="ready"), tuple[int, str])
    assert_type(sqlstate_to_error_code("PZ001"), ErrorCode | None)
    assert_type(sqlstate_to_error_code(None), ErrorCode | None)

    # With --warn-unused-ignores, erasing the callable signatures fails these checks.
    local_boundary("wrong", label="ready")  # type: ignore[arg-type]
    local_boundary(1, wrong="ready")  # type: ignore[call-arg]
    observation_boundary("wrong", limit=2)  # type: ignore[arg-type]
    observation_boundary(b"ready", wrong=2)  # type: ignore[call-arg]
    decorated("wrong", label="ready")  # type: ignore[arg-type]
    decorated(1, wrong="ready")  # type: ignore[call-arg]
    sqlstate_to_error_code(sqlstate="PZ001")  # type: ignore[call-arg]
