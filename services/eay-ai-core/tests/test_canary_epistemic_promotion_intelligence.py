from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.canary_epistemic_activation import (
    ActivationReceipt,
    CanaryIdentity,
    HealthStatus,
    HealthVerdict,
    RolloutSnapshot,
    RolloutState,
    _seal,
)
from app.canary_epistemic_promotion import (
    PromotionDisposition,
    PromotionEvidence,
    assess_promotion_readiness,
    review_promotion,
    seal_promotion_approval,
)

NOW = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
IDENTITY = CanaryIdentity(
    tenant_id="tenant-a",
    company_id="company-a",
    problem_class="operations-root-cause",
    rollout_id="rollout-001",
)
CANDIDATE = "a" * 64
BASELINE = "b" * 64
BASELINE_PROFILE = "c" * 64


def _activation():
    return _seal(
        ActivationReceipt,
        "activation_fingerprint",
        {
            "identity": IDENTITY,
            "generation": 1,
            "candidate_fingerprint": CANDIDATE,
            "baseline_fingerprint": BASELINE,
            "baseline_profile_fingerprint": BASELINE_PROFILE,
            "shadow_acceptance_fingerprint": "e" * 64,
            "approval_fingerprint": "f" * 64,
            "maximum_exposure_fraction": 0.10,
            "activated_at": NOW - timedelta(hours=1),
        },
    )


def _snapshot(state=RolloutState.ACTIVE, generation=1):
    return _seal(
        RolloutSnapshot,
        "snapshot_fingerprint",
        {
            "identity": IDENTITY,
            "generation": generation,
            "state": state,
            "candidate_fingerprint": CANDIDATE,
            "baseline_fingerprint": BASELINE,
            "baseline_profile_fingerprint": BASELINE_PROFILE,
            "selected_profile_fingerprint": (
                CANDIDATE if state is RolloutState.ACTIVE else BASELINE_PROFILE
            ),
            "activation_fingerprint": _activation().activation_fingerprint,
            "rollback_fingerprint": None,
            "updated_at": NOW,
        },
    )


def _healthy(index: int, at: datetime):
    return _seal(
        HealthVerdict,
        "verdict_fingerprint",
        {
            "identity": IDENTITY,
            "generation": 1,
            "observation_fingerprint": f"{index:064x}",
            "status": HealthStatus.HEALTHY,
            "rollback_required": False,
            "blockers": (),
            "evaluated_at": at,
        },
    )


def _drifted(index: int, at: datetime):
    return _seal(
        HealthVerdict,
        "verdict_fingerprint",
        {
            "identity": IDENTITY,
            "generation": 1,
            "observation_fingerprint": f"{index:064x}",
            "status": HealthStatus.DRIFTED,
            "rollback_required": True,
            "blockers": ("canary_health_grounding_integrity_regression",),
            "evaluated_at": at,
        },
    )


def _ready_evidence():
    verdicts = (
        _healthy(1, NOW - timedelta(minutes=40)),
        _healthy(2, NOW - timedelta(minutes=20)),
        _healthy(3, NOW - timedelta(minutes=5)),
    )
    return assess_promotion_readiness(
        snapshot=_snapshot(),
        activation=_activation(),
        verdicts=verdicts,
        evaluated_at=NOW,
    )


def test_sustained_distinct_health_becomes_review_ready() -> None:
    evidence = _ready_evidence()
    assert evidence.disposition is PromotionDisposition.REVIEW_READY
    assert len(evidence.verdict_fingerprints) == 3
    assert len(evidence.observation_fingerprints) == 3
    assert evidence.automatic_promotion_allowed is False
    assert not any(evidence.authority.model_dump().values())


def test_single_or_short_health_window_cannot_promote() -> None:
    evidence = assess_promotion_readiness(
        snapshot=_snapshot(),
        activation=_activation(),
        verdicts=(
            _healthy(1, NOW - timedelta(minutes=8)),
            _healthy(2, NOW - timedelta(minutes=4)),
        ),
        evaluated_at=NOW,
    )
    assert evidence.disposition is PromotionDisposition.HOLD
    assert "canary_promotion_healthy_window_count_insufficient" in evidence.blockers
    assert "canary_promotion_observation_span_insufficient" in evidence.blockers


def test_duplicate_health_observation_cannot_count_twice() -> None:
    first = _healthy(1, NOW - timedelta(minutes=40))
    replay = _seal(
        HealthVerdict,
        "verdict_fingerprint",
        {
            "identity": IDENTITY,
            "generation": 1,
            "observation_fingerprint": first.observation_fingerprint,
            "status": HealthStatus.HEALTHY,
            "rollback_required": False,
            "blockers": (),
            "evaluated_at": NOW - timedelta(minutes=20),
        },
    )
    evidence = assess_promotion_readiness(
        snapshot=_snapshot(),
        activation=_activation(),
        verdicts=(first, replay, _healthy(3, NOW - timedelta(minutes=5))),
        evaluated_at=NOW,
    )
    assert evidence.disposition is PromotionDisposition.HOLD
    assert "canary_promotion_duplicate_health_observation" in evidence.blockers


def test_any_drifted_window_blocks_promotion() -> None:
    evidence = assess_promotion_readiness(
        snapshot=_snapshot(),
        activation=_activation(),
        verdicts=(
            _healthy(1, NOW - timedelta(minutes=40)),
            _drifted(2, NOW - timedelta(minutes=20)),
            _healthy(3, NOW - timedelta(minutes=5)),
        ),
        evaluated_at=NOW,
    )
    assert evidence.disposition is PromotionDisposition.HOLD
    assert "canary_promotion_requires_only_healthy_windows" in evidence.blockers


def test_stale_latest_health_blocks_promotion() -> None:
    evidence = assess_promotion_readiness(
        snapshot=_snapshot(),
        activation=_activation(),
        verdicts=(
            _healthy(1, NOW - timedelta(hours=2)),
            _healthy(2, NOW - timedelta(minutes=80)),
            _healthy(3, NOW - timedelta(minutes=30)),
        ),
        evaluated_at=NOW,
    )
    assert evidence.disposition is PromotionDisposition.HOLD
    assert "canary_promotion_latest_health_evidence_stale" in evidence.blockers


def test_rolled_back_snapshot_cannot_be_promoted() -> None:
    active = _snapshot()
    rolled_back = active.model_copy(
        update={
            "state": RolloutState.ROLLED_BACK,
            "generation": 2,
            "selected_profile_fingerprint": BASELINE_PROFILE,
            "rollback_fingerprint": "9" * 64,
        }
    )
    with pytest.raises(ValueError):
        assess_promotion_readiness(
            snapshot=rolled_back,
            activation=_activation(),
            verdicts=(),
            evaluated_at=NOW,
        )


def test_promotion_requires_second_verified_review() -> None:
    evidence = _ready_evidence()
    with pytest.raises(ValueError, match="requires_verified_review_authority"):
        seal_promotion_approval(
            evidence=evidence,
            approved_by_ref="principal://reviewer",
            review_authority_ref="authority://promotion-review",
            review_authority_verified=False,
            approval_evidence_ref="approval://promotion-001",
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )


def test_review_receipt_never_performs_activation_or_grants_authority() -> None:
    evidence = _ready_evidence()
    approval = seal_promotion_approval(
        evidence=evidence,
        approved_by_ref="principal://reviewer",
        review_authority_ref="authority://promotion-review",
        review_authority_verified=True,
        approval_evidence_ref="approval://promotion-001",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    receipt = review_promotion(
        snapshot=_snapshot(),
        evidence=evidence,
        approval=approval,
        reviewed_at=NOW + timedelta(minutes=1),
    )
    assert receipt.promotion_review_passed is True
    assert receipt.production_activation_performed is False
    assert not any(receipt.authority.model_dump().values())


def test_tampered_evidence_is_rejected_before_review() -> None:
    evidence = _ready_evidence()
    tampered = evidence.model_copy(update={"candidate_fingerprint": "9" * 64})
    with pytest.raises(ValueError, match="evidence_fingerprint_mismatch"):
        PromotionEvidence.model_validate(tampered.model_dump(mode="json"))
