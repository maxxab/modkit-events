"""Immutable application-neutral event values."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


def freeze(value: object, depth: int = 0) -> object:
    """Snapshot strict JSON values, rejecting cycles/deep input without custom coercions."""
    if depth > 64:
        raise ValueError("JSON nesting exceeds 64 levels")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return MappingProxyType({key: freeze(item, depth + 1) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item, depth + 1) for item in value)
    raise TypeError("Event values must be JSON-compatible")


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    name: str
    payload: Mapping[str, object]
    schema_version: int = 1
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.event_id, self.name):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Event identity and name must be nonempty strings")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("schema_version must be a positive integer")
        for name in ("payload", "metadata"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"{name} must be a mapping")
            object.__setattr__(self, name, freeze(value))
