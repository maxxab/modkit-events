"""NEW MKSC1 scope seam; no historical canonical-format compatibility."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import NoReturn, ParamSpec, TypeVar, cast

_P = ParamSpec("_P")
_T = TypeVar("_T")
# Normative fixed set, independent of interpreter Unicode tables and SQL locale.
_WHITESPACE = frozenset(
    (9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
     8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
     8232, 8233, 8239, 8287, 12288)
)
_HEADER = b"MKSC\x01"


def _scope_boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    """Scope-only validation boundary, not a generic persistence sanitizer."""
    @wraps(function)
    def checked(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return function(*args, **kwargs)
        except Exception:
            pass
        # Raising may attach an ambient caller exception. Detach at final exit.
        try:
            raise ValueError("Invalid scope")
        except ValueError as error:
            error.__cause__ = None
            error.__context__ = None
            error.__suppress_context__ = True
            raise
    return checked


def _reject_field(reject: Callable[[], NoReturn] | None) -> NoReturn:
    if reject is not None:
        reject()
    raise ValueError


def _encode_field(
    value: object, *, _reject: Callable[[], NoReturn] | None = None
) -> bytes:
    """Share field checks while allowing only private intentional-error translation."""
    if type(value) is not str:
        _reject_field(_reject)
    # UTF-8 needs at least one byte per codepoint; avoid oversized allocations.
    if not 1 <= len(value) <= 256:
        _reject_field(_reject)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        if _reject is None or type(error) is not UnicodeEncodeError:
            raise
        _reject_field(_reject)
    if len(encoded) > 256 or all(ord(char) in _WHITESPACE for char in value):
        _reject_field(_reject)
    return encoded


@dataclass(frozen=True, slots=True, repr=False)
class Scope:
    application: str
    tenant: str | None = None
    owner: str | None = None

    @_scope_boundary
    def __post_init__(self) -> None:
        _encode_field(self.application)
        if self.tenant is not None:
            _encode_field(self.tenant)
        if self.owner is not None:
            _encode_field(self.owner)


def _fields(scope: Scope) -> tuple[bytes, bytes | None, bytes | None]:
    if type(scope) is not Scope:
        raise ValueError
    return (
        _encode_field(scope.application),
        None if scope.tenant is None else _encode_field(scope.tenant),
        None if scope.owner is None else _encode_field(scope.owner),
    )


@_scope_boundary
def encode_scope_fields(scope: Scope) -> tuple[bytes, bytes | None, bytes | None]:
    """Revalidate logical fields and return immutable raw UTF-8 projections."""
    return _fields(scope)


def _snapshot(value: object) -> bytes:
    if type(value) not in (bytes, bytearray, memoryview):
        raise ValueError
    raw = cast(bytes | bytearray | memoryview, value)
    size = raw.nbytes if isinstance(raw, memoryview) else len(raw)
    if not 1 <= size <= 256:
        raise ValueError
    # bytes(memoryview) snapshots logical bytes in C order, including strided views.
    result = bytes(raw)
    if not 1 <= len(result) <= 256:
        raise ValueError
    return result


@_scope_boundary
def decode_scope_fields(
    application: bytes | bytearray | memoryview,
    tenant: bytes | bytearray | memoryview | None = None,
    owner: bytes | bytearray | memoryview | None = None,
) -> Scope:
    """Snapshot all raw fields before strict decoding; never accept TEXT wire data."""
    app = _snapshot(application)
    tenant_bytes = None if tenant is None else _snapshot(tenant)
    owner_bytes = None if owner is None else _snapshot(owner)
    return Scope(
        app.decode("utf-8", errors="strict"),
        None if tenant_bytes is None else tenant_bytes.decode("utf-8", errors="strict"),
        None if owner_bytes is None else owner_bytes.decode("utf-8", errors="strict"),
    )


@_scope_boundary
def canonical_scope(scope: Scope) -> bytes:
    """Encode the sole NEW scope frame: MKSC + version1 + lengths/presence."""
    application, tenant, owner = _fields(scope)
    parts = [_HEADER, len(application).to_bytes(2, "big"), application]
    for value in (tenant, owner):
        if value is None:
            parts.append(b"\x00")
        else:
            parts.extend((b"\x01", len(value).to_bytes(2, "big"), value))
    return b"".join(parts)


@_scope_boundary
def decode_canonical_scope(raw: bytes) -> Scope:
    """Require one unique strict frame with no trailing data or alternate version."""
    if type(raw) is not bytes or not 10 <= len(raw) <= 781 or raw[:5] != _HEADER:
        raise ValueError
    position = 5

    def present() -> bytes:
        nonlocal position
        if position + 2 > len(raw):
            raise ValueError
        length = int.from_bytes(raw[position:position + 2], "big")
        position += 2
        if not 1 <= length <= 256 or position + length > len(raw):
            raise ValueError
        value = raw[position:position + length]
        position += length
        return value

    def optional() -> bytes | None:
        nonlocal position
        if position >= len(raw):
            raise ValueError
        tag = raw[position]
        position += 1
        if tag == 0:
            return None
        if tag != 1:
            raise ValueError
        return present()

    application = present()
    tenant = optional()
    owner = optional()
    if position != len(raw):
        raise ValueError
    return decode_scope_fields(application, tenant, owner)
