"""Cross-run alert fatigue control for EAY Jarvis.

Within-batch deduplication is not enough. This contract decides whether a risk
should be re-notified based on cooldown, meaningful severity change, new
evidence or resolution/reopen state. It does not send notifications itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

ALERT_INTELLIGENCE_CONTRACT = "eay-alert-intelligence-v1"


class AlertDecision(str, Enum):
    NOTIFY = "notify"
    SUPPRESS_COOLDOWN = "suppress_cooldown"
    RENOTIFY_ESCALATION = "renotify_escalation"
    RENOTIFY_NEW_EVIDENCE = "renotify_new_evidence"
    RESOLUTION_UPDATE = "resolution_update"


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class PriorAlertState(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=500)
    last_notified_at: datetime
    last_priority_score: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = ()
    resolved: bool = False

    @model_validator(mode="after")
    def validate_time(self) -> "PriorAlertState":
        if not _aware(self.last_notified_at):
            raise ValueError("prior_alert_timezone_required")
        return self


class AlertCandidate(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=500)
    observed_at: datetime
    priority_score: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    resolved: bool = False

    @model_validator(mode="after")
    def validate_time(self) -> "AlertCandidate":
        if not _aware(self.observed_at):
            raise ValueError("alert_candidate_timezone_required")
        return self


class AlertPolicyResult(BaseModel):
    contract: str = ALERT_INTELLIGENCE_CONTRACT
    fingerprint: str
    decision: AlertDecision
    should_notify: bool
    score_delta: float
    new_evidence_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def evaluate_alert_policy(
    candidate: AlertCandidate,
    prior: PriorAlertState | None,
    *,
    cooldown_minutes: int = 120,
    escalation_delta: float = 0.15,
) -> AlertPolicyResult:
    if cooldown_minutes < 1:
        raise ValueError("alert_cooldown_must_be_positive")
    if not 0.0 <= escalation_delta <= 1.0:
        raise ValueError("alert_escalation_delta_out_of_range")

    if prior is None or prior.fingerprint != candidate.fingerprint:
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.NOTIFY,
            should_notify=True,
            score_delta=candidate.priority_score,
            new_evidence_refs=candidate.evidence_refs,
        )

    if candidate.observed_at < prior.last_notified_at:
        raise ValueError("alert_candidate_precedes_prior_notification")

    prior_refs = set(prior.evidence_refs)
    new_refs = tuple(ref for ref in candidate.evidence_refs if ref not in prior_refs)
    delta = round(candidate.priority_score - prior.last_priority_score, 6)

    if candidate.resolved and not prior.resolved:
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.RESOLUTION_UPDATE,
            should_notify=True,
            score_delta=delta,
            new_evidence_refs=new_refs,
        )

    if prior.resolved and not candidate.resolved:
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.RENOTIFY_ESCALATION,
            should_notify=True,
            score_delta=delta,
            new_evidence_refs=new_refs,
            warnings=("previously_resolved_alert_reopened",),
        )

    if delta >= escalation_delta:
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.RENOTIFY_ESCALATION,
            should_notify=True,
            score_delta=delta,
            new_evidence_refs=new_refs,
        )

    elapsed = candidate.observed_at - prior.last_notified_at
    if new_refs and elapsed >= timedelta(minutes=min(cooldown_minutes, 30)):
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.RENOTIFY_NEW_EVIDENCE,
            should_notify=True,
            score_delta=delta,
            new_evidence_refs=new_refs,
        )

    if elapsed < timedelta(minutes=cooldown_minutes):
        return AlertPolicyResult(
            fingerprint=candidate.fingerprint,
            decision=AlertDecision.SUPPRESS_COOLDOWN,
            should_notify=False,
            score_delta=delta,
            new_evidence_refs=new_refs,
            warnings=("duplicate_alert_suppressed",),
        )

    return AlertPolicyResult(
        fingerprint=candidate.fingerprint,
        decision=AlertDecision.NOTIFY,
        should_notify=True,
        score_delta=delta,
        new_evidence_refs=new_refs,
    )
