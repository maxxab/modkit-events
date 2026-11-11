"""Cooperative single-lane recovery requirements; no driver import at import time.

M/R are retained Python logical bytes, D is construction-frame count. None is
an allocator/RSS promise. This finite profile is intentionally limited to the
reviewed CPython 3.12.3 Linux 64-bit layout plus the bounded 3.13.5 Linux
x86_64 conventional-GIL/nondebug qualification branch. Driver identity remains
psycopg binary 3.3.8/libpq 180006. Actual 3.13 product qualification is separate.
"""

import platform
import struct
import sys
import sysconfig
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from .bindings import (
    FrozenRequest,
    ReadinessExpectation,
    ReturnContext,
    _freeze_parameters,
    _validate_readiness_expectation_raw,
)
from .catalog import WireType, get_statement
from .errors import ErrorCode, _fail, _reject_validation, _ValidationReject
from .observations import ScanPage, SchemaStatus, WorkObservation

_INTERPRETER = "cpython-3.12.3-linux-64-recovery-v1"
_CONTRACT = "modkit-e13-recovery-logical-v1"
_DRIVER = ("3.3.8", 180006, "binary")
_UNITS = "retained-python-bytes/construction-frame-count"
# Exact canonical order, not a projection. Generated from the reviewed E13 table.
_CAPS = (
    ("record_type", 6),
    ("visited", 4),
    ("next_cursor", 16),
    ("pass_exhausted", 1),
    ("work_id", 16),
    ("kind", 5),
    ("subscription_id", 256),
    ("namespace", 256),
    ("command_type", 256),
    ("schema_version_decimal", 4096),
    ("runnable_version", 4),
    ("canonical_version", 4),
    ("scope_evidence", 781),
    ("scope_application", 256),
    ("scope_tenant", 256),
    ("scope_owner", 256),
    ("idempotency_key", 256),
    ("intent_evidence", 1048576),
    ("semantic_input", 1048576),
    ("replay_input", 1048576),
    ("protected_binding", 1048576),
    ("replay_policy", 16),
    ("max_attempts", 4),
    ("deadline", 8),
    ("original_available_at", 8),
    ("state", 14),
    ("cancellation_requested", 1),
    ("token", 16),
    ("ownership_revision", 8),
    ("lease_until", 8),
    ("available_at", 8),
    ("cycle", 4),
    ("attempt_count", 4),
    ("dispatch_id", 16),
    ("result", 1048576),
    ("created_at", 8),
    ("updated_at", 8),
    ("success_origin", 10),
    ("completion_guard_id", 16),
    ("final_fence_at", 8),
    ("completion_result_digest", 32),
    ("resolution_operation_id", 16),
    ("terminal_resolution_operation_id", 16),
    ("resolution_present", 1),
    ("resolution_record_operation_id", 16),
    ("resolution_record_operation_kind", 14),
    ("resolution_record_work_id", 16),
    ("resolution_record_expected_revision", 8),
    ("resolution_record_cycle", 4),
    ("resolution_record_attempt", 4),
    ("resolution_record_dispatch_id", 16),
    ("resolution_record_outcome", 19),
    ("resolution_record_retry_at", 8),
    ("resolution_record_result", 1048576),
    ("resolution_record_result_digest", 32),
    ("resolution_record_reason", 256),
    ("resolution_record_evidence", 1048576),
    ("resolution_record_binding", 1048576),
    ("resolution_record_resolution_root_xid", 8),
    ("resolution_record_recorded_at", 8),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryRequirements:
    contract_id: str
    interpreter_profile_id: str
    namespace: bytes
    kind: str
    page_limit: int
    discovery_min: int
    discovery_default: int
    discovery_max: int
    required_profile: str
    readiness: ReadinessExpectation
    e13_preparation_min: int
    e13_result_min: int
    e33_preparation_min: int
    e33_result_min: int
    lifecycle_minimum: object
    driver_requirement: tuple
    logical_units: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifiedRecoveryProfile:
    requirements: RecoveryRequirements
    interpreter_profile_id: str
    observed_psycopg_version: str
    observed_libpq_version: int
    observed_driver_implementation: str
    supported_profile_id: str


def _layout():
    version = tuple(sys.version_info[:3])
    if (
        sys.implementation.name != "cpython"
        or version not in ((3, 12, 3), (3, 13, 5))
        or sys.platform != "linux"
        or struct.calcsize("P") != 8
        or sys.int_info.bits_per_digit != 30
        or sys.int_info.sizeof_digit != 4
    ):
        _reject_validation()
    interpreter = _INTERPRETER
    if version == (3, 13, 5):
        if tuple(sys.version_info) != (3, 13, 5, "final", 0):
            _reject_validation()
        # These restrictions apply only to the newly qualified branch; do not
        # retroactively narrow the existing 3.12 layout/profile contract.
        debug = sysconfig.get_config_var("Py_DEBUG")
        free_threaded = sysconfig.get_config_var("Py_GIL_DISABLED")
        gil_enabled = getattr(sys, "_is_gil_enabled", None)
        if (
            platform.machine() != "x86_64"
            or type(debug) is not int
            or debug != 0
            or type(free_threaded) is not int
            or free_threaded != 0
            or not callable(gil_enabled)
            or gil_enabled() is not True
        ):
            _reject_validation()
        interpreter = "cpython-3.13.5-linux-x86_64-gil-release-recovery-v1"
    samples = (
        (None, 16),
        (True, 28),
        (b"", 33),
        ("", 64),
        (chr(0x10000), 68),
        (0, 28),
        (2**128 - 1, 44),
        (UUID(int=0), 64),
        (datetime(2000, 1, 1, tzinfo=timezone.utc), 48),
    )
    for value, maximum in samples:
        if sys.getsizeof(value) > maximum:
            _reject_validation()
    for n in (0, 1, 5, 256):
        if sys.getsizeof((None,) * n) > _tuple(n):
            _reject_validation()
    for cls, maximum in (
        (FrozenRequest, 56),
        (ReturnContext, 48),
        (ReadinessExpectation, 40),
        (WorkObservation, 352),
        (ScanPage, 64),
        (SchemaStatus, 80),
    ):
        if sys.getsizeof(object.__new__(cls)) > maximum:
            _reject_validation()
    return interpreter


def _tuple(n):
    return 40 + 8 * n


def _bytes(n):
    return 33 + n


def _text(n):
    # UTF-8 length bounds codepoints; kind4 is representation-safe.
    return 64 + 4 * n


def _integer(bits):
    return 24 + 4 * max(1, (bits + 29) // 30)


def _recovery_preparation_min():
    _layout()
    return (
        56 + _tuple(5) + _bytes(256) + _text(5) + _integer(9) + 108 + _integer(13) + 48 + _tuple(0)
    )


def _column_max(column, cap):
    kind = column.wire_type
    if kind is WireType.BYTEA:
        size = _bytes(cap)
    elif kind is WireType.TEXT:
        size = _text(cap)
    elif kind is WireType.UUID:
        size = 108
    elif kind is WireType.TIMESTAMPTZ:
        size = 48
    elif kind is WireType.BOOL:
        size = 28
    elif kind is WireType.INT4:
        size = _integer(32)
    elif kind in (WireType.INT8, WireType.XID8):
        size = _integer(64)
    else:
        _reject_validation()
    return max(size, 16) if column.nullable else size


def _recovery_result_min(limit):
    _layout()
    if type(limit) is not int or not 1 <= limit <= 256:
        _reject_validation()
    base = get_statement("E13").result.columns[4:43]
    if len(base) != 39 or tuple(c.name for c in base) != tuple(name for name, cap in _CAPS[4:43]):
        _reject_validation()
    work = 352 + sum(_column_max(c, cap) for c, (_, cap) in zip(base, _CAPS[4:43])) + 16
    return 64 + _tuple(limit) + limit * work + _integer(13) + 108 + 28


def _validate_recovery_request(request):
    _layout()
    if type(request) is not FrozenRequest or request.statement is not get_statement("E13"):
        _reject_validation()
    _freeze_parameters(
        request.statement, request.parameters, request.context, _reject=_reject_validation
    )
    return request.parameters[2]


def _readiness_minima(expectation):
    _validate_readiness_expectation_raw(expectation)
    if tuple(s.component for s in expectation.components) != ("events", "workers"):
        _reject_validation()
    statuses = 0
    for status in expectation.components:
        statuses += (
            80 + _text(len(status.component.encode("utf8"))) + _integer(status.version.bit_length())
        )
        statuses += _bytes(len(status.migration_digest))
        statuses += sum(
            _text(len(v.encode("utf8")))
            for v in (status.catalog_contract_id, status.scope_format_id, status.intent_format_id)
        )
    result = _tuple(2) + statuses
    preparation = 56 + _tuple(1) + _text(7) + 48 + _tuple(0) + 40 + result
    return preparation, result


def recovery_requirements(*, readiness):
    """Pure, exact workers readiness expectations; no registry/connection work."""
    try:
        interpreter = _layout()
        a13 = _recovery_preparation_min()
        b13 = _recovery_result_min(1)
        a33, b33 = _readiness_minima(readiness)
    except _ValidationReject:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    # Importing the carrier is inert; no configure, counters or live-state reads.
    from .managed_lifecycle import LifecycleLimits

    a, b = max(a13, a33), max(b13, b33)
    minimum = LifecycleLimits(
        retained_cells=1,
        admitted_live=1,
        checkouts=1,
        roots=1,
        roots_per_checkout=1,
        executions=1,
        preparations=1,
        preparations_per_execution=1,
        prepare_bytes=a,
        prepare_bytes_per_execution=a,
        results=1,
        results_per_ticket=1,
        result_bytes=b,
        result_bytes_per_ticket=b,
        cleanup_bundles=1,
        cleanup_bytes=4096,
        construction_slots=2,
    )
    return RecoveryRequirements(
        contract_id=_CONTRACT,
        interpreter_profile_id=interpreter,
        namespace=b"jobs",
        kind="job",
        page_limit=1,
        discovery_min=1,
        discovery_default=128,
        discovery_max=4096,
        required_profile="workers",
        readiness=readiness,
        e13_preparation_min=a13,
        e13_result_min=b13,
        e33_preparation_min=a33,
        e33_result_min=b33,
        lifecycle_minimum=minimum,
        driver_requirement=_DRIVER,
        logical_units=_UNITS,
    )


def _verify_driver():
    _layout()
    try:
        import psycopg
        from psycopg import pq
    except ImportError:
        _reject_validation()
    version, lib, implementation = psycopg.__version__, pq.version(), pq.__impl__
    if (
        type(version) is not str
        or type(lib) is not int
        or type(implementation) is not str
        or (version, lib, implementation) != _DRIVER
    ):
        _reject_validation()
    return version, lib, implementation


def verify_recovery_driver(requirements, /):
    """Explicit optional dependency check; never creates any connection/cursor."""
    if type(requirements) is not RecoveryRequirements:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    expected = recovery_requirements(readiness=requirements.readiness)
    # Check field types before equality so forged fields cannot run comparison hooks.
    for name in RecoveryRequirements.__dataclass_fields__:
        value, wanted = getattr(requirements, name), getattr(expected, name)
        if type(value) is not type(wanted):
            _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    for name in expected.lifecycle_minimum.__dataclass_fields__:
        value = getattr(requirements.lifecycle_minimum, name)
        if type(value) is not int or value != getattr(expected.lifecycle_minimum, name):
            _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    driver = requirements.driver_requirement
    if len(driver) != 3 or any(
        type(value) is not type(wanted) for value, wanted in zip(driver, _DRIVER)
    ):
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    # readiness was raw-validated above and is the same object in expected.
    if requirements != expected:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    try:
        version, lib, implementation = _verify_driver()
    except _ValidationReject:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=False)
    return VerifiedRecoveryProfile(
        requirements=requirements,
        interpreter_profile_id=expected.interpreter_profile_id,
        observed_psycopg_version=version,
        observed_libpq_version=lib,
        observed_driver_implementation=implementation,
        supported_profile_id=_CONTRACT
        + "/"
        + expected.interpreter_profile_id
        + "/psycopg-binary-3.3.8-libpq-180006",
    )
