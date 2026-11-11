"""Logical execution identity and ordinary-operation synchronized uncertainty.

No resource registry, transaction authority or uninterruptible bookkeeping claim.
"""

from threading import Lock

from .errors import ErrorCode, _fail
from .observations import (
    Uncertainty,
    _join_uncertainty,
    _uncertainty_from_categories,
    _valid_uncertainty,
)


class ExecutionLedger:
    """One shared holder per execution; pass the same instance between wrappers.

    Completed reads/unions are linearizable. An interrupted union may or may not
    have published; it never undoes publication. Repeated asynchronous interrupts
    and uncertain mutex cleanup require caller fail-stop, not a replacement ledger.
    """

    __slots__ = ("_lock", "_incident_identity", "_uncertainty", "_managed_execution")

    def __init__(self) -> None:
        if hasattr(self, "_lock"):
            self._invalid()
        self._managed_execution = None  # Inert one-shot managed identity, never ledger payload.
        self._lock = Lock()
        self._incident_identity = object()
        self._uncertainty = _uncertainty_from_categories(frozenset())

    @property
    def incident_identity(self) -> object:
        return self._incident_identity

    @property
    def uncertainty(self) -> Uncertainty:
        with self._lock:
            snapshot = self._uncertainty
        return snapshot

    def _invalid(self) -> None:
        # This protected read is the invalid-operation linearization point.
        with self._lock:
            unconfirmed = self._uncertainty.present
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)

    def join_uncertainty(self, value: Uncertainty, /) -> None:
        if not _valid_uncertainty(value):
            self._invalid()
        with self._lock:
            # Sole existing union semantics; one complete immutable publication.
            candidate = _join_uncertainty(self._uncertainty, value)
            self._uncertainty = candidate

    def note_incident(self, code: ErrorCode, /) -> None:
        if type(code) is not ErrorCode:
            self._invalid()
        self.join_uncertainty(_uncertainty_from_categories(frozenset({code})))

    def __copy__(self):
        self._invalid()

    def __deepcopy__(self, memo):
        self._invalid()

    def __reduce_ex__(self, protocol):
        self._invalid()
