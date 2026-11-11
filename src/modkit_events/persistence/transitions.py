"""Internal declarative SQL transition specification, not a runtime state engine.

Guards are named requirements enforced in PostgreSQL functions. This table does
not authorize state changes, prove a transaction outcome, or schedule execution.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class _TransitionRule:
    rule_id: str
    operation: str
    source: str
    target: str
    guard: str
    dispatch_pointer: str
    attempt_delta: int
    release_capacity: bool
    success_origin: str | None = None

    def __post_init__(self) -> None:
        if any(
            type(value) is not str or not value
            for value in (self.rule_id, self.operation, self.source, self.target, self.guard)
        ):
            raise ValueError("invalid transition specification")
        if self.dispatch_pointer not in ("null", "create", "retain", "clear_resolved"):
            raise ValueError("invalid dispatch pointer rule")
        if type(self.attempt_delta) is not int or self.attempt_delta not in (0, 1):
            raise ValueError("invalid attempt delta")
        if type(self.release_capacity) is not bool or self.success_origin not in (
            None,
            "guarded",
            "reconciled",
        ):
            raise ValueError("invalid transition effect")


def _rule(
    rule_id: str,
    operation: str,
    source: str,
    target: str,
    guard: str,
    pointer: str,
    *,
    attempt_delta: int = 0,
    release: bool = False,
    origin: str | None = None,
) -> _TransitionRule:
    return _TransitionRule(
        rule_id=rule_id,
        operation=operation,
        source=source,
        target=target,
        guard=guard,
        dispatch_pointer=pointer,
        attempt_delta=attempt_delta,
        release_capacity=release,
        success_origin=origin,
    )


# An exact recorded operation repeat returns its immutable observation BEFORE
# these transition effects; it never re-applies capacity/history/revision changes.
# Compound source labels enumerate exactly the permitted precondition states.
# Clock guards always mean database time after every acquired blocking lock.
_WORK_RULES = (
    _rule(
        "intake_runnable",
        "E03",
        "new",
        "queued",
        "identity_three_paths_capacity_supported_int4",
        "null",
    ),
    _rule(
        "intake_blocked",
        "E03",
        "new",
        "blocked_schema",
        "identity_three_paths_capacity_unsupported",
        "null",
    ),
    _rule(
        "claim",
        "E04",
        "queued|retry_waiting",
        "claimed",
        "due_capable_no_dispatch_no_cancel_live_deadline_budget_nonblocking",
        "null",
    ),
    _rule("renew", "E05", "claimed|running", "same", "live_exact_fence_deadline_capped", "retain"),
    _rule(
        "dispatch",
        "E06",
        "claimed",
        "running",
        "live_exact_fence_no_cancel_deadline_budget_prior_count_stable_intent",
        "create",
        attempt_delta=1,
    ),
    _rule(
        "defer",
        "E07",
        "claimed",
        "queued",
        "live_exact_fence_no_dispatch_no_cancel_future_before_deadline",
        "null",
    ),
    _rule(
        "arm_guard",
        "E08",
        "running",
        "same",
        "actual_root_live_fence_unsatisfied_before_associated_writes",
        "retain",
    ),
    _rule(
        "complete",
        "E10",
        "running",
        "succeeded",
        "current_root_guard_final_locked_live_fence_no_cancel_deadline_complete_last",
        "retain",
        release=True,
        origin="guarded",
    ),
    _rule(
        "failure_terminal",
        "E11",
        "running",
        "failed",
        "new_root_confirmed_failure_live_dispatched_fence_retry_null",
        "retain",
        release=True,
    ),
    _rule(
        "failure_cancelled",
        "E11",
        "running",
        "cancelled",
        "new_root_confirmed_no_effect_live_dispatched_fence_retry_null",
        "retain",
        release=True,
    ),
    _rule(
        "failure_retry",
        "E11",
        "running",
        "retry_waiting",
        "new_root_confirmed_failure_live_fence_safe_budget_no_cancel_future_before_deadline",
        "clear_resolved",
    ),
    _rule(
        "cancel_predispatch",
        "E12",
        "queued|retry_waiting|claimed|blocked_schema",
        "cancelled",
        "optional_observed_fence_no_unresolved_dispatch",
        "null",
        release=True,
    ),
    _rule(
        "cancel_running",
        "E12",
        "running",
        "held",
        "optional_observed_fence_dispatched_effect_not_undone",
        "retain",
    ),
    _rule(
        "cancel_held",
        "E12",
        "held",
        "held",
        "optional_observed_fence_first_request_only_revision_change",
        "retain",
    ),
    _rule(
        "cancel_terminal",
        "E12",
        "succeeded|failed|expired|cancelled",
        "same",
        "terminal_observation_no_mutation",
        "retain",
    ),
    _rule(
        "recover_expired_predispatch",
        "E13",
        "queued|retry_waiting|claimed|blocked_schema",
        "expired",
        "no_unresolved_dispatch_deadline_reached_nonblocking",
        "null",
        release=True,
    ),
    _rule(
        "recover_exhausted_predispatch",
        "E13",
        "queued|retry_waiting|claimed",
        "failed",
        "no_unresolved_dispatch_budget_exhausted_nonblocking",
        "null",
        release=True,
    ),
    _rule(
        "recover_claim",
        "E13",
        "claimed",
        "queued",
        "no_dispatch_expired_lease_live_deadline_budget_nonblocking",
        "null",
    ),
    _rule(
        "recover_dispatched",
        "E13",
        "running",
        "held",
        "dispatch_expired_lease_or_deadline_nonblocking",
        "retain",
    ),
    _rule(
        "reconcile_success",
        "E31",
        "held",
        "succeeded",
        "operation_exact_repeat_or_current_revision_confirmed_success_evidence",
        "retain",
        release=True,
        origin="reconciled",
    ),
    _rule(
        "reconcile_rejection",
        "E31",
        "held",
        "failed",
        "operation_exact_repeat_or_current_revision_confirmed_rejection_evidence",
        "retain",
        release=True,
    ),
    _rule(
        "reconcile_cancelled",
        "E31",
        "held",
        "cancelled",
        "operation_exact_repeat_or_current_revision_confirmed_no_effect_evidence",
        "retain",
        release=True,
    ),
    _rule(
        "reconcile_safe_retry",
        "E31",
        "held",
        "retry_waiting",
        "operation_exact_repeat_or_current_revision_proven_safe_policy_budget_no_cancel_future_before_deadline",
        "clear_resolved",
    ),
    _rule(
        "hold_uncertain",
        "E32",
        "running",
        "held",
        "operation_exact_repeat_or_new_root_live_dispatched_fence_uncertainty",
        "retain",
    ),
)
_PUBLICATION_RULES = (
    _rule("enqueue", "E02", "new", "pending", "full_event_identity_or_exact_duplicate", "null"),
    _rule(
        "claim_publication", "E22", "pending", "claimed", "bounded_nonblocking_live_lease", "null"
    ),
    _rule(
        "renew_publication",
        "E23",
        "claimed|publishing",
        "same",
        "live_exact_publication_fence",
        "retain",
    ),
    _rule(
        "publication_intent",
        "E24",
        "claimed",
        "publishing",
        "live_exact_fence_stable_intent_committed_before_io",
        "create",
    ),
    _rule(
        "publication_confirmed",
        "E25",
        "publishing",
        "published",
        "live_exact_fence_intent_confirmed_durability_evidence",
        "retain",
    ),
    _rule(
        "publication_rejected",
        "E25",
        "publishing",
        "rejected",
        "live_exact_fence_intent_confirmed_rejection",
        "retain",
    ),
    _rule(
        "publication_uncertain",
        "E25",
        "publishing",
        "held",
        "live_exact_fence_intent_uncertainty_or_insufficient_durability",
        "retain",
    ),
    _rule(
        "recover_publication_preintent",
        "E26",
        "claimed",
        "pending",
        "expired_lease_no_intent_nonblocking",
        "null",
    ),
    _rule(
        "recover_publication_intent",
        "E26",
        "publishing",
        "held",
        "expired_lease_any_intent_nonblocking",
        "retain",
    ),
    _rule(
        "repair_published",
        "E27",
        "held",
        "published",
        "operation_exact_repeat_or_current_revision_confirmed_evidence",
        "retain",
    ),
    _rule(
        "repair_rejected",
        "E27",
        "held",
        "rejected",
        "operation_exact_repeat_or_current_revision_confirmed_rejection",
        "retain",
    ),
)

# Package-internal persisted domains accepted by FL10-RECORD-CODES-DESIGN-1.
# Rule additions require reviewed history-domain impact; exact literal tests
# intentionally fail on an unintended new persisted code. No execution authority.
_WORK_HISTORY_CODES = frozenset(
    rule.rule_id for rule in _WORK_RULES if rule.rule_id not in ("arm_guard", "cancel_terminal")
)
_PUBLICATION_HISTORY_CODES = frozenset(rule.rule_id for rule in _PUBLICATION_RULES)
_ATTEMPT_OUTCOME_CODES = frozenset(
    {
        "dispatched",
        "succeeded",
        "failed",
        "cancelled",
        "uncertain",
        "cancelled_unresolved",
        "safe_retry",
    }
)

__all__ = ()
