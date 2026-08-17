from datetime import datetime, timedelta, timezone

from app.alert_intelligence import (
    AlertCandidate,
    AlertDecision,
    PriorAlertState,
    evaluate_alert_policy,
)

UTC = timezone.utc
BASE = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _prior(**updates):
    base = dict(
        fingerprint="operations|orders|istanbul",
        last_notified_at=BASE,
        last_priority_score=0.60,
        evidence_refs=("ops://orders",),
        resolved=False,
    )
    base.update(updates)
    return PriorAlertState(**base)


def _candidate(**updates):
    base = dict(
        fingerprint="operations|orders|istanbul",
        observed_at=BASE + timedelta(minutes=20),
        priority_score=0.62,
        evidence_refs=("ops://orders",),
        resolved=False,
    )
    base.update(updates)
    return AlertCandidate(**base)


def test_duplicate_alert_inside_cooldown_is_suppressed():
    result = evaluate_alert_policy(_candidate(), _prior())

    assert result.decision is AlertDecision.SUPPRESS_COOLDOWN
    assert result.should_notify is False


def test_material_priority_escalation_breaks_cooldown():
    result = evaluate_alert_policy(
        _candidate(priority_score=0.82),
        _prior(),
    )

    assert result.decision is AlertDecision.RENOTIFY_ESCALATION
    assert result.should_notify is True


def test_new_evidence_can_trigger_renotification_after_short_guard_period():
    result = evaluate_alert_policy(
        _candidate(
            observed_at=BASE + timedelta(minutes=40),
            evidence_refs=("ops://orders", "weather://rain"),
        ),
        _prior(),
    )

    assert result.decision is AlertDecision.RENOTIFY_NEW_EVIDENCE
    assert result.new_evidence_refs == ("weather://rain",)


def test_resolution_update_is_not_silently_suppressed():
    result = evaluate_alert_policy(
        _candidate(resolved=True),
        _prior(),
    )

    assert result.decision is AlertDecision.RESOLUTION_UPDATE
    assert result.should_notify is True


def test_reopened_resolved_alert_is_renotified():
    result = evaluate_alert_policy(
        _candidate(priority_score=0.40),
        _prior(resolved=True, last_priority_score=0.30),
    )

    assert result.decision is AlertDecision.RENOTIFY_ESCALATION
    assert result.should_notify is True
    assert "previously_resolved_alert_reopened" in result.warnings
