"""Code-only errors with immediate-exit exception-chain detachment."""
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import NoReturn, ParamSpec, TypeVar

_P = ParamSpec("_P")
_T = TypeVar("_T")


class _ValidationReject(Exception):
    """An intentional private validation rejection, never an unexpected primary."""


def _reject_validation() -> NoReturn:
    raise _ValidationReject


class ErrorCode(Enum):
    UNSATISFIED_GUARD = 'UNSATISFIED_GUARD'
    IDENTITY_CONFLICT = 'IDENTITY_CONFLICT'
    STALE_FENCE = 'STALE_FENCE'
    INVALID_TRANSITION = 'INVALID_TRANSITION'
    UNSUPPORTED_ISOLATION = 'UNSUPPORTED_ISOLATION'
    INVALID_ARGUMENT = 'INVALID_ARGUMENT'
    CAPACITY_EXCEEDED = 'CAPACITY_EXCEEDED'
    GUARD_MISMATCH = 'GUARD_MISMATCH'
    DEADLINE_EXCEEDED = 'DEADLINE_EXCEEDED'
    FRESH_ROOT_REQUIRED = 'FRESH_ROOT_REQUIRED'
    SCHEMA_MISMATCH = 'SCHEMA_MISMATCH'
    INTEGRITY_VIOLATION = 'INTEGRITY_VIOLATION'
    LOCAL_INVALID_ARGUMENT = 'LOCAL_INVALID_ARGUMENT'
    INVALID_OBSERVATION = 'INVALID_OBSERVATION'
    RESOURCE_BUSY = 'RESOURCE_BUSY'
    PROFILE_REJECTED = 'PROFILE_REJECTED'
    DATABASE_FAILURE = 'DATABASE_FAILURE'
    OUTCOME_UNKNOWN = 'OUTCOME_UNKNOWN'


class PersistenceError(Exception):
    def __init__(self, code: ErrorCode, *, unconfirmed: bool):
        if type(code) is not ErrorCode or type(unconfirmed) is not bool:
            code, unconfirmed = ErrorCode.LOCAL_INVALID_ARGUMENT, False
        self.code, self.unconfirmed = code, unconfirmed
        super().__init__(code.value)


def _fail(code: ErrorCode, *, unconfirmed: bool) -> NoReturn:
    try:
        raise PersistenceError(code, unconfirmed=unconfirmed)
    except PersistenceError as error:
        error.__cause__ = error.__context__ = None
        error.__suppress_context__ = True
        raise


def _decorate(
    function: Callable[_P, _T], code: ErrorCode, unconfirmed: bool
) -> Callable[_P, _T]:
    @wraps(function)
    def checked(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return function(*args, **kwargs)
        except Exception:
            pass
        _fail(code, unconfirmed=unconfirmed)
    return checked


def _boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    return _decorate(function, ErrorCode.LOCAL_INVALID_ARGUMENT, False)


def _observation_boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    return _decorate(function, ErrorCode.INVALID_OBSERVATION, True)


_SQLSTATE_CODES = {
    'PZ001': ErrorCode.UNSATISFIED_GUARD,
    'PZ002': ErrorCode.IDENTITY_CONFLICT,
    'PZ003': ErrorCode.STALE_FENCE,
    'PZ004': ErrorCode.INVALID_TRANSITION,
    'PZ005': ErrorCode.UNSUPPORTED_ISOLATION,
    'PZ006': ErrorCode.INVALID_ARGUMENT,
    'PZ007': ErrorCode.CAPACITY_EXCEEDED,
    'PZ008': ErrorCode.GUARD_MISMATCH,
    'PZ009': ErrorCode.DEADLINE_EXCEEDED,
    'PZ010': ErrorCode.FRESH_ROOT_REQUIRED,
    'PZ011': ErrorCode.SCHEMA_MISMATCH,
    'PZ012': ErrorCode.INTEGRITY_VIOLATION,
}


@_boundary
def sqlstate_to_error_code(sqlstate: str | None, /) -> ErrorCode | None:
    """Recognize a diagnosis only; never prove rejection, rollback or replay safety."""
    if sqlstate is None:
        return None
    if type(sqlstate) is not str:
        raise ValueError
    if len(sqlstate) != 5:
        return None
    return _SQLSTATE_CODES.get(sqlstate)
