"""Bounded NEW MKPF/J and managed replay codecs; no transaction or I/O."""
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from .errors import _boundary, _reject_validation
from .models import (
    CanonicalEvidence, ProtectedBindingInput, MaterialState, CleanupPolicy,
    _canonical_evidence_raw,
)
from .scope import Scope, _encode_field
from ..models import Event, _event_from_fields

_MAX = 1048576


def _reject_scalar(reject):
    if reject is not None:
        reject()
    raise ValueError


def _bytes(value, maximum=_MAX, *, _reject=None):
    if type(value) not in (bytes, bytearray, memoryview):
        _reject_scalar(_reject)
    if (value.nbytes if type(value) is memoryview else len(value)) > maximum:
        _reject_scalar(_reject)
    result = bytes(value)
    if len(result) > maximum:
        _reject_scalar(_reject)
    return result


def _bytes_raw(value, maximum=_MAX):
    """First-slice raw byte values are immutable, not borrowed mutable buffers."""
    if type(value) is not bytes:
        _reject_validation()
    return _bytes(value, maximum, _reject=_reject_validation)


def _integer(value, minimum, maximum, *, _reject=None):
    if type(value) is not int or not minimum <= value <= maximum:
        _reject_scalar(_reject)
    return value


def _integer_raw(value, minimum, maximum):
    return _integer(value, minimum, maximum, _reject=_reject_validation)


def _instant(value, *, _reject=None):
    if type(value) is not datetime or value.utcoffset() is None:
        _reject_scalar(_reject)
    return value.astimezone(timezone.utc)


def _identifier(value):
    return Scope(value).application.encode('utf-8')


def _identifier_raw(value):
    """Validate through the shared field authority without public sanitization."""
    return _encode_field(value, _reject=_reject_validation)


def _event_raw(event_id, name, payload, schema_version, metadata):
    return _event_from_fields(
        event_id, name, payload, schema_version, metadata, _reject=_reject_validation
    )


def _frame(raw):
    return len(raw).to_bytes(8,'big')+raw


def _record(tag, fields, *, _reject=None):
    size = 5 + 8 + len(tag) + 4 + sum(8 + len(value) for value in fields)
    if size > _MAX:
        _reject_scalar(_reject)
    return (
        b"MKPF\x01"
        + _frame(tag)
        + len(fields).to_bytes(4, "big")
        + b"".join(_frame(value) for value in fields)
    )


def _record_raw(tag, fields):
    """First-slice framing supports one exact immutable event-envelope shape."""
    if type(tag) is not bytes or tag != b"event-envelope":
        _reject_validation()
    if type(fields) is not tuple or len(fields) != 5:
        _reject_validation()
    if any(type(value) is not bytes for value in fields):
        _reject_validation()
    return _record(tag, fields, _reject=_reject_validation)


def _optional(raw):
    return b"0" if raw is None else b"1" + _frame(raw)


def _decimal(value, *, _reject=None):
    if type(value) is not int:
        _reject_scalar(_reject)
    if _reject is not None and value.bit_length() > 13607:
        _reject_scalar(_reject)
    negative = value < 0
    value = abs(value)
    if value.bit_length() > 13607:
        _reject_scalar(_reject)
    chunks = []
    while value:
        value, part = divmod(value, 1000000000)
        chunks.append(part)
    text = (
        "0"
        if not chunks
        else str(chunks[-1]) + "".join(f"{x:09d}" for x in reversed(chunks[:-1]))
    )
    if len(text) > 4096:
        _reject_scalar(_reject)
    return ("-" if negative else "").encode() + text.encode("ascii")


def _decimal_raw(value):
    return _decimal(value, _reject=_reject_validation)


def _read_decimal(raw, signed=True, *, _reject=None):
    if type(raw) is not bytes:
        _reject_scalar(_reject)
    if _reject is not None and len(raw) > 4097:
        _reject_scalar(_reject)
    negative = raw.startswith(b"-")
    digits = raw[1:] if negative else raw
    if negative and not signed:
        _reject_scalar(_reject)
    if (
        not 1 <= len(digits) <= 4096
        or any(c < 48 or c > 57 for c in digits)
        or len(digits) > 1
        and digits[0] == 48
        or negative
        and digits == b"0"
    ):
        _reject_scalar(_reject)
    n = 0
    for pos in range(0, len(digits), 9):
        part = digits[pos : pos + 9]
        n = n * 10 ** len(part) + int(part)
    return -n if negative else n


def _read_decimal_raw(raw, signed=True):
    if type(signed) is not bool:
        _reject_validation()
    return _read_decimal(raw, signed, _reject=_reject_validation)


def _version_to_decimal_core(version, *, _reject=None):
    if type(version) is not int or version < 1:
        _reject_scalar(_reject)
    return _decimal(version, _reject=_reject)


@_boundary
def version_to_decimal(version):
    return _version_to_decimal_core(version)


def _version_to_decimal_raw(version):
    return _version_to_decimal_core(version, _reject=_reject_validation)


def _version_from_decimal_core(raw, *, _reject=None):
    value = _read_decimal(raw, False, _reject=_reject)
    if value < 1:
        _reject_scalar(_reject)
    return value


@_boundary
def version_from_decimal(raw):
    return _version_from_decimal_core(raw)


def _version_from_decimal_raw(raw):
    return _version_from_decimal_core(raw, _reject=_reject_validation)


class _Budget:
    def __init__(self, *, _reject=None):
        self.nodes = 0
        self.bytes = 0
        self._reject = _reject

    def node(self, depth):
        self.nodes += 1
        if depth > 32 or self.nodes > 262144:
            _reject_scalar(self._reject)

    def add(self, size):
        self.bytes += size
        if self.bytes > _MAX:
            _reject_scalar(self._reject)


def _utf8(value, *, _reject=None):
    if type(value) is not str or len(value) > _MAX:
        _reject_scalar(_reject)
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeEncodeError as error:
        if _reject is None or type(error) is not UnicodeEncodeError:
            raise
        _reject_scalar(_reject)
    if len(raw) > _MAX:
        _reject_scalar(_reject)
    return raw


def _j(value, depth, budget, *, _reject=None):
    budget.node(depth)
    if value is None:
        budget.add(1)
        return b"n"
    if type(value) is bool:
        budget.add(1)
        return b"t" if value else b"f"
    if type(value) is int:
        raw = _decimal(value, _reject=_reject)
        budget.add(9 + len(raw))
        return b"i" + _frame(raw)
    if type(value) is float:
        if not math.isfinite(value):
            _reject_scalar(_reject)
        raw = value.hex().encode("ascii")
        budget.add(9 + len(raw))
        return b"d" + _frame(raw)
    if type(value) is str:
        raw = _utf8(value, _reject=_reject)
        budget.add(9 + len(raw))
        return b"s" + _frame(raw)
    if isinstance(value, Mapping):
        budget.add(5)
        items = []
        for index, (key, item) in enumerate(value.items()):
            if index >= 65536:
                _reject_scalar(_reject)
            key_raw = _utf8(key, _reject=_reject)
            budget.add(16 + len(key_raw))
            items.append((key_raw, _j(item, depth + 1, budget, _reject=_reject)))
        items.sort(key=lambda pair: pair[0])
        if any(items[i - 1][0] == items[i][0] for i in range(1, len(items))):
            _reject_scalar(_reject)
        return (
            b"o"
            + len(items).to_bytes(4, "big")
            + b"".join(_frame(key) + _frame(value) for key, value in items)
        )
    if type(value) in (list, tuple):
        if len(value) > 65536:
            _reject_scalar(_reject)
        precharged = len(value)
        budget.add(5 + 8 * precharged)
        items = []
        for index, item in enumerate(value):
            if index >= 65536:
                _reject_scalar(_reject)
            if index >= precharged:
                budget.add(8)
            items.append(_j(item, depth + 1, budget, _reject=_reject))
        return (
            b"a"
            + len(items).to_bytes(4, "big")
            + b"".join(_frame(item) for item in items)
        )
    _reject_scalar(_reject)


def _canonical_json_core(value, *, _reject=None):
    return _j(value, 0, _Budget(_reject=_reject), _reject=_reject)


@_boundary
def canonical_json(value):
    return _canonical_json_core(value)


def _canonical_json_raw(value):
    return _canonical_json_core(value, _reject=_reject_validation)


class _Reader:
    def __init__(self, raw, *, _reject=None):
        if _reject is not None and (type(raw) is not bytes or len(raw) > _MAX):
            _reject_scalar(_reject)
        self.raw = raw
        self.pos = 0
        self._reject = _reject

    def take(self, n):
        if self._reject is not None and (type(n) is not int or not 0 <= n <= _MAX):
            _reject_scalar(self._reject)
        if n < 0 or self.pos + n > len(self.raw):
            _reject_scalar(self._reject)
        result = self.raw[self.pos : self.pos + n]
        self.pos += n
        return result

    def number(self, n):
        if self._reject is not None and (type(n) is not int or n not in (4, 8)):
            _reject_scalar(self._reject)
        return int.from_bytes(self.take(n), "big")

    def frame(self):
        return self.take(self.number(8))

    def end(self):
        if self.pos != len(self.raw):
            _reject_scalar(self._reject)


def _reader_raw(raw):
    return _Reader(raw, _reject=_reject_validation)


_HEX_FLOAT = re.compile(
    rb"-?0x(?:(1)\.[0-9a-f]{13}p([+-](?:0|[1-9][0-9]{0,3}))"
    rb"|0\.[0-9a-f]{13}p-1022|0\.0p\+0)\Z"
)


def _read_float_hex(part, *, _reject=None):
    if _reject is not None and type(part) is not bytes:
        _reject_scalar(_reject)
    if len(part) > 32:
        _reject_scalar(_reject)
    if _reject is not None:
        match = _HEX_FLOAT.fullmatch(part)
        if match is None:
            _reject_scalar(_reject)
        if match[1] is not None and not -1022 <= int(match[2]) <= 1023:
            _reject_scalar(_reject)
    value = float.fromhex(part.decode("ascii"))
    if not math.isfinite(value) or value.hex().encode() != part:
        _reject_scalar(_reject)
    return value


def _read_float_hex_raw(part):
    return _read_float_hex(part, _reject=_reject_validation)


def _decode_utf8(raw, *, _reject=None):
    if _reject is not None and type(raw) is not bytes:
        _reject_scalar(_reject)
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        if _reject is None or type(error) is not UnicodeDecodeError:
            raise
        _reject_scalar(_reject)


def _parse_j(raw, depth, budget, *, _reject=None):
    budget.node(depth)
    r = _Reader(raw) if _reject is None else _reader_raw(raw)
    tag = r.take(1)
    if tag in (b"n", b"t", b"f"):
        value = {b"n": None, b"t": True, b"f": False}[tag]
    elif tag in (b"i", b"d", b"s"):
        part = r.frame()
        if tag == b"i":
            value = (_read_decimal if _reject is None else _read_decimal_raw)(part)
        elif tag == b"s":
            value = _decode_utf8(part, _reject=_reject)
        else:
            value = (_read_float_hex if _reject is None else _read_float_hex_raw)(part)
    elif tag in (b"a", b"o"):
        count = r.number(4)
        if count > 65536:
            _reject_scalar(_reject)
        if tag == b"a":
            value = tuple(
                _parse_j(r.frame(), depth + 1, budget, _reject=_reject)
                for _ in range(count)
            )
        else:
            result = {}
            prior = None
            for _ in range(count):
                key = r.frame()
                if prior is not None and key <= prior:
                    _reject_scalar(_reject)
                prior = key
                result[_decode_utf8(key, _reject=_reject)] = _parse_j(
                    r.frame(), depth + 1, budget, _reject=_reject
                )
            value = MappingProxyType(result)
    else:
        _reject_scalar(_reject)
    r.end()
    return value


def _parse_canonical_json_core(raw, *, _reject=None):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX:
        _reject_scalar(_reject)
    value = _parse_j(raw, 0, _Budget(_reject=_reject), _reject=_reject)
    if (
        canonical_json(value) if _reject is None else _canonical_json_raw(value)
    ) != raw:
        _reject_scalar(_reject)
    return value


@_boundary
def parse_canonical_json(raw):
    return _parse_canonical_json_core(raw)


def _parse_canonical_json_raw(raw):
    return _parse_canonical_json_core(raw, _reject=_reject_validation)


_NUMBER=re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')

def _json_number(text, *, _reject=None):
    if len(text) > 8192 or not _NUMBER.fullmatch(text):
        _reject_scalar(_reject)
    mantissa, *exponent = re.split("[eE]", text)
    if sum(c.isdigit() for c in mantissa) > 4096:
        _reject_scalar(_reject)
    if exponent and len(exponent[0].lstrip("+-")) > 6:
        _reject_scalar(_reject)
    if not exponent and "." not in text:
        return (
            0
            if text == "-0"
            else (_read_decimal if _reject is None else _read_decimal_raw)(text.encode())
        )
    value = float(text)
    if not math.isfinite(value):
        _reject_scalar(_reject)
    return value


def _json_number_raw(text):
    """Bounded exact JSON-number text with deliberate private rejections only."""
    if type(text) is not str:
        _reject_validation()
    return _json_number(text, _reject=_reject_validation)


def _pairs(items):
    if len(items)>65536:raise ValueError
    result={}
    for key,value in items:
        if key in result:raise ValueError
        result[key]=value
    return result


def _invalid(value):raise ValueError


class _JSONReader:
    """Bounded recursive parser; stdlib decodes individual string tokens only."""

    def __init__(self, text, *, _reject=None):
        self.text = text
        self.pos = 0
        self.nodes = 0
        self._reject = _reject

    def whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def string(self):
        start = self.pos
        self.pos += 1
        escaped = False
        while self.pos < len(self.text):
            c = self.text[self.pos]
            self.pos += 1
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                try:
                    value = json.loads(self.text[start : self.pos])
                except json.JSONDecodeError as error:
                    if self._reject is None or type(error) is not json.JSONDecodeError:
                        raise
                    _reject_scalar(self._reject)
                if self._reject is None:
                    _utf8(value)
                else:
                    _utf8(value, _reject=self._reject)
                return value
        _reject_scalar(self._reject)

    def value(self, depth=0, *, envelope_root=False):
        self.whitespace()
        self.nodes += 1
        if depth > 32 or self.nodes > 262144 or self.pos >= len(self.text):
            _reject_scalar(self._reject)
        c = self.text[self.pos]
        if c == '"':
            return self.string()
        if c in "[{":
            self.pos += 1
            obj = c == "{"
            end = "}" if obj else "]"
            result = {} if obj else []
            self.whitespace()
            if self.pos < len(self.text) and self.text[self.pos] == end:
                self.pos += 1
                return result
            count = 0
            while True:
                if count >= 65536:
                    _reject_scalar(self._reject)
                self.whitespace()
                if obj:
                    if self.pos >= len(self.text) or self.text[self.pos] != '"':
                        _reject_scalar(self._reject)
                    key = self.string()
                    if key in result:
                        _reject_scalar(self._reject)
                    self.whitespace()
                    if self.pos >= len(self.text) or self.text[self.pos] != ":":
                        _reject_scalar(self._reject)
                    self.pos += 1
                    child_depth = (
                        0 if envelope_root and key in ("payload", "metadata") else depth + 1
                    )
                    result[key] = self.value(child_depth)
                else:
                    result.append(self.value(depth + 1))
                count += 1
                self.whitespace()
                if self.pos >= len(self.text):
                    _reject_scalar(self._reject)
                separator = self.text[self.pos]
                self.pos += 1
                if separator == end:
                    return result
                if separator != ",":
                    _reject_scalar(self._reject)
        for token, value in (("true", True), ("false", False), ("null", None)):
            if self.text.startswith(token, self.pos):
                self.pos += len(token)
                return value
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in "-+0123456789.eE":
            self.pos += 1
            if self.pos - start > 8192:
                _reject_scalar(self._reject)
        return (_json_number if self._reject is None else _json_number_raw)(
            self.text[start : self.pos]
        )


def _replay(raw, *, event=False, _reject=None):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX or raw.startswith(b"\xef\xbb\xbf"):
        _reject_scalar(_reject)
    reader = (
        _JSONReader(raw.decode("utf-8", "strict"))
        if _reject is None
        else _JSONReader(_decode_utf8(raw, _reject=_reject), _reject=_reject)
    )
    result = reader.value(envelope_root=event)
    reader.whitespace()
    if reader.pos != len(reader.text):
        _reject_scalar(_reject)
    return result


def _replay_raw(raw, *, event=False):
    """Parse bounded exact replay bytes; no public validation boundary."""
    if type(event) is not bool:
        _reject_validation()
    return _replay(raw, event=event, _reject=_reject_validation)


def _decode_mapping_replay_core(raw, *, _reject=None):
    value = (_replay if _reject is None else _replay_raw)(raw)
    if type(value) is not dict:
        _reject_scalar(_reject)
    return (parse_canonical_json if _reject is None else _parse_canonical_json_raw)(
        (canonical_json if _reject is None else _canonical_json_raw)(value)
    )


@_boundary
def decode_mapping_replay(raw):
    return _decode_mapping_replay_core(raw)


def _decode_mapping_replay_raw(raw):
    return _decode_mapping_replay_core(raw, _reject=_reject_validation)


def _float_decimal(value):
    if value==0:return '-0.0' if math.copysign(1,value)<0 else '0.0'
    negative=value<0;n,d=abs(value).as_integer_ratio();whole,remainder=divmod(n,d)
    fraction=[]
    while remainder:
        digit,remainder=divmod(remainder*10,d);fraction.append(str(digit))
    return ('-' if negative else '')+str(whole)+'.'+(''.join(fraction) or '0')


def _emit(value, *, _reject=None):
    """Append bounded tokens, rejecting BEFORE an expanded buffer exceeds budget."""
    output = bytearray()

    def append(raw):
        if len(raw) > _MAX - len(output):
            _reject_scalar(_reject)
        output.extend(raw)

    def emit(item):
        if item is None:
            append(b"null")
        elif type(item) is bool:
            append(b"true" if item else b"false")
        elif type(item) is int:
            append(_decimal(item, _reject=_reject))
        elif type(item) is float:
            append(_float_decimal(item).encode("ascii"))
        elif type(item) is str:
            append(b'"')
            for c in item:
                if c == '"':
                    append(b'\\"')
                elif c == "\\":
                    append(b"\\\\")
                elif ord(c) < 32:
                    append(f"\\u{ord(c):04x}".encode("ascii"))
                else:
                    append(c.encode("utf8"))
            append(b'"')
        elif isinstance(item, Mapping):
            append(b"{")
            for index, (key, child) in enumerate(
                sorted(item.items(), key=lambda pair: pair[0].encode("utf8"))
            ):
                if index:
                    append(b",")
                emit(key)
                append(b":")
                emit(child)
            append(b"}")
        else:
            append(b"[")
            for index, child in enumerate(item):
                if index:
                    append(b",")
                emit(child)
            append(b"]")

    emit(value)
    return bytes(output)


def _emit_raw(value):
    """Emit only a previously bounded canonical snapshot with raw rejections."""
    return _emit(value, _reject=_reject_validation)


@_boundary
def encode_mapping_replay(value):
    if not isinstance(value,Mapping):raise ValueError
    frozen=parse_canonical_json(canonical_json(value))
    return _emit(frozen)


def _validate_event_replay_core(raw, *, _reject=None):
    value = (_replay if _reject is None else _replay_raw)(raw, event=True)
    if type(value) is not dict or set(value) != {
        "event_id",
        "name",
        "schema_version",
        "payload",
        "metadata",
    }:
        _reject_scalar(_reject)
    event = (
        Event(**value)
        if _reject is None
        else _event_raw(
            value["event_id"],
            value["name"],
            value["payload"],
            value["schema_version"],
            value["metadata"],
        )
    )
    (canonical_event if _reject is None else _canonical_event_raw)(event)
    return event


@_boundary
def validate_event_replay(raw):
    return _validate_event_replay_core(raw)


def _validate_event_replay_raw(raw):
    return _validate_event_replay_core(raw, _reject=_reject_validation)


def _canonical_event_core(event, *, _reject=None):
    if type(event) is not Event:
        _reject_scalar(_reject)
    fields = [
        (_identifier if _reject is None else _identifier_raw)(event.event_id),
        (_identifier if _reject is None else _identifier_raw)(event.name),
        (version_to_decimal if _reject is None else _version_to_decimal_raw)(
            event.schema_version
        ),
        (canonical_json if _reject is None else _canonical_json_raw)(event.payload),
        (canonical_json if _reject is None else _canonical_json_raw)(event.metadata),
    ]
    raw = (
        _record(b"event-envelope", fields)
        if _reject is None
        else _record_raw(b"event-envelope", tuple(fields))
    )
    evidence = CanonicalEvidence if _reject is None else _canonical_evidence_raw
    return evidence(version=1, content=raw, digest=sha256(raw).digest())


@_boundary
def canonical_event(event):
    return _canonical_event_core(event)


def _canonical_event_raw(event):
    return _canonical_event_core(event, _reject=_reject_validation)


def _timestamp(value, *, _reject=None):
    value = (_instant if _reject is None else _instant_raw)(value)
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}T{value.hour:02d}:{value.minute:02d}:{value.second:02d}.{value.microsecond:06d}Z".encode(
        "ascii"
    )


def _metadata(value, empty=False, *, _reject=None):
    parse_canonical_json_fn = (
        parse_canonical_json if _reject is None else _parse_canonical_json_raw
    )
    canonical_json_fn = canonical_json if _reject is None else _canonical_json_raw
    if type(value) is bytes:
        if empty and value == b"":
            return value
        parsed = parse_canonical_json_fn(value)
        if not isinstance(parsed, Mapping):
            _reject_scalar(_reject)
        return value
    if not isinstance(value, Mapping):
        _reject_scalar(_reject)
    return canonical_json_fn(value)


def _normalize_material(m, *, _reject=None):
    bytes_fn = _bytes if _reject is None else _bytes_raw
    instant_fn = _instant if _reject is None else _instant_raw
    identifier_fn = _identifier if _reject is None else _identifier_raw
    if (
        type(m.material_state) is not MaterialState
        or m.material_state is MaterialState.ERASED
        or type(m.cleanup_policy) is not CleanupPolicy
    ):
        _reject_scalar(_reject)
    sidecar = None if m.sidecar is None else bytes_fn(m.sidecar)
    reference = None if m.reference is None else bytes_fn(m.reference)
    content = bytes_fn(m.content_binding)
    expires = None if m.expires_at is None else instant_fn(m.expires_at)
    projection = _metadata(m.projection_metadata, _reject=_reject)
    recovery = _metadata(
        m.recovery_metadata,
        empty=m.material_state is MaterialState.ABSENT,
        _reject=_reject,
    )
    if m.material_state is MaterialState.ABSENT:
        if (
            any(
                v is not None
                for v in (sidecar, reference, m.codec, m.key_version, expires)
            )
            or m.cleanup_policy is not CleanupPolicy.RETAIN
            or content != b""
            or recovery != b""
        ):
            _reject_scalar(_reject)
    else:
        if (
            (sidecar is None) == (reference is None)
            or sidecar == b""
            or reference == b""
            or not content
            or not recovery
        ):
            _reject_scalar(_reject)
        identifier_fn(m.codec)
        identifier_fn(m.key_version)
    return dict(
        sidecar=sidecar,
        reference=reference,
        content_binding=content,
        expires_at=expires,
        projection_metadata=projection,
        recovery_metadata=recovery,
    )


def _canonical_protected_binding_core(material, *, _reject=None):
    identifier_fn = _identifier if _reject is None else _identifier_raw

    def _timestamp_fn(value):
        return _timestamp(value, _reject=_reject)

    if type(material) is not ProtectedBindingInput:
        _reject_scalar(_reject)
    values = _normalize_material(material, _reject=_reject)
    fields = [
        material.material_state.value.encode(),
        _optional(None if material.codec is None else identifier_fn(material.codec)),
        _optional(
            None
            if material.key_version is None
            else identifier_fn(material.key_version)
        ),
        _optional(
            None
            if values["expires_at"] is None
            else _timestamp_fn(values["expires_at"])
        ),
        material.cleanup_policy.value.encode(),
        _optional(values["sidecar"]),
        _optional(values["reference"]),
        values["content_binding"],
        values["recovery_metadata"],
        values["projection_metadata"],
    ]
    raw = _record(b"protected-binding", fields, _reject=_reject)
    return (CanonicalEvidence if _reject is None else _canonical_evidence_raw)(
        version=1, content=raw, digest=sha256(raw).digest()
    )


def _unoptional(raw, *, _reject=None):
    if raw == b"0":
        return None
    r = _Reader(raw, _reject=_reject)
    if r.take(1) != b"1":
        _reject_scalar(_reject)
    value = r.frame()
    r.end()
    return value


def _decode_protected_binding_core(raw, *, _reject=None):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX:
        _reject_scalar(_reject)
    r = _Reader(raw, _reject=_reject)
    if (
        r.take(5) != b"MKPF\x01"
        or r.frame() != b"protected-binding"
        or r.number(4) != 10
    ):
        _reject_scalar(_reject)
    f = [r.frame() for _ in range(10)]
    r.end()
    codec, key, expiry, sidecar, reference = (
        _unoptional(f[i], _reject=_reject) for i in (1, 2, 3, 5, 6)
    )
    if _reject is not None:
        for value in (codec, key):
            if value is not None and not 1 <= len(value) <= 256:
                _reject_scalar(_reject)
    instant = None
    if expiry is not None:
        if len(expiry) != 27:
            _reject_scalar(_reject)
        if _reject is not None:
            if not re.fullmatch(
                rb"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",
                expiry,
            ):
                _reject_scalar(_reject)
            try:
                instant = datetime.fromisoformat(
                    expiry.decode("ascii").replace("Z", "+00:00")
                )
            except ValueError as error:
                if type(error) is not ValueError:
                    raise
                _reject_scalar(_reject)
        else:
            instant = datetime.fromisoformat(
                expiry.decode("ascii").replace("Z", "+00:00")
            )
        if _timestamp(instant, _reject=_reject) != expiry:
            _reject_scalar(_reject)
    if _reject is not None:
        if f[0] not in (b"absent", b"present") or f[4] not in (
            b"retain",
            b"erase_after_terminal",
        ):
            _reject_scalar(_reject)
    material = (
        ProtectedBindingInput if _reject is None else _protected_binding_input_raw
    )(
        material_state=MaterialState(f[0].decode("ascii")),
        codec=None if codec is None else _decode_utf8(codec, _reject=_reject),
        key_version=None if key is None else _decode_utf8(key, _reject=_reject),
        expires_at=instant,
        cleanup_policy=CleanupPolicy(f[4].decode("ascii")),
        sidecar=sidecar,
        reference=reference,
        content_binding=f[7],
        recovery_metadata=f[8],
        projection_metadata=f[9],
    )
    if _canonical_protected_binding_core(material, _reject=_reject).content != raw:
        _reject_scalar(_reject)
    return material


@_boundary
def validate_protected_binding(raw,material):
    decoded=decode_protected_binding(raw);evidence=canonical_protected_binding(material)
    if canonical_protected_binding(decoded).content!=evidence.content:raise ValueError
    return evidence


def _canonical_intent_core(admission, *, _reject=None):
    identifier_fn = _identifier if _reject is None else _identifier_raw
    version_to_decimal_fn = (
        version_to_decimal if _reject is None else _version_to_decimal_raw
    )
    bytes_fn = _bytes if _reject is None else _bytes_raw
    integer_fn = _integer if _reject is None else _integer_raw

    def _timestamp_fn(value):
        return _timestamp(value, _reject=_reject)

    from .models import AdmissionInput, ReplayPolicy, WorkIdentity

    if (
        type(admission) is not AdmissionInput
        or type(admission.identity) is not WorkIdentity
        or type(admission.replay_policy) is not ReplayPolicy
    ):
        _reject_scalar(_reject)
    identity = admission.identity
    if _reject is None:
        identity.__post_init__()
    else:
        from .models import _validate_work_identity_raw

        _validate_work_identity_raw(identity)
    fields = [
        identity.kind.value.encode(),
        _optional(
            None
            if identity.subscription_id is None
            else identifier_fn(identity.subscription_id)
        ),
        identifier_fn(identity.namespace),
        identifier_fn(identity.command_type),
        version_to_decimal_fn(admission.schema_version),
        version_to_decimal_fn(identity.scope.canonical_version),
        identity.scope.canonical,
        _optional(
            None
            if identity.idempotency_key is None
            else identifier_fn(identity.idempotency_key)
        ),
        bytes_fn(admission.semantic_input),
        bytes_fn(admission.protected_binding),
        admission.replay_policy.value.encode(),
        _decimal(integer_fn(admission.max_attempts, 1, 1000)),
        _optional(
            None if admission.deadline is None else _timestamp_fn(admission.deadline)
        ),
        _timestamp_fn(admission.original_available_at),
    ]
    raw = _record(b"work-intent", fields, _reject=_reject)
    return (CanonicalEvidence if _reject is None else _canonical_evidence_raw)(
        version=1, content=raw, digest=sha256(raw).digest()
    )


from dataclasses import dataclass
from uuid import UUID
from collections.abc import Sequence
from .catalog import (StatementSpec, ParameterSpec, ResultSpec, ColumnSpec, WireType,
                      ConstraintId, RecordKind, CardinalityKind)
from .models import AdmissionInput, EventInput, Fence, GuardRef, PublicationFence


def _scalar_core(value, wire_type, nullable, *, _reject=None):
    if type(wire_type) is not WireType or type(nullable) is not bool:
        _reject_scalar(_reject)
    if value is None:
        if not nullable:
            _reject_scalar(_reject)
        return None
    if wire_type is WireType.UUID:
        if type(value) is not UUID:
            _reject_scalar(_reject)
        return value
    if wire_type is WireType.BYTEA:
        return _bytes(value, _reject=_reject)
    if wire_type is WireType.TEXT:
        if type(value) is not str or len(value) > _MAX:
            _reject_scalar(_reject)
        _utf8(value, _reject=_reject)
        return value
    if wire_type is WireType.INT4:
        return _integer(value, -(2**31), 2**31 - 1, _reject=_reject)
    if wire_type is WireType.INT8:
        return _integer(value, -(2**63), 2**63 - 1, _reject=_reject)
    if wire_type is WireType.XID8:
        return _integer(value, 1, 2**64 - 1, _reject=_reject)
    if wire_type is WireType.FLOAT8:
        if type(value) not in (int, float):
            _reject_scalar(_reject)
        result = float(value)
        if not math.isfinite(result):
            _reject_scalar(_reject)
        return result
    if wire_type is WireType.BOOL:
        if type(value) is not bool:
            _reject_scalar(_reject)
        return value
    if wire_type is WireType.TIMESTAMPTZ:
        return _instant(value, _reject=_reject)
    if wire_type in (WireType.BYTEA_ARRAY, WireType.INT4_ARRAY):
        if isinstance(value, (str, bytes, bytearray, memoryview)):
            _reject_scalar(_reject)
        result = []
        base = WireType.BYTEA if wire_type is WireType.BYTEA_ARRAY else WireType.INT4
        for index, item in enumerate(value):
            if index >= 256:
                _reject_scalar(_reject)
            result.append(_scalar(item, base, False))
        return tuple(result)
    _reject_scalar(_reject)



@_boundary
def _scalar(value, wire_type, nullable):
    return _scalar_core(value, wire_type, nullable)


_RAW_SCALAR_TYPES = frozenset((
    WireType.UUID, WireType.BYTEA, WireType.TEXT, WireType.INT4,
    WireType.INT8, WireType.XID8, WireType.BOOL, WireType.TIMESTAMPTZ, WireType.FLOAT8,
))


def _scalar_raw(value, wire_type, nullable):
    """Exact immutable raw scalar validation; unsupported kinds fail closed."""
    if type(wire_type) is not WireType or wire_type not in _RAW_SCALAR_TYPES:
        _reject_validation()
    if wire_type is WireType.BYTEA and value is not None and type(value) is not bytes:
        _reject_validation()
    if wire_type is WireType.FLOAT8:
        if type(value) is not float or not math.isfinite(value):
            _reject_validation()
        return value
    if value is not None and wire_type is WireType.TIMESTAMPTZ:
        return _instant_raw(value)
    if value is not None and wire_type is WireType.UUID:
        return _uuid_raw(value)
    return _scalar_core(value, wire_type, nullable, _reject=_reject_validation)


def _statement_shape(statement):
    if type(statement) is not StatementSpec:raise ValueError
    statement.__post_init__()
    if type(statement.result) is not ResultSpec:raise ValueError
    statement.result.__post_init__()
    for parameter in statement.parameters:
        if type(parameter) is not ParameterSpec:raise ValueError
        parameter.__post_init__()
    for column in statement.result.columns:
        if type(column) is not ColumnSpec:raise ValueError
        column.__post_init__()


def _statement_shape_raw(statement):
    """Revalidate actual selected metadata without public constructor boundaries."""
    if type(statement) is not StatementSpec:
        _reject_validation()
    from . import catalog

    expected_key = next((key for key in ("E05", "E06", "E08", "E09", "E10", "E11", "E14", "E28", "E32")
                         if statement is catalog.get_statement(key)), None)
    if expected_key is None:
        _reject_validation()
    key = statement.key
    if type(key) is not str or key != expected_key:
        _reject_validation()
    catalog._validate_statement_spec(statement, _reject=_reject_validation)
    catalog._validate_result_spec(statement.result, _reject=_reject_validation)
    for parameter in statement.parameters:
        catalog._validate_parameter_spec(parameter, _reject=_reject_validation)
    for column in statement.result.columns:
        catalog._validate_column_spec(column, _reject=_reject_validation)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ReadinessExpectation:
    components: tuple

    @_boundary
    def __post_init__(self):
        from .observations import SchemaStatus
        if type(self.components) is not tuple or not 1<=len(self.components)<=2:raise ValueError
        for value in self.components:
            if type(value) is not SchemaStatus:raise ValueError
            value.__post_init__()
            if (value.catalog_contract_id,value.scope_format_id,value.intent_format_id)!=('modkit-pg-ab-2','MKSC-1','MKPF-1'):raise ValueError
        if tuple(v.component for v in self.components) not in (('events',),('events','workers')):raise ValueError


def _validate_empty_context_fields(expected, readiness, *, _reject):
    if type(expected) is not tuple or expected or readiness is not None:
        _reject_scalar(_reject)


def _validate_return_context(context, *, _reject=None):
    if _reject is not None:
        if (
            type(context.expected) is not tuple
            or len(context.expected) > 1
            or context.readiness is not None
        ):
            _reject_scalar(_reject)
        from .models import _validate_admission_input_raw, _validate_fence_raw

        for value in context.expected:
            if type(value) is Fence:
                _validate_fence_raw(value)
            elif type(value) is GuardRef:
                _validate_guard_ref_raw(value)
            else:
                _validate_admission_input_raw(value)
        return
    allowed = (AdmissionInput, EventInput, Fence, GuardRef, PublicationFence)
    if type(context.expected) is not tuple or len(context.expected) > 2:
        _reject_scalar(_reject)
    if len({type(v) for v in context.expected}) != len(context.expected):
        _reject_scalar(_reject)
    for value in context.expected:
        if type(value) not in allowed:
            _reject_scalar(_reject)
        value.__post_init__()
    if context.readiness is not None:
        if type(context.readiness) is not ReadinessExpectation:
            _reject_scalar(_reject)
        context.readiness.__post_init__()


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ReturnContext:
    expected: tuple
    readiness: ReadinessExpectation | None

    @_boundary
    def __post_init__(self):
        _validate_return_context(self)


@dataclass(slots=True)
class _ReturnContextDraft:
    expected: object
    readiness: object


def _return_context_raw(*, expected=(), readiness=None):
    """Construct empty or one-admission context without a public boundary."""
    draft = _ReturnContextDraft(expected, readiness)
    _validate_return_context(draft, _reject=_reject_validation)
    context = object.__new__(ReturnContext)
    object.__setattr__(context, "expected", draft.expected)
    object.__setattr__(context, "readiness", draft.readiness)
    return context


def _constraint(value, code, *, _reject=None):
    if type(code) is not ConstraintId:
        _reject_scalar(_reject)
    if value is None:
        return
    name = code.value
    identifiers={'subscription_id','namespace','command_type','idempotency_key','scope_application','scope_tenant','scope_owner','event_id','consumer_group','effect_id','provider_key_reference','protected_codec','protected_key_version'}
    if name in identifiers:
        if _reject is None:
            _identifier(value.decode("utf8"))
        else:
            _identifier_raw(_decode_utf8(_bytes_raw(value), _reject=_reject))
        return
    if name=='scope_evidence':
        from .scope import decode_canonical_scope
        decode_canonical_scope(value);return
    if name=='schema_version_decimal':version_from_decimal(value);return
    if name=='canonical_version':_integer(value,1,1);return
    bounds={'max_attempts':(1,1000),'capacity':(1,2147483647),'limit':(1,256),'discovery_budget':(1,4096),'ownership_revision':(1,2**63-1),'expected_revision':(0,2**63-1),'cycle':(1,1),'expected_attempt':(0,1000),'attempt':(1,1000),'after_id':(0,2**63-1),'after_cycle':(0,2147483647),'after_attempt':(0,2147483647)}
    if name in bounds:_integer(value,*bounds[name]);return
    if name=='lease_seconds':
        if not 0<value<=3600:raise ValueError
        return
    if name=='outbox_cursor':
        if len(value)!=32:raise ValueError
        return
    if name=='receipt':
        if len(value)>4096:raise ValueError
        return
    enums={'kind':('job','inbox'),'replay_policy':('disabled','application_safe'),'failure_outcome':('failed','cancelled','retry_waiting'),'publication_status':('confirmed','rejected','uncertain'),'repair_status':('published','rejected'),'resolution_outcome':('confirmed_success','confirmed_rejection','confirmed_cancelled','safe_retry'),'required_profile':('events','workers'),'material_state':('absent','present'),'protected_cleanup_policy':('retain','erase_after_terminal')}
    if name in enums:
        if value not in enums[name]:raise ValueError
        return
    if name=='reason':
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,255}',value):raise ValueError
        return
    if name=='command_types':
        for raw in value:_identifier(raw.decode('utf8'))
        return
    if name=='schema_versions':
        for version in value:_integer(version,1,2147483647)
        return
    # Structural scalars and bounded opaque evidence have no further standalone
    # semantics; their cross-field relationships are checked below.
    permitted={'work_id','token','expected_token','dispatch_id','intent_id','operation_id','guard_id','root_xid','failed_business_root','work_cursor','after_work_id','deadline','original_available_at','available_at','retry_at','after_created_at','protected_expires_at','supported','manifest','broker_reference','transport_observation','intent_evidence','semantic_input','replay_input','protected_binding','envelope_evidence','request_evidence','result','evidence','binding','protected_sidecar','protected_reference','protected_recovery_metadata','projection_metadata'}
    if name not in permitted:raise ValueError


def _validate_guard_ref_raw(value, /):
    """Check the retained reference directly, without reconstructing a Fence."""
    if type(value) is not GuardRef:
        _reject_validation()
    for name in ("guard_id", "work_id", "token"):
        _uuid_raw(getattr(value, name))
    _integer_raw(value.root_xid, 1, 2**64 - 1)
    _integer_raw(value.ownership_revision, 1, 2**63 - 1)
    _integer_raw(value.cycle, 1, 1)
    _integer_raw(value.expected_attempt, 0, 1000)


def _constraint_raw(value, code):
    """Only constraints reached by the fixed selected Events requests."""
    if type(code) is not ConstraintId:
        _reject_validation()
    if code in (ConstraintId.EVENT_ID, ConstraintId.EFFECT_ID,
                ConstraintId.PROVIDER_KEY_REFERENCE):
        if value is not None:
            _identifier_raw(_decode_utf8(_bytes_raw(value), _reject=_reject_validation))
        return
    bounds = {"ownership_revision": (1, 2**63 - 1), "cycle": (1, 1),
              "expected_attempt": (0, 1000)}
    if code.value in bounds:
        _integer_raw(value, *bounds[code.value])
        return
    if code.value == "lease_seconds":
        if type(value) is not float or not math.isfinite(value) or not 0 < value <= 3600:
            _reject_validation()
        return
    if code.value == "failure_outcome":
        if type(value) is not str or value not in ("failed", "cancelled", "retry_waiting"):
            _reject_validation()
        return
    if code.value == "reason":
        if type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,255}", value) is None:
            _reject_validation()
        return
    if code.value not in ("work_id", "token", "dispatch_id", "request_evidence",
                          "guard_id", "root_xid", "result", "failed_business_root",
                          "retry_at", "evidence", "operation_id", "binding"):
        _reject_validation()


def _admission_values_core(admission, *, _reject=None):
    identifier_fn = _identifier if _reject is None else _identifier_raw
    version_to_decimal_fn = (
        version_to_decimal if _reject is None else _version_to_decimal_raw
    )
    canonical_intent_fn = canonical_intent if _reject is None else _canonical_intent_raw
    identity = admission.identity
    scope = identity.scope
    return dict(
        work_id=identity.work_id,
        kind=identity.kind.value,
        subscription_id=None
        if identity.subscription_id is None
        else identifier_fn(identity.subscription_id),
        namespace=identifier_fn(identity.namespace),
        command_type=identifier_fn(identity.command_type),
        scope_evidence=scope.canonical,
        idempotency_key=None
        if identity.idempotency_key is None
        else identifier_fn(identity.idempotency_key),
        canonical_version=scope.canonical_version,
        schema_version_decimal=version_to_decimal_fn(admission.schema_version),
        scope_application=scope.application,
        scope_tenant=scope.tenant,
        scope_owner=scope.owner,
        intent_evidence=canonical_intent_fn(admission).content,
        semantic_input=admission.semantic_input,
        replay_input=admission.replay_input,
        protected_binding=admission.protected_binding,
        replay_policy=admission.replay_policy.value,
        max_attempts=admission.max_attempts,
        deadline=admission.deadline,
        original_available_at=admission.original_available_at,
    )



def _admission_values(admission):
    return _admission_values_core(admission)


def _admission_values_raw(admission, /):
    from .models import _validate_admission_input_raw

    _validate_admission_input_raw(admission)
    return _admission_values_core(admission, _reject=_reject_validation)


def _snapshot_sequence(values, maximum, *, _reject=None):
    """Read a Sequence once, bounding actual items rather than trusting __len__."""
    if not isinstance(values, Sequence) or isinstance(
        values, (str, bytes, bytearray, memoryview)
    ):
        _reject_scalar(_reject)
    result = []
    for index, value in enumerate(values):
        if index >= maximum:
            _reject_scalar(_reject)
        result.append(value)
    return tuple(result)


def _freeze_parameters(statement, parameters, context, *, _reject=None):
    (_statement_shape if _reject is None else _statement_shape_raw)(statement)
    if type(context) is not ReturnContext:
        _reject_scalar(_reject)
    if _reject is None:
        context.__post_init__()
    else:
        _validate_return_context(context, _reject=_reject)
    if _reject is not None and type(parameters) is not tuple:
        _reject_scalar(_reject)
    parameters = (
        _snapshot_sequence(parameters, len(statement.parameters))
        if _reject is None
        else _snapshot_sequence(parameters, len(statement.parameters), _reject=_reject)
    )
    if len(parameters) != len(statement.parameters):
        _reject_scalar(_reject)
    frozen = tuple(
        (_scalar if _reject is None else _scalar_raw)(
            value, spec.wire_type, spec.nullable
        )
        for spec, value in zip(statement.parameters, parameters)
    )
    for spec, value in zip(statement.parameters, frozen):
        (_constraint if _reject is None else _constraint_raw)(value, spec.constraint)
    p = dict(zip((s.name for s in statement.parameters), frozen))
    key = statement.key
    expected_types = {
        "E02": (EventInput,),
        "E03": (AdmissionInput, EventInput),
        "W01": (AdmissionInput,),
        "E05": (Fence,),
        "E06": (Fence,),
        "E07": (Fence,),
        "E08": (Fence,),
        "E09": (Fence,),
        "E10": (GuardRef,),
        "E11": (Fence,),
        "E23": (PublicationFence,),
        "E24": (PublicationFence,),
        "E25": (PublicationFence,),
        "E32": (Fence,),
    }.get(key, ())
    if {type(v) for v in context.expected} != set(expected_types):
        _reject_scalar(_reject)
    if key == "E33":
        if context.readiness is None or tuple(
            v.component for v in context.readiness.components
        ) != (
            ("events",) if p["required_profile"] == "events" else ("events", "workers")
        ):
            _reject_scalar(_reject)
    elif context.readiness is not None:
        _reject_scalar(_reject)
    for expected in context.expected:
        if type(expected) is AdmissionInput:
            for name, value in _admission_values(expected).items():
                if p[name] != value:
                    _reject_scalar(_reject)
        elif type(expected) is EventInput:
            cv = "event_canonical_version" if key == "E03" else "canonical_version"
            rp = "event_replay_input" if key == "E03" else "replay_input"
            if (p["event_id"], p[cv], p["envelope_evidence"], p[rp]) != (
                expected.event_id_bytes,
                1,
                expected.evidence.content,
                expected.replay_envelope,
            ):
                _reject_scalar(_reject)
            if key == "E03" and (
                p["semantic_input"] != expected.evidence.content
                or p["replay_input"] != expected.replay_envelope
            ):
                _reject_scalar(_reject)
        elif type(expected) in (Fence, GuardRef):
            for name in expected.__dataclass_fields__:
                if p[name] != getattr(expected, name):
                    _reject_scalar(_reject)
        elif type(expected) is PublicationFence:
            if (p["event_id"], p["token"], p["ownership_revision"]) != (
                _identifier(expected.event_id),
                expected.token,
                expected.ownership_revision,
            ):
                _reject_scalar(_reject)
    if "kind" in p and "subscription_id" in p:
        if (p["kind"] == "job") != (p["subscription_id"] is None):
            _reject_scalar(_reject)
    if key in ("W01", "W04") and (p["kind"] != "job" or p["namespace"] != b"jobs"):
        _reject_scalar(_reject)
    if key in ("W03", "W05") and p["namespace"] != b"jobs":
        _reject_scalar(_reject)
    if key in ("E03", "E34") and p["kind"] != "inbox":
        _reject_scalar(_reject)
    if "command_types" in p:
        pairs = tuple(zip(p["command_types"], p["schema_versions"]))
        if (
            not pairs
            or len(p["command_types"]) != len(p["schema_versions"])
            or len(set(pairs)) != len(pairs)
        ):
            _reject_scalar(_reject)
    if "discovery_budget" in p and p["discovery_budget"] < p["limit"]:
        _reject_scalar(_reject)
    if key == "E12" and (p["expected_token"] is None) != (
        p["expected_revision"] is None
    ):
        _reject_scalar(_reject)
    if key in ("E30", "W03") and (p["after_created_at"] is None) != (
        p["after_work_id"] is None
    ):
        _reject_scalar(_reject)
    if key in ("E11", "E31"):
        retry = p["outcome"] in ("retry_waiting", "safe_retry")
        if retry != (p["retry_at"] is not None):
            _reject_scalar(_reject)
        if key == "E31" and (p["outcome"] == "confirmed_success") != (
            p["result"] is not None
        ):
            _reject_scalar(_reject)
    if key == "W01":
        material = decode_protected_binding(p["protected_binding"])
        values = {
            "material_state": material.material_state.value,
            "protected_sidecar": material.sidecar,
            "protected_reference": material.reference,
            "protected_codec": None
            if material.codec is None
            else _identifier(material.codec),
            "protected_key_version": None
            if material.key_version is None
            else _identifier(material.key_version),
            "protected_expires_at": material.expires_at,
            "protected_recovery_metadata": material.recovery_metadata,
            "protected_cleanup_policy": material.cleanup_policy.value,
            "projection_metadata": material.projection_metadata,
        }
        if any(p[n] != v for n, v in values.items()):
            _reject_scalar(_reject)
    return frozen


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class FrozenRequest:
    statement: StatementSpec
    parameters: tuple
    context: ReturnContext

    @_boundary
    def __post_init__(self):
        object.__setattr__(self,'parameters',_freeze_parameters(self.statement,self.parameters,self.context))


@_boundary
def freeze_request(statement,parameters,/,*,context):
    return FrozenRequest(statement=statement,parameters=parameters,context=context)



def _freeze_request_raw(statement, parameters, /, *, context):
    """Validate the fixed selected Events graph before creating its final carrier."""
    from .catalog import get_statement

    if statement is get_statement("E05"):
        # Constructor-only normalization under the caller's paid construction
        # frame. Retained-graph validation never coerces an integer to float.
        _statement_shape_raw(statement)
        if type(parameters) is not tuple or len(parameters) != 6:
            _reject_validation()
        seconds = parameters[5]
        if type(seconds) not in (int, float) or not 0 < seconds <= 3600:
            _reject_validation()
        parameters = parameters[:5] + (float(seconds),)
    frozen = _freeze_parameters(statement, parameters, context, _reject=_reject_validation)
    request = object.__new__(FrozenRequest)
    object.__setattr__(request, "statement", statement)
    object.__setattr__(request, "parameters", frozen)
    object.__setattr__(request, "context", context)
    return request


def _instant_raw(value):
    if type(value) is not datetime or value.tzinfo is not timezone.utc:
        _reject_validation()
    return value


def _uuid_raw(value):
    from uuid import SafeUUID

    if type(value) is not UUID:
        _reject_validation()
    if type(value.int) is not int or not 0 <= value.int < 2**128:
        _reject_validation()
    if not any(
        value.is_safe is choice
        for choice in (SafeUUID.safe, SafeUUID.unsafe, SafeUUID.unknown)
    ):
        _reject_validation()
    return value


@_boundary
def canonical_protected_binding(material):
    return _canonical_protected_binding_core(material)


def _canonical_protected_binding_raw(material, /):
    return _canonical_protected_binding_core(material, _reject=_reject_validation)


@_boundary
def decode_protected_binding(raw):
    return _decode_protected_binding_core(raw)


def _decode_protected_binding_raw(raw, /):
    return _decode_protected_binding_core(raw, _reject=_reject_validation)


@_boundary
def canonical_intent(admission):
    return _canonical_intent_core(admission)


def _canonical_intent_raw(admission, /):
    return _canonical_intent_core(admission, _reject=_reject_validation)


def _protected_binding_input_raw(**values):
    from types import SimpleNamespace

    draft = SimpleNamespace(**values)
    normalized = _normalize_material(draft, _reject=_reject_validation)
    material = object.__new__(ProtectedBindingInput)
    for name in ProtectedBindingInput.__dataclass_fields__:
        object.__setattr__(material, name, normalized.get(name, values[name]))
    return material
