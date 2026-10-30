"""Bounded UTF-8 JSON envelope encoding with no application schema assumptions."""

import json
from collections.abc import Mapping

from .models import Event


def _plain(value: object, remaining: int) -> object:
    if remaining < 0:
        raise ValueError("JSON nesting exceeds configured depth")
    if isinstance(value, Mapping):
        return {key: _plain(item, remaining - 1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item, remaining - 1) for item in value]
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


class JsonCodec:
    def __init__(self, *, max_bytes: int = 1048576, max_depth: int = 32):
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if type(max_depth) is not int or not 1 <= max_depth <= 64:
            raise ValueError("max_depth must be between 1 and 64")
        self.max_bytes = max_bytes
        self.max_depth = max_depth

    def encode(self, event: Event) -> bytes:
        value = {
            "event_id": event.event_id,
            "name": event.name,
            "schema_version": event.schema_version,
            "payload": _plain(event.payload, self.max_depth),
            "metadata": _plain(event.metadata, self.max_depth),
        }
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > self.max_bytes:
            raise ValueError("Encoded event exceeds max_bytes")
        return raw

    def decode(self, raw: bytes) -> Event:
        if not isinstance(raw, bytes) or len(raw) > self.max_bytes:
            raise ValueError("Expected bytes within max_bytes")
        try:
            value = json.loads(raw, parse_constant=_invalid_constant, object_pairs_hook=_pairs)
            if not isinstance(value, dict):
                raise ValueError("Envelope must be a JSON object")
            event = Event(**value)
            _plain(event.payload, self.max_depth)
            _plain(event.metadata, self.max_depth)
            return event
        except (TypeError, UnicodeError, RecursionError) as error:
            raise ValueError("Invalid event envelope") from error
