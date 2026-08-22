from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.canary_epistemic_activation import (
    ActivationApproval,
    ActivationReceipt,
    CanaryIdentity,
    HealthStatus,
    RolloutState,
    activate_canary,
    assess_health,
    automatic_rollback,
    seal_activation_approval,
    seal_baseline,
    seal_health_observation,
)
from app.shadow_epistemic_acceptance import (
    REQUIRED_SHADOW_SCENARIOS,
    ShadowAcceptanceEvidence,
    ShadowAcceptanceMetrics,
    ShadowPerformance,
    _acceptance_payload,
    _fingerprint,
)

NOW = datetime(2026, 8, 21, 13, 0, tzinfo=UTC)
CANDIDATE = "a" * 64
BASELINE_PROFILE = "b" * 64
IDENTITY = CanaryIdentity(
    tenant_id="tenant-a",
    company_id="company-a",
    problem_class="operations-root-cause",
    rollout_id="rollout-001",
)


def _performance(quality: float) -> ShadowPerformance:
    return ShadowPerformance(
        correctness=quality,
        brier_score=round(1.0 - quality, 6),
        falsification_success=quality,
        contradiction_resolution=quality,
        information_gain_per_probe=quality,
        cost_efficiency=max(0.0, quality - 0.05),
        latency_efficiency=max(0.0, quality - 0.08),
    )


def _shadow() -> ShadowAcceptanceEvidence:
    metrics = ShadowAcceptanceMetrics(
        sample_count=8,
        scenario_count=8,
        baseline_mean_quality_score=0.72,
        candidate_mean_quality_score=0.91,
        measured_quality_improvement=0.19,
        baseline_mean_brier_score=0.28,
        candidate_mean_brier_score=0.09,
        baseline_mean_cost_efficiency=0.67,
        candidate_mean_cost_efficiency=0.86,
        baseline_mean_latency_efficiency=0.64,
        candidate_mean_latency_efficiency=0.83,
    )
    values = {
        "candidate_fingerprint": CANDIDATE,
        "promotion_binding_fingerprint": "c" * 64,
        "candidate_system_id": "jarvis-epistemic-candidate",
        "candidate_version": "candidate-v1",
        "tenant_id": IDENTITY.tenant_id,
        "company_id": IDENTITY.company_id,
        "problem_class": IDENTITY.problem_class,
        "required_scenarios": REQUIRED_SHADOW_SCENARIOS,
        "observed_scenarios": REQUIRED_SHADOW_SCENARIOS,
        "observation_fingerprints": tuple(f"{i:064x}" for i in range(1, 9)),
        "evidence_refs": ("shadow-acceptance://candidate-v1",),
        "metrics": metrics,
        "production_shaped_acceptance_passed": True,
        "controlled_activation_review_ready": True,
        "automatic_activation_allowed": False,
        "automatic_policy_update_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
        "blockers": (),
    }
    draft = ShadowAcceptanceEvidence.model_construct(
        **values,
        acceptance_fingerprint="0" * 64,
    )
    return ShadowAcceptanceEvidence(
        **values,
        acceptance_fingerprint=_fingerprint(_acceptance_payload(draft)),
    )


def _baseline(profile: str = BASELINE_PROFILE):
    return seal_baseline(
        tenant_id=IDENTITY.tenant_id,
        company_id=IDENTITY.company_id,
        problem_class=IDENTITY.problem_class,
        profile_ref="epistemic-profile://baseline-v1",
        profile_fingerprint=profile,
        approved_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        approval_evidence_ref="approval://baseline-v1",
    )


def _approval(shadow, baseline, **overrides):
    values = {
        "identity": IDENTITY,
        "generation": 1,
        "candidate_fingerprint": shadow.candidate_fingerprint,
        "baseline": baseline,
        "shadow_acceptance_fingerprint": shadow.acceptance_fingerprint,
        "maximum_exposure_fraction": 0.10,
        "approved_by_ref": "principal://platform-admin-1",
        "approval_authority_ref": "authority://epistemic-rollout-review-v1",
        "approval_authority_verified": True,
        "approval_evidence_ref": "approval://rollout-001",
        "approved_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    return seal_activation_approval(**values)


def _activated():
    shadow, baseline = _shadow(), _baseline()
    approval = _approval(shadow, baseline)
    snapshot, receipt = activate_canary(
        shadow=shadow,
        baseline=baseline,
        approval=approval,
        activated_at=NOW,
    )
    return shadow, baseline, approval, snapshot, receipt


def _health(
    snapshot,
    *,
    sample_count=120,
    ended_at=NOW + timedelta(minutes=5),
    quality=0.91,
    grounding=1.0,
    authority=1.0,
    safe_failure=1.0,
    error_rate=0.015,
    observation_id="health-001",
):
    return seal_health_observation(
        snapshot=snapshot,
        observation_id=observation_id,
        window_started_at=ended_at - timedelta(minutes=5),
        window_ended_at=ended_at,
        sample_count=sample_count,
        baseline=_performance(0.86),
        candidate=_performance(quality),
        grounding_integrity_rate=grounding,
        authority_integrity_rate=authority,
        safe_failure_rate=safe_failure,
        baseline_error_rate=0.02,
        candidate_error_rate=error_rate,
        evidence_refs=(f"canary-telemetry://{observation_id}",),
    )


def test_review_activates_only_bounded_epistemic_selection() -> None:
    _, baseline, _, snapshot, receipt = _activated()
    assert snapshot.state is RolloutState.ACTIVE
    assert snapshot.generation == 1
    assert snapshot.selected_profile_fingerprint == CANDIDATE
    assert snapshot.baseline_profile_fingerprint == baseline.profile_fingerprint
    assert receipt.maximum_exposure_fraction == 0.10
    assert receipt.epistemic_selection_state_changed is True
    assert not any(receipt.authority.model_dump().values())


def test_unverified_review_authority_cannot_approve() -> None:
    shadow, baseline = _shadow(), _baseline()
    with pytest.raises(ValueError, match="requires_verified_review_authority"):
        _approval(shadow, baseline, approval_authority_verified=False)


def test_tampered_shadow_or_approval_is_rejected() -> None:
    shadow, baseline = _shadow(), _baseline()
    approval = _approval(shadow, baseline)
    tampered_shadow = shadow.model_copy(update={"candidate_version": "forged-v9"})
    with pytest.raises(ValueError, match="shadow_acceptance_fingerprint_mismatch"):
        activate_canary(
            shadow=tampered_shadow,
            baseline=baseline,
            approval=approval,
            activated_at=NOW,
        )
    tampered_approval = approval.model_copy(update={"maximum_exposure_fraction": 0.25})
    with pytest.raises(ValueError, match="canary_approval_fingerprint_mismatch"):
        activate_canary(
            shadow=shadow,
            baseline=baseline,
            approval=tampered_approval,
            activated_at=NOW,
        )


def test_cross_tenant_approval_is_rejected() -> None:
    shadow, baseline = _shadow(), _baseline()
    wrong_identity = IDENTITY.model_copy(update={"tenant_id": "tenant-b"})
    approval = _approval(shadow, baseline, identity=wrong_identity)
    with pytest.raises(ValueError, match="approval_identity_mismatch"):
        activate_canary(
            shadow=shadow,
            baseline=baseline,
            approval=approval,
            activated_at=NOW,
        )


def test_healthy_fresh_telemetry_keeps_canary_active() -> None:
    *_, snapshot, _ = _activated()
    verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    assert verdict.status is HealthStatus.HEALTHY
    assert verdict.rollback_required is False
    assert verdict.blockers == ()


@pytest.mark.parametrize(
    ("kwargs", "blocker"),
    (
        ({"grounding": 0.90}, "grounding_integrity_regression"),
        ({"authority": 0.98}, "authority_integrity_regression"),
        ({"safe_failure": 0.80}, "safe_failure_regression"),
        ({"quality": 0.70}, "quality_regression"),
        ({"error_rate": 0.20}, "error_rate_regression"),
    ),
)
def test_health_regressions_force_rollback(kwargs, blocker) -> None:
    *_, snapshot, _ = _activated()
    verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot, **kwargs),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    assert verdict.status is HealthStatus.DRIFTED
    assert verdict.rollback_required is True
    assert any(blocker in item for item in verdict.blockers)


def test_stale_or_insufficient_telemetry_fails_closed() -> None:
    *_, snapshot, _ = _activated()
    observation = _health(
        snapshot,
        sample_count=5,
        ended_at=NOW - timedelta(hours=1),
    )
    verdict = assess_health(
        snapshot=snapshot,
        observation=observation,
        evaluated_at=NOW,
    )
    assert verdict.status is HealthStatus.UNKNOWN
    assert verdict.rollback_required is True
    assert "canary_health_telemetry_stale" in verdict.blockers
    assert "canary_health_sample_count_insufficient" in verdict.blockers


def test_tampered_health_is_rejected_before_use() -> None:
    *_, snapshot, _ = _activated()
    observation = _health(snapshot)
    tampered = observation.model_copy(update={"generation": 2})
    with pytest.raises(ValueError, match="canary_health_fingerprint_mismatch"):
        assess_health(
            snapshot=snapshot,
            observation=tampered,
            evaluated_at=NOW + timedelta(minutes=6),
        )


def _rollback_fixture():
    shadow, baseline, approval, snapshot, activation = _activated()
    verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot, grounding=0.90),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    rolled_back, receipt = automatic_rollback(
        snapshot=snapshot,
        activation=activation,
        baseline=baseline,
        verdict=verdict,
        idempotency_key="rollback:rollout-001:gen-1",
        rolled_back_at=NOW + timedelta(minutes=7),
    )
    return shadow, baseline, approval, snapshot, activation, verdict, rolled_back, receipt


def test_drift_rolls_back_only_to_exact_baseline() -> None:
    _, baseline, _, _, _, _, rolled_back, receipt = _rollback_fixture()
    assert rolled_back.state is RolloutState.ROLLED_BACK
    assert rolled_back.generation == 2
    assert rolled_back.selected_profile_fingerprint == BASELINE_PROFILE
    assert receipt.approved_baseline_fingerprint == baseline.baseline_fingerprint
    assert receipt.restored_baseline_profile_fingerprint == BASELINE_PROFILE
    assert not any(receipt.authority.model_dump().values())


def test_wrong_baseline_cannot_be_rollback_target() -> None:
    _, _, _, snapshot, activation = _activated()
    verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot, grounding=0.90),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(ValueError, match="canary_rollback_exact_baseline_required"):
        automatic_rollback(
            snapshot=snapshot,
            activation=activation,
            baseline=_baseline("d" * 64),
            verdict=verdict,
            idempotency_key="rollback:wrong-baseline",
            rolled_back_at=NOW + timedelta(minutes=7),
        )


def test_healthy_verdict_cannot_trigger_automatic_rollback() -> None:
    _, baseline, _, snapshot, activation = _activated()
    verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(ValueError, match="requires_unhealthy_verdict"):
        automatic_rollback(
            snapshot=snapshot,
            activation=activation,
            baseline=baseline,
            verdict=verdict,
            idempotency_key="rollback:healthy-canary",
            rolled_back_at=NOW + timedelta(minutes=7),
        )


def test_rollback_replay_is_idempotent() -> None:
    _, baseline, _, _, activation, verdict, rolled_back, receipt = _rollback_fixture()
    replay_snapshot, replay_receipt = automatic_rollback(
        snapshot=rolled_back,
        activation=activation,
        baseline=baseline,
        verdict=verdict,
        idempotency_key=receipt.idempotency_key,
        rolled_back_at=NOW + timedelta(minutes=20),
        previous_receipt=receipt,
    )
    assert replay_snapshot.snapshot_fingerprint == rolled_back.snapshot_fingerprint
    assert replay_receipt.rollback_fingerprint == receipt.rollback_fingerprint


def test_conflicting_idempotent_replay_is_rejected() -> None:
    _, baseline, _, snapshot, activation, _, rolled_back, receipt = _rollback_fixture()
    other_verdict = assess_health(
        snapshot=snapshot,
        observation=_health(snapshot, authority=0.90, observation_id="health-002"),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(ValueError, match="canary_rollback_idempotency_conflict"):
        automatic_rollback(
            snapshot=rolled_back,
            activation=activation,
            baseline=baseline,
            verdict=other_verdict,
            idempotency_key=receipt.idempotency_key,
            rolled_back_at=NOW + timedelta(minutes=20),
            previous_receipt=receipt,
        )


def test_rollback_blocks_stale_approval_resurrection() -> None:
    shadow, baseline, approval, _, _, _, rolled_back, _ = _rollback_fixture()
    with pytest.raises(ValueError, match="canary_activation_rollout_already_exists"):
        activate_canary(
            shadow=shadow,
            baseline=baseline,
            approval=approval,
            activated_at=NOW + timedelta(minutes=8),
            current_snapshot=rolled_back,
        )


def test_activation_receipt_tampering_cannot_grant_authority() -> None:
    *_, receipt = _activated()
    tampered_authority = receipt.authority.model_copy(
        update={"provider_authority_granted": True}
    )
    tampered = receipt.model_copy(update={"authority": tampered_authority})
    with pytest.raises(ValueError, match="canary_never_grants_execution_authority"):
        ActivationReceipt.model_validate(tampered.model_dump(mode="json"))


def test_approval_is_frozen() -> None:
    approval = _approval(_shadow(), _baseline())
    with pytest.raises(Exception):
        approval.maximum_exposure_fraction = 0.25
    assert isinstance(approval, ActivationApproval)
