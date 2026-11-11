"""Immutable application-neutral event values."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import NoReturn


def _reject_event(error_type, message, reject) -> NoReturn:
    if reject is not None:
        reject()
    raise error_type(message)


def _freeze(value: object, depth: int = 0, *, _reject=None) -> object:
    if depth > 64:
        _reject_event(ValueError, "JSON nesting exceeds 64 levels", _reject)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _reject_event(ValueError, "JSON numbers must be finite", _reject)
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            _reject_event(ValueError, "JSON object keys must be strings", _reject)
        return MappingProxyType(
            {key: _freeze(item, depth + 1, _reject=_reject) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, depth + 1, _reject=_reject) for item in value)
    _reject_event(TypeError, "Event values must be JSON-compatible", _reject)


def freeze(value: object, depth: int = 0) -> object:
    """Snapshot strict JSON values, rejecting cycles/deep input without custom coercions."""
    return _freeze(value, depth)


def _validate_event_fields(event, *, _reject=None) -> None:
    for value in (event.event_id, event.name):
        if not isinstance(value, str) or not value.strip():
            _reject_event(ValueError, "Event identity and name must be nonempty strings", _reject)
    if type(event.schema_version) is not int or event.schema_version < 1:
        _reject_event(ValueError, "schema_version must be a positive integer", _reject)
    for name in ("payload", "metadata"):
        value = getattr(event, name)
        if not isinstance(value, Mapping):
            _reject_event(ValueError, f"{name} must be a mapping", _reject)
        object.__setattr__(event, name, _freeze(value, _reject=_reject))


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    name: str
    payload: Mapping[str, object]
    schema_version: int = 1
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event_fields(self)


@dataclass(slots=True)
class _EventDraft:
    event_id: object
    name: object
    payload: object
    schema_version: object
    metadata: object


def _event_from_fields(event_id, name, payload, schema_version, metadata, *, _reject):
    """Validate using a fixed draft before allocating the final exact Event."""
    draft = _EventDraft(event_id, name, payload, schema_version, metadata)
    _validate_event_fields(draft, _reject=_reject)
    event = object.__new__(Event)
    object.__setattr__(event, "event_id", draft.event_id)
    object.__setattr__(event, "name", draft.name)
    object.__setattr__(event, "payload", draft.payload)
    object.__setattr__(event, "schema_version", draft.schema_version)
    object.__setattr__(event, "metadata", draft.metadata)
    return event
